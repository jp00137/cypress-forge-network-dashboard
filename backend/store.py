import json
import logging
import sqlite3
import threading
import time
from contextlib import contextmanager, closing
from .collector import ROOT
from .observations import changes

log = logging.getLogger('cypress')


class Store:
    def __init__(self, path=None, retention_days=7):
        self.retention_days = max(1, min(90, int(retention_days)))
        self.path = path or ROOT / 'data' / 'history.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Optional callable(event) for add-ons; called only after the event's transaction commits.
        self.event_hook = None
        self._local = threading.local()
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS snapshots (ts REAL PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, ts REAL NOT NULL, kind TEXT, subject TEXT, message TEXT, severity TEXT)')
            db.execute('CREATE INDEX IF NOT EXISTS events_time ON events(ts)')
            db.execute('CREATE INDEX IF NOT EXISTS events_subject_time ON events(subject,ts)')
            db.execute('CREATE TABLE IF NOT EXISTS firewall_state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS dhcp_state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS devices (mac TEXT PRIMARY KEY, first_seen REAL, last_seen REAL, payload TEXT)')
            # Non-destructive v0.1 migration: recover inventory from retained snapshots.
            if not db.execute('SELECT 1 FROM devices LIMIT 1').fetchone():
                for ts, payload in db.execute('SELECT ts, payload FROM snapshots ORDER BY ts').fetchall():
                    self._devices(db, json.loads(payload))

    @contextmanager
    def connect(self):
        # sqlite's own context manager commits but does not close the connection.
        # Explicit close is essential for Windows backups/rollback and file locks.
        outer = getattr(self._local, 'pending', None)
        pending = self._local.pending = []
        try:
            with closing(sqlite3.connect(self.path, timeout=10)) as db:
                with db:
                    yield db
        finally:
            self._local.pending = outer
        # Reached only when the transaction committed; a rollback notifies nobody.
        self._notify(pending)

    def _notify(self, pending):
        hook = self.event_hook
        if not hook:
            return
        for event in pending:
            try:
                hook(event)
            except Exception as exc:
                log.warning('Event hook failed: %s', type(exc).__name__)

    def add(self, snapshot):
        if snapshot['mode'] != 'live':
            raise ValueError('Only live observations belong in history')
        with self.connect() as db:
            prior = db.execute('SELECT payload FROM snapshots ORDER BY ts DESC LIMIT 1').fetchone()
            previous = json.loads(prior[0]) if prior else None
            # A repeated timestamp must not generate duplicate events.
            if db.execute('SELECT 1 FROM snapshots WHERE ts = ?', (snapshot['timestamp'],)).fetchone():
                return False
            db.execute('INSERT OR REPLACE INTO snapshots VALUES (?, ?)',
                       (snapshot['timestamp'], json.dumps(snapshot)))
            self._devices(db, snapshot)
            events = changes(previous, snapshot) if previous else [dict(kind='baseline', subject='collector', message='First verified observation recorded. Device presence is not proof of connectivity.', severity='info')]
            for event in events:
                self._event(db, snapshot['timestamp'], event)
            cutoff = time.time() - self.retention_days * 86400
            db.execute('DELETE FROM snapshots WHERE ts < ?', (cutoff,))
            db.execute('DELETE FROM events WHERE ts < ?', (cutoff,))
            db.execute('DELETE FROM devices WHERE last_seen < ?', (cutoff,))
        return True

    def _devices(self, db, snapshot):
        for client in snapshot['clients']:
            prior = db.execute('SELECT payload FROM devices WHERE mac=?', (client['mac'],)).fetchone()
            addresses = json.loads(prior[0]).get('addresses', []) if prior else []
            addresses = [ip for ip in addresses if ip != client['ip']] + [client['ip']]
            payload = {**client, 'addresses': addresses[-50:]}
            db.execute('INSERT INTO devices VALUES (?, ?, ?, ?) ON CONFLICT(mac) DO UPDATE SET last_seen=excluded.last_seen, payload=excluded.payload',
                       (client['mac'], snapshot['timestamp'], snapshot['timestamp'], json.dumps(payload)))

    def _event(self, db, ts, event):
        db.execute('INSERT INTO events(ts,kind,subject,message,severity) VALUES (?,?,?,?,?)',
                   (ts, event['kind'], event['subject'], event['message'], event['severity']))
        pending = getattr(self._local, 'pending', None)
        if pending is not None:
            pending.append(dict(ts=ts, kind=event['kind'], subject=event['subject'],
                                message=event['message'], severity=event['severity']))

    def event(self, kind, message, severity='warning'):
        with self.connect() as db:
            self._event(db, time.time(), dict(kind=kind, subject='collector', message=message, severity=severity))
            db.execute('DELETE FROM events WHERE ts < ?', (time.time() - self.retention_days * 86400,))

    def events(self, limit=200):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute('SELECT * FROM events ORDER BY ts DESC, id DESC LIMIT ?', (limit,))]

    def device_events(self, mac, limit=500):
        limit = max(1, min(1000, int(limit)))
        cutoff = time.time() - self.retention_days * 86400
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute('SELECT * FROM events WHERE subject=? AND ts>=? ORDER BY ts DESC,id DESC LIMIT ?',
                              (mac, cutoff, limit + 1)).fetchall()
        return [dict(row) for row in rows[:limit]], len(rows) > limit

    def devices(self):
        with self.connect() as db:
            return [dict(**json.loads(row[2]), first_seen=row[0], last_seen=row[1]) for row in db.execute('SELECT first_seen,last_seen,payload FROM devices ORDER BY last_seen DESC LIMIT 2000')]

    def history(self, limit=120, hours=None):
        with self.connect() as db:
            rows = db.execute('SELECT payload FROM snapshots WHERE ts >= ? ORDER BY ts DESC LIMIT ?',
                              (time.time() - hours * 3600 if hours else 0, limit)).fetchall()
        return [json.loads(r[0]) for r in reversed(rows)]

    def backup(self, target):
        with self.connect() as source, closing(sqlite3.connect(target)) as destination:
            source.backup(destination)

    def firewall(self):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM firewall_state WHERE id=1').fetchone()
        return json.loads(row[0]) if row else None

    def dhcp(self):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM dhcp_state WHERE id=1').fetchone()
        return json.loads(row[0]) if row else None

    def save_dhcp(self, snapshot):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM dhcp_state WHERE id=1').fetchone()
            old = json.loads(row[0]) if row else None
            if not old or old.get('config_hash') != snapshot['config_hash']:
                self._event(db, snapshot['timestamp'], dict(kind='dhcp_config_changed' if old else 'dhcp_baseline',
                    subject='dhcp_dns', message='Committed DHCP/DNS configuration changed.' if old else 'Committed DHCP/DNS configuration read successfully.',
                    severity='warning' if old else 'info'))
            db.execute('INSERT OR REPLACE INTO dhcp_state VALUES (1, ?)', (json.dumps(snapshot),))
            db.execute('DELETE FROM events WHERE ts < ?', (time.time() - self.retention_days * 86400,))

    def save_firewall(self, snapshot):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM firewall_state WHERE id=1').fetchone()
            old = json.loads(row[0]) if row else None
            events = [('firewall_baseline', 'Committed configuration and active nftables read successfully.', 'info')] if not old else []
            if old:
                for key, kind, message in [('config_hash', 'firewall_config_changed', 'Committed firewall configuration changed.'),
                                            ('active_hash', 'firewall_runtime_changed', 'Active nftables structure changed; traffic counters and handles are excluded.')]:
                    if old.get(key) != snapshot.get(key):
                        events.append((kind, message, 'warning'))
            for kind, message, severity in events:
                self._event(db, snapshot['timestamp'], dict(kind=kind, subject='firewall', message=message, severity=severity))
            db.execute('INSERT OR REPLACE INTO firewall_state VALUES (1, ?)', (json.dumps(snapshot),))
            db.execute('DELETE FROM events WHERE ts < ?', (time.time() - self.retention_days * 86400,))


def rates(current, previous):
    if not previous:
        return
    dt = current['timestamp'] - previous['timestamp']
    if dt <= 0 or current['router']['uptime'] <= previous['router']['uptime']:
        return
    old_ports = {p['name']: p for p in previous.get('ports', [])}
    for port in current.get('ports', []):
        prior = old_ports.get(port['name'])
        if not prior or port.get('carrier') is not True or prior.get('carrier') is not True:
            continue
        for key in ('rx', 'tx'):
            a, b = port['counters'].get(key), prior.get('counters', {}).get(key)
            if a is not None and b is not None and a >= b:
                port[key + '_mbps'] = round((a - b) * 8 / dt / 1_000_000, 3)
    old = {x['name']: x for x in previous['interfaces']}
    # WAN direction is relative to the router. Do not sum LAN + WAN (double counting).
    for interface in current['interfaces']:
        if interface['name'] != 'wan':
            continue
        prior = old.get('wan', {})
        if prior.get('device') != interface['device']:
            return
        for key in ('rx', 'tx'):
            a, b = interface['counters'].get(key), prior.get('counters', {}).get(key)
            if a is not None and b is not None and a >= b:
                current[key + '_mbps'] = round((a - b) * 8 / dt / 1_000_000, 3)
