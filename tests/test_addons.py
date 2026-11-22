import asyncio
import copy
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import APIRouter
from fastapi.testclient import TestClient
from backend.addons import AddonManager
from backend.collector import parse
from backend.main import create_app
from backend.store import Store
from test_backend import fixture

LOCAL = 'http://127.0.0.1:8765'


class Recorder:
    title = 'Recorder'
    version = '0.1.0'

    def __init__(self):
        self.snapshots, self.events = [], []

    def on_snapshot(self, snapshot, previous):
        self.snapshots.append((snapshot, previous))

    def on_event(self, event):
        self.events.append(event)


class Broken:
    def on_snapshot(self, snapshot, previous):
        raise RuntimeError('secret-token-123')

    def on_event(self, event):
        raise RuntimeError('secret-token-123')


class FakeEntryPoint:
    def __init__(self, name, target):
        self.name, self.target = name, target

    def load(self):
        if isinstance(self.target, Exception):
            raise self.target
        return self.target


def live(**extra):
    return {'mode': 'live', 'poll_seconds': 60, **extra}


class DiscoveryTests(unittest.TestCase):
    def discover(self, eps):
        with patch('backend.addons.entry_points', return_value=eps) as found:
            manager = AddonManager.discover()
        found.assert_called_once_with(group='cypressforge.addons')
        return manager

    def test_no_addons_installed(self):
        self.assertEqual(self.discover([]).info(), [])

    def test_class_instantiated_object_kept_bad_ones_skipped(self):
        obj = Recorder()
        manager = self.discover([FakeEntryPoint('alpha', Recorder), FakeEntryPoint('beta', obj),
                                 FakeEntryPoint('broken', ImportError('missing dep')),
                                 FakeEntryPoint('Bad Name!', Recorder), FakeEntryPoint('beta', Recorder)])
        self.assertEqual([a.name for a in manager.addons], ['alpha', 'beta'])
        self.assertIsInstance(manager.addons[0].obj, Recorder)
        self.assertIs(manager.addons[1].obj, obj)

    def test_discovery_failure_is_not_fatal(self):
        with patch('backend.addons.entry_points', side_effect=RuntimeError('broken metadata')):
            self.assertEqual(AddonManager.discover().addons, [])


class HookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Store(Path(self.temp.name) / 'history.sqlite3')

    def tearDown(self):
        self.temp.cleanup()

    def snaps(self):
        now = time.time()
        a = parse(fixture(now - 60), '192.168.1.1', now - 60)
        b = copy.deepcopy(a)
        b['timestamp'] = now
        b['router']['uptime'] += 60
        return a, b

    def test_on_snapshot_after_store_with_previous(self):
        rec = Recorder()
        a, b = self.snaps()
        items = iter([a, b, b])
        app = create_app(live(), self.db, lambda _: copy.deepcopy(next(items)), addons=AddonManager([('rec', rec)]))
        asyncio.run(app.state.poll_once())
        asyncio.run(app.state.poll_once())
        asyncio.run(app.state.poll_once())  # same timestamp: not stored, so no hook
        self.assertEqual(len(rec.snapshots), 2)
        self.assertIsNone(rec.snapshots[0][1])
        self.assertEqual(rec.snapshots[1][1]['timestamp'], a['timestamp'])
        self.assertEqual(rec.snapshots[1][0]['timestamp'], b['timestamp'])
        self.assertEqual(len(self.db.history()), 2)

    def test_no_snapshot_hook_on_failed_collection(self):
        rec = Recorder()
        def fail(_):
            raise RuntimeError('SSH authentication/read access failed')
        app = create_app(live(), self.db, fail, addons=AddonManager([('rec', rec)]))
        asyncio.run(app.state.poll_once())
        self.assertEqual(rec.snapshots, [])
        self.assertEqual([e['kind'] for e in rec.events], ['collector_failure'])

    def test_hook_gets_copy_not_core_state(self):
        class Mutator:
            def on_snapshot(self, snapshot, previous):
                snapshot['clients'].clear()
                snapshot['router']['model'] = 'tampered'
        a, _ = self.snaps()
        app = create_app(live(), self.db, lambda _: copy.deepcopy(a), addons=AddonManager([('mut', Mutator())]))
        asyncio.run(app.state.poll_once())
        self.assertEqual(app.state.collector_state['snapshot']['router']['model'], 'Meraki MX64')
        self.assertEqual(len(app.state.collector_state['snapshot']['clients']), 1)

    def test_broken_addon_never_stops_collection(self):
        rec = Recorder()
        a, b = self.snaps()
        items = iter([a, b])
        manager = AddonManager([('broken', Broken()), ('rec', rec)])
        app = create_app(live(), self.db, lambda _: copy.deepcopy(next(items)), addons=manager)
        with self.assertLogs('cypress.addons', 'WARNING') as logs:
            asyncio.run(app.state.poll_once())
            asyncio.run(app.state.poll_once())
        self.assertTrue(app.state.collector_state['verified'])
        self.assertEqual(len(self.db.history()), 2)
        self.assertEqual(len(rec.snapshots), 2)  # later add-ons still run
        self.assertGreater(manager.addons[0].errors, 0)
        self.assertNotIn('secret-token-123', '\n'.join(logs.output))

    def test_on_event_fires_after_commit_for_every_writer(self):
        seen = []
        db = self.db
        def hook(event):
            # Committed: a fresh connection can already read it.
            seen.append((event['kind'], any(e['kind'] == event['kind'] for e in db.events())))
        db.event_hook = hook
        a, _ = self.snaps()
        db.add(a)
        db.event('collector_failure', 'test')
        db.save_dhcp(dict(timestamp=time.time(), config_hash='x'))
        db.save_firewall(dict(timestamp=time.time(), config_hash='x', active_hash='y'))
        self.assertEqual(seen, [('baseline', True), ('collector_failure', True),
                                ('dhcp_baseline', True), ('firewall_baseline', True)])

    def test_rolled_back_event_not_announced(self):
        seen = []
        self.db.event_hook = seen.append
        with self.assertRaises(RuntimeError):
            with self.db.connect() as db:
                self.db._event(db, time.time(), dict(kind='x', subject='s', message='m', severity='info'))
                raise RuntimeError('fails mid-transaction')
        self.assertEqual(seen, [])
        self.assertEqual(self.db.events(), [])

    def test_event_has_fields_and_broken_hook_is_harmless(self):
        rec = Recorder()
        app = create_app(live(), self.db, addons=AddonManager([('broken', Broken()), ('rec', rec)]))
        self.db.event('collector_failure', 'Collection failed')
        self.assertEqual(len(self.db.events()), 1)
        self.assertEqual(set(rec.events[0]), {'ts', 'kind', 'subject', 'message', 'severity'})
        self.assertEqual(app.state.addons.addons[0].errors, 1)


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Store(Path(self.temp.name) / 'history.sqlite3')
        ui = Path(self.temp.name) / 'ui'
        ui.mkdir()
        (ui / 'index.html').write_text('<h1>hello add-on</h1>')
        router = APIRouter()

        @router.get('/ping')
        def ping():
            return {'pong': True}

        @router.post('/write')
        def write():
            return {'wrote': True}

        class Hello:
            title = 'Hello'
            version = '1.2.3'
            def routes(self):
                return router
            def static_dir(self):
                return ui

        class BadRoutes:
            def routes(self):
                raise RuntimeError('boom')
            def static_dir(self):
                return Path(self.temp_missing)
            temp_missing = '/nonexistent/cf-addon-ui'

        self.manager = AddonManager([('hello', Hello()), ('bad', BadRoutes())])

    def tearDown(self):
        self.temp.cleanup()

    def client(self, **kw):
        return TestClient(create_app({'mode': 'demo', 'poll_seconds': 60}, self.db, addons=self.manager),
                          base_url=LOCAL, **kw)

    def test_routes_static_and_listing(self):
        with self.client() as c:
            self.assertEqual(c.get('/api/addon/hello/ping').json(), {'pong': True})
            self.assertIn('hello add-on', c.get('/addon/hello/').text)
            listed = {a['name']: a for a in c.get('/api/addons').json()['addons']}
        self.assertEqual(listed['hello']['api'], '/api/addon/hello/')
        self.assertEqual(listed['hello']['ui'], '/addon/hello/')
        self.assertEqual(listed['hello']['version'], '1.2.3')
        self.assertEqual(listed['hello']['hooks'], ['routes', 'static_dir'])
        self.assertIsNone(listed['bad']['api'])
        self.assertIsNone(listed['bad']['ui'])
        self.assertGreater(listed['bad']['errors'], 0)

    def test_addon_routes_keep_core_boundaries(self):
        with self.client() as c:
            self.assertEqual(c.post('/api/addon/hello/write').status_code, 405)
            self.assertEqual(c.get('/api/addon/hello/ping', headers={'host': 'evil.example'}).status_code, 400)
            self.assertEqual(c.get('/api/addon/hello/ping', headers={'origin': 'https://evil.example'}).status_code, 403)
            self.assertIn("frame-ancestors 'none'", c.get('/addon/hello/').headers['content-security-policy'])
        with self.client(client=('192.168.1.8', 1234)) as c:
            self.assertEqual(c.get('/api/addon/hello/ping').status_code, 403)
            self.assertEqual(c.get('/addon/hello/').status_code, 403)

    def test_core_runs_with_no_addons(self):
        with TestClient(create_app({'mode': 'demo', 'poll_seconds': 60}, self.db, addons=AddonManager()),
                        base_url=LOCAL) as c:
            self.assertEqual(c.get('/api/addons').json(), {'addons': []})
            self.assertEqual(c.get('/api/health').status_code, 200)
        self.assertIsNone(self.db.event_hook)


