import copy
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from starlette.requests import Request
from starlette.responses import Response
from starlette.middleware.trustedhost import TrustedHostMiddleware
from backend.collector import parse
from backend.main import create_app
from backend.observations import changes
from backend.store import Store
from test_backend import fixture


def inline(coroutine):
    """Drive immediate async dependencies without Windows loopback socketpair setup."""
    try:
        coroutine.send(None)
    except StopIteration as done:
        return done.value
    else:
        coroutine.close()
        raise AssertionError('Unexpected real asynchronous I/O in isolated test')


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Store(Path(self.temp.name)/'test.sqlite3')
        self.a=parse(fixture(time.time()),'192.168.1.1')
        self.b=copy.deepcopy(self.a);self.b['timestamp']+=60;self.b['router']['uptime']+=60
    def tearDown(self):self.temp.cleanup()

    def test_device_ledger_and_address_history(self):
        self.db.add(self.a);self.b['clients'][0]['ip']='192.168.1.99';self.db.add(self.b)
        row=self.db.devices()[0]
        self.assertEqual(row['first_seen'],self.a['timestamp'])
        self.assertEqual(row['last_seen'],self.b['timestamp'])
        self.assertEqual(row['addresses'],['192.168.1.2','192.168.1.99'])
        self.assertIn('address_changed',[e['kind'] for e in self.db.events()])

    def test_missing_is_not_offline(self):
        self.b['clients']=[]
        events=changes(self.a,self.b)
        self.assertEqual(events[0]['kind'],'device_missing')
        self.assertIn('connectivity is unknown',events[0]['message'])

    def test_interface_errors_and_reboot(self):
        self.b['router']['uptime']=1;self.b['router']['release']='new'
        self.b['interfaces'][0]['up']=False
        self.b['interfaces'][0]['counters']['rx_errors']=4
        kinds={e['kind'] for e in changes(self.a,self.b)}
        self.assertTrue({'router_reboot','firmware_changed','interface_down','interface_errors'}<=kinds)

    def test_duplicate_observation_does_not_duplicate_events(self):
        self.db.add(self.a);self.db.add(self.a)
        self.assertEqual(len(self.db.events()),1)
        self.assertEqual(len(self.db.history()),1)

    def test_baseline_and_read_only_api(self):
        self.db.add(self.a)
        app=create_app({'mode':'live','poll_seconds':60},self.db)
        dashboard=next(r.endpoint for r in app.routes if r.path=='/api/dashboard')()
        self.assertEqual(len(dashboard['devices']),1)
        self.assertEqual(dashboard['events'][0]['kind'],'baseline')
        history=next(r.endpoint for r in app.routes if r.path=='/api/history')(24,100)
        self.assertEqual(len(history['snapshots']),1)
        demo=create_app({'mode':'demo','poll_seconds':60},self.db)
        d=next(r.endpoint for r in demo.routes if r.path=='/api/dashboard')()
        self.assertEqual(d['events'],[]);self.assertEqual(d['devices'],[]);self.assertEqual(d['history'],[])

    def test_retention_applies_to_events_and_inventory(self):
        self.a['timestamp']=time.time()-9*86400
        self.db.add(self.a)
        self.assertEqual(self.db.devices(),[]);self.assertEqual(self.db.events(),[])

    def test_non_destructive_schema_upgrade(self):
        path=Path(self.temp.name)/'old.sqlite3'
        import sqlite3
        db=sqlite3.connect(path)
        try:
            db.execute('CREATE TABLE snapshots (ts REAL PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('INSERT INTO snapshots VALUES (?,?)',(self.a['timestamp'],json.dumps(self.a)));db.commit()
        finally:db.close()
        migrated=Store(path)
        self.assertEqual(len(migrated.history()),1);self.assertEqual(len(migrated.devices()),1)

    def test_failure_deduplication_and_recovery(self):
        results=iter([RuntimeError('Denied'),RuntimeError('Denied'),self.a])
        def collector(_):
            result=next(results)
            if isinstance(result,Exception):raise result
            return result
        async def direct(fn,*args):return fn(*args)
        app=create_app({'mode':'live','poll_seconds':60},self.db,collector)
        with patch('backend.main.asyncio.to_thread',direct):
            inline(app.state.poll_once());inline(app.state.poll_once());inline(app.state.poll_once())
        kinds=[e['kind'] for e in self.db.events()]
        self.assertEqual(kinds.count('collector_failure'),1)
        self.assertEqual(kinds.count('collector_recovered'),1)
        self.assertTrue(app.state.collector_state['verified'])

    def test_request_boundaries_without_network_transport(self):
        app=create_app({'mode':'demo','poll_seconds':60},self.db)
        dispatch=next(m.kwargs['dispatch'] for m in app.user_middleware if 'dispatch' in m.kwargs)
        async def ok(request):return Response('OK')
        def request(method='GET',origin=None,client='127.0.0.1'):
            return Request({'type':'http','method':method,'path':'/api/dashboard','headers':[(b'origin',origin.encode())] if origin else [],'client':(client,1234)})
        self.assertEqual(inline(dispatch(request('POST'),ok)).status_code,405)
        self.assertEqual(inline(dispatch(request(origin='https://evil.example'),ok)).status_code,403)
        self.assertEqual(inline(dispatch(request(client='192.168.1.2'),ok)).status_code,403)
        self.assertEqual(inline(dispatch(request(),ok)).status_code,200)
        settings=next(m.kwargs for m in app.user_middleware if m.cls is TrustedHostMiddleware)
        sent=[]
        async def send(message):sent.append(message)
        async def receive():return {'type':'http.request','body':b''}
        async def unused(scope,receive,send):raise AssertionError('Bad host reached application')
        middleware=TrustedHostMiddleware(unused,**settings)
        inline(middleware({'type':'http','path':'/','headers':[(b'host',b'evil.example')]},receive,send))
        self.assertEqual(sent[0]['status'],400)


if __name__=='__main__':unittest.main()
