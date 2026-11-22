"""Task 2: the examples/hello add-on works through the real seam, without being installed."""
import asyncio
import copy
import sys
import tempfile
import time
import tomllib
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from backend.addons import AddonManager
from backend.collector import parse
from backend.main import create_app
from backend.store import Store
from test_backend import fixture

HELLO = Path(__file__).resolve().parents[1] / 'examples' / 'hello'
sys.path.insert(0, str(HELLO))
from cf_hello import Hello  # noqa: E402

LOCAL = 'http://127.0.0.1:8765'


class HelloExampleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Store(Path(self.temp.name) / 'history.sqlite3')

    def tearDown(self):
        self.temp.cleanup()

    def test_entry_point_matches_package(self):
        meta = tomllib.loads((HELLO / 'pyproject.toml').read_text())
        self.assertEqual(meta['project']['entry-points']['cypressforge.addons'], {'hello': 'cf_hello:Hello'})
        self.assertTrue((HELLO / 'cf_hello' / 'ui' / 'index.html').is_file())
        self.assertTrue((HELLO / 'cf_hello' / 'ui' / 'app.js').is_file())

    def test_listed_with_all_hooks_and_ui_served(self):
        manager = AddonManager([('hello', Hello())])
        app = create_app({'mode': 'demo', 'poll_seconds': 60}, self.db, addons=manager)
        with TestClient(app, base_url=LOCAL) as c:
            listed = c.get('/api/addons').json()['addons']
            self.assertIn('Hello add-on', c.get('/addon/hello/').text)
            self.assertEqual(c.get('/addon/hello/app.js').status_code, 200)
            stats = c.get('/api/addon/hello/stats').json()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]['hooks'], ['on_snapshot', 'on_event', 'routes', 'static_dir'])
        self.assertEqual((listed[0]['api'], listed[0]['ui']), ('/api/addon/hello/', '/addon/hello/'))
        self.assertEqual(listed[0]['errors'], 0)
        self.assertEqual(stats['snapshots'], 0)
        self.assertIsNone(stats['last_snapshot'])

    def test_counts_snapshots_and_events_from_live_polls(self):
        now = time.time()
        a = parse(fixture(now - 60), '192.168.1.1', now - 60)
        b = copy.deepcopy(a)
        b['timestamp'] = now
        b['router']['uptime'] += 60
        items = iter([a, b])
        hello = Hello()
        app = create_app({'mode': 'live', 'poll_seconds': 60}, self.db,
                         lambda _: copy.deepcopy(next(items)), addons=AddonManager([('hello', hello)]))
        asyncio.run(app.state.poll_once())
        asyncio.run(app.state.poll_once())
        self.db.event('collector_failure', 'test failure')
        stats = hello.stats()  # no TestClient here: live mode would start the background poller
        self.assertEqual(stats['snapshots'], 2)
        self.assertEqual(stats['last_snapshot'], dict(timestamp=b['timestamp'], clients=len(b['clients']), first=False))
        self.assertEqual(stats['events']['baseline'], 1)
        self.assertEqual(stats['events']['collector_failure'], 1)
        self.assertEqual(stats['event_total'], sum(stats['events'].values()))

    def test_stats_route_is_read_only_and_local_only(self):
        app = create_app({'mode': 'demo', 'poll_seconds': 60}, self.db, addons=AddonManager([('hello', Hello())]))
        with TestClient(app, base_url=LOCAL) as c:
            self.assertEqual(c.post('/api/addon/hello/stats').status_code, 405)
        with TestClient(app, base_url=LOCAL, client=('192.168.1.8', 1234)) as c:
            self.assertEqual(c.get('/api/addon/hello/stats').status_code, 403)


if __name__ == '__main__':
    unittest.main()