class ClientScriptTests(unittest.TestCase):
    """THEME-SEAM.md: an add-on may name one .js module in its static_dir for core's page."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Store(Path(self.temp.name) / 'history.sqlite3')
        self.ui = Path(self.temp.name) / 'ui'
        self.ui.mkdir()
        (self.ui / 'index.html').write_text('<h1>ui</h1>')
        (self.ui / 'client.js').write_text('export {};')

    def tearDown(self):
        self.temp.cleanup()

    def listed(self, client, static=True):
        ui = self.ui

        class Addon:
            title = 'Themed'

        obj = Addon()
        if client is not ...:
            obj.client = client
        if static:
            obj.static_dir = lambda: ui
        app = create_app({'mode': 'demo', 'poll_seconds': 60}, self.db, addons=AddonManager([('themed', obj)]))
        with TestClient(app, base_url=LOCAL) as c:
            entry = c.get('/api/addons').json()['addons'][0]
            served = c.get(entry['client']) if entry['client'] else None
        return entry, served

    def test_accepted_client_is_listed_and_served(self):
        entry, served = self.listed('client.js')
        self.assertEqual(entry['client'], '/addon/themed/client.js')
        self.assertEqual(entry['errors'], 0)
        self.assertEqual(served.status_code, 200)
        self.assertIn('javascript', served.headers['content-type'])

    def test_no_client_attribute_lists_null(self):
        entry, _ = self.listed(...)
        self.assertIsNone(entry['client'])
        self.assertEqual(entry['errors'], 0)

    def test_missing_file_is_an_error(self):
        entry, _ = self.listed('other.js')
        self.assertIsNone(entry['client'])
        self.assertEqual(entry['last_error'], 'client: not found')

    def test_bad_names_are_rejected(self):
        (self.ui / 'x.mjs').write_text('')
        for bad in ('../client.js', 'sub/client.js', 'x.mjs', '.client.js', 'client.js?x', 42, ''):
            with self.subTest(bad=bad):
                entry, _ = self.listed(bad)
                self.assertIsNone(entry['client'])
                self.assertEqual(entry['last_error'], 'client: invalid name')

    def test_client_needs_static_dir(self):
        entry, _ = self.listed('client.js', static=False)
        self.assertIsNone(entry['client'])
        self.assertEqual(entry['last_error'], 'client: no static_dir')


if __name__ == '__main__':
    unittest.main()
