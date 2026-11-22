import tempfile
import time
import unittest
from pathlib import Path
from backend.store import Store
from backend.main import create_app


class DeviceEventTests(unittest.TestCase):
    def test_device_history_survives_global_event_window_and_applies_retention(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Store(Path(folder) / 'history.sqlite3', retention_days=7)
            mac = 'aa:bb:cc:dd:ee:ff'
            now = time.time()
            with db.connect() as connection:
                for i in range(250):
                    db._event(connection, now-i, dict(kind='test', subject='router', message='other', severity='info'))
                for ts in (now-1000, now-2000, now-9*86400):
                    db._event(connection, ts, dict(kind='address_changed', subject=mac, message='IP changed', severity='info'))
            self.assertFalse(any(e['subject'] == mac for e in db.events()))
            rows, truncated = db.device_events(mac, 1)
            self.assertEqual(len(rows), 1)
            self.assertTrue(truncated)
            rows, truncated = db.device_events(mac, 2)
            self.assertEqual(len(rows), 2)
            self.assertFalse(truncated)
            self.assertGreater(rows[0]['ts'], rows[1]['ts'])
            self.assertEqual(db.device_events("' OR 1=1 --")[0], [])
            live = create_app({'mode':'live','poll_seconds':60}, db)
            endpoint = next(r.endpoint for r in live.routes if r.path == '/api/device-events')
            self.assertEqual(len(endpoint('AA-BB-CC-DD-EE-FF', 500)['events']), 2)
            demo = create_app({'mode':'demo','poll_seconds':60}, db)
            endpoint = next(r.endpoint for r in demo.routes if r.path == '/api/device-events')
            self.assertEqual(endpoint(mac, 500)['events'], [])
