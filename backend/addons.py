"""Generic add-on seam (MIT). Core never imports an add-on by name.

An add-on registers an entry point in the ``cypressforge.addons`` group. The entry
point may name a class (instantiated with no arguments), an object, or a module.
Every hook is optional:

    on_snapshot(snapshot, previous)  after a live snapshot is stored
    on_event(event)                  after each core event is committed
    routes()                         FastAPI APIRouter, mounted at /api/addon/<name>/
    static_dir()                     built frontend folder, served at /addon/<name>/

An add-on with a static_dir may also set ``client = "file.js"``: a module in that folder
that core's dashboard page imports once (docs/THEME-SEAM.md), for example to override
the --cf-* colour tokens.

Hooks get copies of core data, run with errors caught and counted, and can never
stop collection. Add-on routes sit behind the same local-only middleware as core.
"""
import copy
import logging
import re
from importlib.metadata import entry_points
from pathlib import Path

GROUP = 'cypressforge.addons'
NAME = re.compile(r'[a-z0-9][a-z0-9_-]{0,31}')
HOOKS = ('on_snapshot', 'on_event', 'routes', 'static_dir')
CLIENT = re.compile(r'[A-Za-z0-9._-]+\.js')

log = logging.getLogger('cypress.addons')


class Addon:
    def __init__(self, name, obj):
        self.name = name
        self.obj = obj
        self.errors = 0
        self.last_error = None
        self.api = None
        self.ui = None
        self.client = None

    def has(self, hook):
        return callable(getattr(self.obj, hook, None))

    def call(self, hook, *args):
        """Run one hook; a failure is logged and counted, never raised."""
        try:
            return getattr(self.obj, hook)(*args)
        except Exception as exc:
            self.errors += 1
            self.last_error = f'{hook}: {type(exc).__name__}'
            # Type only: add-on exception text may carry tokens or passwords.
            log.warning('Add-on %s %s failed: %s', self.name, hook, type(exc).__name__)
            return None

    def info(self):
        return dict(name=self.name,
                    title=str(getattr(self.obj, 'title', self.name)),
                    version=str(getattr(self.obj, 'version', '') or ''),
                    hooks=[h for h in HOOKS if self.has(h)],
                    api=self.api, ui=self.ui, client=self.client,
                    errors=self.errors, last_error=self.last_error)


class AddonManager:
    def __init__(self, addons=()):
        self.addons = []
        for name, obj in addons:
            self._register(name, obj)

    def _register(self, name, obj):
        if not isinstance(name, str) or not NAME.fullmatch(name):
            log.warning('Skipping add-on with invalid name %r', name)
            return
        if any(a.name == name for a in self.addons):
            log.warning('Skipping duplicate add-on %s', name)
            return
        self.addons.append(Addon(name, obj))

    @classmethod
    def discover(cls, group=GROUP):
        manager = cls()
        try:
            found = list(entry_points(group=group))
        except Exception as exc:
            log.warning('Add-on discovery failed: %s', type(exc).__name__)
            return manager
        for ep in sorted(found, key=lambda e: e.name):
            try:
                obj = ep.load()
                if isinstance(obj, type):
                    obj = obj()
            except Exception as exc:
                log.warning('Add-on %s failed to load: %s', ep.name, type(exc).__name__)
                continue
            manager._register(ep.name, obj)
        return manager

    def snapshot(self, snapshot, previous):
        for addon in self.addons:
            if addon.has('on_snapshot'):
                addon.call('on_snapshot', copy.deepcopy(snapshot), copy.deepcopy(previous))

    def event(self, event):
        for addon in self.addons:
            if addon.has('on_event'):
                addon.call('on_event', dict(event))

    def mount(self, app):
        """Mount add-on API routers and static UIs. Bad parts are skipped, not fatal."""
        from fastapi import APIRouter
        from fastapi.staticfiles import StaticFiles
        for addon in self.addons:
            if addon.has('routes'):
                router = addon.call('routes')
                if isinstance(router, APIRouter):
                    try:
                        app.include_router(router, prefix=f'/api/addon/{addon.name}')
                        addon.api = f'/api/addon/{addon.name}/'
                    except Exception as exc:
                        addon.errors += 1
                        addon.last_error = f'routes: {type(exc).__name__}'
                        log.warning('Add-on %s routes not mounted: %s', addon.name, type(exc).__name__)
                elif router is not None:
                    addon.errors += 1
                    addon.last_error = 'routes: not an APIRouter'
            mounted = None
            if addon.has('static_dir'):
                folder = addon.call('static_dir')
                if folder is not None and Path(folder).is_dir():
                    mounted = Path(folder)
                    app.mount(f'/addon/{addon.name}', StaticFiles(directory=mounted, html=True),
                              name=f'addon-{addon.name}')
                    addon.ui = f'/addon/{addon.name}/'
                elif folder is not None:
                    addon.errors += 1
                    addon.last_error = 'static_dir: folder not found'
            self._client(addon, mounted)

    @staticmethod
    def _client(addon, mounted):
        """Accept ``client`` only as a plain .js file name inside the mounted static_dir."""
        name = getattr(addon.obj, 'client', None)
        if name is None:
            return
        if not isinstance(name, str) or not CLIENT.fullmatch(name) or name.startswith('.'):
            problem = 'client: invalid name'
        elif mounted is None:
            problem = 'client: no static_dir'
        elif not (mounted / name).is_file():
            problem = 'client: not found'
        else:
            problem = None
        if problem:
            addon.errors += 1
            addon.last_error = problem
            log.warning('Add-on %s %s', addon.name, problem)
        else:
            addon.client = f'/addon/{addon.name}/{name}'

    def info(self):
        return [addon.info() for addon in self.addons]
