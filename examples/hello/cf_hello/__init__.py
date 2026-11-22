"""Hello: the smallest useful Cypress Forge add-on (MIT).

Shows every hook in backend/addons.py:
  on_event     counts core events by kind
  on_snapshot  remembers when the last snapshot was stored and how many clients it held
  routes       GET /api/addon/hello/stats returns those numbers
  static_dir   a one-page UI at /addon/hello/

State lives in memory only, so it resets when the dashboard restarts.
"""
import threading
import time
from collections import Counter
from pathlib import Path

UI = Path(__file__).parent / 'ui'


class Hello:
    title = 'Hello'
    version = '0.1.0'

    def __init__(self):
        # Hooks run from the poll loop thread and request threads: guard shared state.
        self._lock = threading.Lock()
        self.started = time.time()
        self.events = Counter()
        self.snapshots = 0
        self.last_snapshot = None

    def on_event(self, event):
        with self._lock:
            self.events[str(event.get('kind', 'unknown'))] += 1

    def on_snapshot(self, snapshot, previous):
        clients = snapshot.get('clients') or []
        with self._lock:
            self.snapshots += 1
            self.last_snapshot = dict(timestamp=snapshot.get('timestamp'), clients=len(clients),
                                      first=previous is None)

    def stats(self):
        with self._lock:
            return dict(started=self.started, snapshots=self.snapshots,
                        last_snapshot=dict(self.last_snapshot) if self.last_snapshot else None,
                        events=dict(sorted(self.events.items())),
                        event_total=sum(self.events.values()))

    def routes(self):
        from fastapi import APIRouter
        router = APIRouter()

        @router.get('/stats')
        def stats():
            return self.stats()

        return router

    def static_dir(self):
        return UI
