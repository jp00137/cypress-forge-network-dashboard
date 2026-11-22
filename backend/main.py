import asyncio
import contextlib
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .collector import ROOT, collect, sample, settings
from .store import Store, rates
from .firewall import collect_firewall
from .dhcp import collect_dhcp
from .addons import AddonManager

log = logging.getLogger('cypress')


def ssh_detail(exc, cfg):
    """Last SSH error lines for the local console only; never stored or served."""
    lines = [l.strip() for l in (getattr(exc, 'stderr', '') or '').splitlines() if l.strip()][-3:]
    text = ' | '.join(lines)
    if cfg.get('identity_file'):
        text = text.replace(cfg['identity_file'], '<identity_file>')
    return text or '-'


def create_app(config=None, store=None, collector=collect, firewall_collector=collect_firewall, dhcp_collector=collect_dhcp,
               addons=None):
    cfg = config or settings()
    db = store or Store(retention_days=cfg.get('retention_days', 7))
    addons = AddonManager.discover() if addons is None else addons
    db.event_hook = addons.event if addons.addons else None
    state = dict(verified=False, error=None, last_success=None, last_attempt=None,
                 snapshot=None, failures=0)
    firewall_state = dict(verified=False, error=None, failures=0, last_attempt=None)
    dhcp_state = dict(verified=False, error=None, failures=0, last_attempt=None)

    async def poll_dhcp_once():
        dhcp_state['last_attempt'] = time.time()
        try:
            snapshot = await asyncio.to_thread(dhcp_collector, cfg)
            await asyncio.to_thread(db.save_dhcp, snapshot)
            dhcp_state.update(verified=True, error=None, failures=0)
        except Exception as exc:
            log.warning('DHCP configuration read failed: %s (%s) SSH said: %s', type(exc).__name__, exc, ssh_detail(exc, cfg))
            if not dhcp_state['failures']:
                with contextlib.suppress(Exception):
                    await asyncio.to_thread(db.event, 'dhcp_read_failed', 'DHCP/DNS configuration read failed; other monitoring is independent.')
            dhcp_state.update(verified=False, failures=dhcp_state['failures'] + 1,
                error=str(exc) if isinstance(exc, RuntimeError) else 'DHCP/DNS configuration validation failed; other monitoring continues')

    async def dhcp_polling():
        while True:
            await poll_dhcp_once()
            await asyncio.sleep(min(3600, cfg.get('dhcp_seconds', 300) * 2 ** min(dhcp_state['failures'], 4)))

    async def poll_firewall_once():
        firewall_state['last_attempt'] = time.time()
        try:
            snapshot = await asyncio.to_thread(firewall_collector, cfg)
            await asyncio.to_thread(db.save_firewall, snapshot)
            firewall_state.update(verified=True, error=None, failures=0)
        except Exception as exc:
            log.warning('Firewall read failed: %s (%s) SSH said: %s', type(exc).__name__, exc, ssh_detail(exc, cfg))
            if not firewall_state['failures']:
                with contextlib.suppress(Exception):
                    await asyncio.to_thread(db.event, 'firewall_read_failed', 'Firewall reads failed; network/port monitoring is independent.')
            firewall_state.update(verified=False, failures=firewall_state['failures'] + 1,
                error=str(exc) if isinstance(exc, RuntimeError) else 'Firewall read/format validation failed; network monitoring continues')

    async def firewall_polling():
        while True:
            await poll_firewall_once()
            await asyncio.sleep(min(3600, cfg.get('firewall_seconds', 300) * 2 ** min(firewall_state['failures'], 4)))

    async def poll_once():
        state['last_attempt'] = time.time()
        try:
            snap = await asyncio.to_thread(collector, cfg)
            previous = state['snapshot']
            rates(snap, previous)
            added = await asyncio.to_thread(db.add, snap)
            if state['failures']:
                await asyncio.to_thread(db.event, 'collector_recovered', 'Authenticated collection recovered.', 'info')
            state.update(verified=True, error=None, last_success=snap['timestamp'],
                         snapshot=snap, failures=0)
            if added is not False and addons.addons:
                # Hooks catch their own errors; this guard keeps collection state correct regardless.
                with contextlib.suppress(Exception):
                    await asyncio.to_thread(addons.snapshot, snap, previous)
        except Exception as exc:
            log.warning('Collection failed: %s (%s) SSH said: %s', type(exc).__name__, exc, ssh_detail(exc, cfg))
            message = str(exc) if isinstance(exc, RuntimeError) else 'Collection/read validation failed'
            if not state['failures']:
                try:
                    await asyncio.to_thread(db.event, 'collector_failure', message)
                except Exception:
                    log.warning('Could not persist collection failure event')
            state.update(verified=False, error=message, failures=state['failures'] + 1)

    async def polling():
        while True:
            await poll_once()
            await asyncio.sleep(min(900, cfg['poll_seconds'] * 2 ** min(state['failures'], 4)))

    @asynccontextmanager
    async def lifespan(app):
        task = None
        firewall_task = None
        dhcp_task = None
        if cfg['mode'] == 'live':
            # Every start verifies all read permissions before the first observation is stored.
            task = asyncio.create_task(polling())
            if cfg.get('collect_firewall', False):
                firewall_task = asyncio.create_task(firewall_polling())
            if cfg.get('collect_dhcp', False):
                dhcp_task = asyncio.create_task(dhcp_polling())
        yield
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if firewall_task:
            firewall_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await firewall_task
        if dhcp_task:
            dhcp_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await dhcp_task

    app = FastAPI(title='CF Network Dashboard', docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]'])

    @app.middleware('http')
    async def local_only(request: Request, call_next):
        if request.client and request.client.host not in ('127.0.0.1', '::1', 'testclient'):
            return JSONResponse({'detail': 'Local access only'}, status_code=403)
        if request.method not in ('GET', 'HEAD'):
            return JSONResponse({'detail': 'Read-only service'}, status_code=405)
        origin = request.headers.get('origin')
        if origin and origin not in ('http://127.0.0.1:8765', 'http://localhost:8765'):
            return JSONResponse({'detail': 'Origin not allowed'}, status_code=403)
        response = await call_next(request)
        response.headers.update({'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
            'Cache-Control': 'no-store', 'Content-Security-Policy':
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"})
        return response

    @app.get('/api/dashboard')
    def dashboard():
        demo = cfg['mode'] == 'demo'
        snap = sample() if demo else state['snapshot']
        history = [] if demo else db.history()
        return dict(mode=cfg['mode'], verified=state['verified'], error=state['error'],
            last_success=state['last_success'], last_attempt=state['last_attempt'],
            poll_seconds=cfg['poll_seconds'], failures=state['failures'],
            stale=bool(not demo and (not state['verified'] or not state['last_success'] or time.time() - state['last_success'] > cfg['poll_seconds'] * 2)),
            snapshot=snap, history=history, retention_days=db.retention_days,
            collect_ports=cfg.get('collect_ports', False),
            collect_firewall=cfg.get('collect_firewall', False),
            collect_dhcp=cfg.get('collect_dhcp', False),
            events=[] if demo else db.events(), devices=[] if demo else db.devices(),
            manual_nodes=[dict(id='upstream', name='Internet provider', kind='upstream', evidence='manual'),
                          *[dict(id=f'deco-{i}', name=f'Access point {i}', kind='ap', evidence='manual') for i in range(1, 4)]])

    @app.get('/api/history')
    def history(hours: int = Query(24, ge=1, le=2160), limit: int = Query(1440, ge=1, le=10080)):
        rows = [] if cfg['mode'] == 'demo' else db.history(limit, hours)
        return dict(mode=cfg['mode'], snapshots=rows, limit=limit, hours=hours,
                    truncated=len(rows) == limit)

    @app.get('/api/device-events')
    def device_events(mac: str = Query(..., pattern=r'^([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}$'),
                      limit: int = Query(500, ge=1, le=1000)):
        mac = mac.lower().replace('-', ':')
        rows, truncated = ([], False) if cfg['mode'] == 'demo' else db.device_events(mac, limit)
        return dict(mode=cfg['mode'], mac=mac, events=rows, truncated=truncated,
                    limit=limit, retention_days=db.retention_days)

    @app.get('/api/addons')
    def addon_list():
        return dict(addons=addons.info())

    @app.get('/api/health')
    def health():
        return {'service': 'ok', 'mode': cfg['mode'], 'verified': state['verified']}

    @app.get('/api/firewall')
    def firewall():
        enabled = cfg['mode'] == 'live' and cfg.get('collect_firewall', False)
        snapshot = db.firewall() if cfg['mode'] == 'live' else None
        interval = cfg.get('firewall_seconds', 300)
        stale = bool(not enabled or not firewall_state['verified'] or not snapshot or time.time() - snapshot['timestamp'] > interval * 2)
        return dict(mode=cfg['mode'], enabled=enabled, interval=interval, stale=stale,
                    snapshot=snapshot, **firewall_state)

    @app.get('/api/dhcp')
    def dhcp():
        enabled = cfg['mode'] == 'live' and cfg.get('collect_dhcp', False)
        snapshot = db.dhcp() if cfg['mode'] == 'live' else None
        interval = cfg.get('dhcp_seconds', 300)
        stale = bool(not enabled or not dhcp_state['verified'] or not snapshot or time.time() - snapshot['timestamp'] > interval * 2)
        return dict(mode=cfg['mode'], enabled=enabled, interval=interval, stale=stale, snapshot=snapshot, **dhcp_state)

    # Add-on routes mount after core routes so an add-on can never shadow a core path.
    addons.mount(app)

    dist = ROOT / 'frontend' / 'dist'
    if dist.exists():
        app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')

        @app.get('/')
        def index():
            return FileResponse(dist / 'index.html')

    app.state.poll_once = poll_once
    app.state.collector_state = state
    app.state.poll_firewall_once = poll_firewall_once
    app.state.firewall_state = firewall_state
    app.state.poll_dhcp_once = poll_dhcp_once
    app.state.dhcp_state = dhcp_state
    app.state.addons = addons
    return app


app = create_app()
