import asyncio
import copy
import json
import sqlite3
import subprocess
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.collector import COMMANDS, collect, parse, sample, ssh_args
from backend.main import create_app
from backend.store import Store, rates


def fixture(now):
    return dict(board=json.dumps({'model':'Meraki MX64', 'hostname':'test', 'release':{'version':'test'}}),
        system=json.dumps({'uptime':300,'load':[65536,0,0], 'memory':{'total':1000,'available':400}}),
        interfaces=json.dumps({'interface':[{'interface':'wan','up':True,'l3_device':'eth0','ipv4-address':[{'address':'192.0.2.2'}]}]}),
        leases=f'{int(now+1000)} aa:bb:cc:dd:ee:ff 192.168.1.2 laptop *\n1 00:11:22:33:44:55 192.168.1.3 expired *\nmalformed',
        neighbors='192.168.1.2 dev br-lan lladdr aa:bb:cc:dd:ee:ff STALE\n192.168.1.4 dev br-lan FAILED',
        counters='eth0: 1000000 1 0 0 0 0 0 0 2000000 1 0 0 0 0 0 0')


class ParserTests(unittest.TestCase):
    def test_evidence_and_expired_leases(self):
        s=parse(fixture(1000),'192.168.1.1',1000)
        self.assertEqual(len(s['clients']),1)
        self.assertEqual(s['clients'][0]['state'],'STALE')
        self.assertEqual(s['clients'][0]['name'],'laptop')
        self.assertEqual(s['router']['load'],1)
        self.assertEqual(s['router']['memory'],60)
        self.assertEqual(s['interfaces'][0]['counters']['tx'],2000000)

    def test_invalid_required_reads_rejected(self):
        raw=fixture(1000);raw['interfaces']='{}'
        with self.assertRaises(ValueError): parse(raw,'192.168.1.1',1000)

    def test_rates_and_counter_reset(self):
        a=parse(fixture(1000),'192.168.1.1',1000);b=copy.deepcopy(a)
        b['timestamp']=1060;b['router']['uptime']=360
        b['interfaces'][0]['counters']['rx']+=7_500_000
        rates(b,a);self.assertEqual(b['rx_mbps'],1)
        b['rx_mbps']=None;b['interfaces'][0]['counters']['rx']=0
        rates(b,a);self.assertIsNone(b['rx_mbps'])
        b['router']['uptime']=1;b['interfaces'][0]['counters']['rx']=999999999
        rates(b,a);self.assertIsNone(b['rx_mbps'])

    def test_ssh_is_noninteractive_and_strict(self):
        cfg={'username':'root','host':'192.168.1.1','identity_file':''}
        args=ssh_args(cfg)
        self.assertIn('BatchMode=yes',args);self.assertIn('StrictHostKeyChecking=yes',args)
        with patch('backend.collector.subprocess.run') as run:
            run.return_value=subprocess.CompletedProcess(args,1,'','Permission denied')
            with self.assertRaisesRegex(RuntimeError,'authentication/read'):collect(cfg)
            kwargs=run.call_args.kwargs
            self.assertEqual(kwargs['timeout'],25)
            self.assertNotIn('shell',kwargs)
            script=run.call_args.args[0][-1]
            self.assertTrue(script.startswith('set -e;'))
            for cmd in COMMANDS.values():self.assertIn(cmd,script)

    def test_successful_command_envelope(self):
        raw=fixture(time.time())
        output=''.join(f'\n__CF_{name}__\n{raw[name]}\n' for name in COMMANDS)
        with patch('backend.collector.subprocess.run',return_value=subprocess.CompletedProcess([],0,output,'')):
            self.assertEqual(collect({'username':'root','host':'192.168.1.1','identity_file':''})['router']['model'],'Meraki MX64')


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=Store(Path(self.temp.name)/'history.sqlite3')
    def tearDown(self):self.temp.cleanup()
    def test_demo_never_collects_or_persists(self):
        def forbidden(_):self.fail('Demo must not SSH')
        with TestClient(create_app({'mode':'demo','poll_seconds':60},self.db,forbidden),base_url='http://127.0.0.1:8765') as c:
            d=c.get('/api/dashboard').json()
            self.assertEqual(d['mode'],'demo');self.assertFalse(d['verified'])
            self.assertEqual(len(d['manual_nodes']),4)
            self.assertEqual(self.db.history(),[])
        with self.assertRaises(ValueError):self.db.add(sample())
    def test_http_boundaries(self):
        with TestClient(create_app({'mode':'demo','poll_seconds':60},self.db),base_url='http://127.0.0.1:8765') as c:
            self.assertEqual(c.get('/api/dashboard',headers={'host':'evil.example'}).status_code,400)
            self.assertEqual(c.get('/api/dashboard',headers={'origin':'https://evil.example'}).status_code,403)
            self.assertEqual(c.post('/api/dashboard').status_code,405)
            self.assertEqual(c.get('/docs').status_code,404)
            self.assertIn("frame-ancestors 'none'",c.get('/api/health').headers['content-security-policy'])
        with TestClient(create_app({'mode':'demo','poll_seconds':60},self.db),base_url='http://127.0.0.1:8765',client=('192.168.1.8',1234)) as c:
            self.assertEqual(c.get('/api/dashboard').status_code,403)
    def test_live_failure_stale_and_recovery(self):
        good=parse(fixture(time.time()),'192.168.1.1')
        responses=iter([good,RuntimeError('SSH authentication/read access failed'),good])
        def collector(_):
            item=next(responses)
            if isinstance(item,Exception):raise item
            return copy.deepcopy(item)
        app=create_app({'mode':'live','poll_seconds':60},self.db,collector)
        # Explicit calls avoid scheduler timing; exercise real storage and state transitions.
        asyncio.run(app.state.poll_once());self.assertTrue(app.state.collector_state['verified'])
        asyncio.run(app.state.poll_once());self.assertFalse(app.state.collector_state['verified'])
        self.assertEqual(app.state.collector_state['failures'],1)
        self.assertIsNotNone(app.state.collector_state['snapshot'])
        asyncio.run(app.state.poll_once());self.assertTrue(app.state.collector_state['verified'])
        self.assertEqual(app.state.collector_state['failures'],0)
    def test_backup_and_retention(self):
        old=parse(fixture(1000),'192.168.1.1',1000);self.db.add(old)
        self.db.add(parse(fixture(time.time()),'192.168.1.1'))
        self.assertEqual(len(self.db.history()),1)
        target=Path(self.temp.name)/'backup.sqlite3';self.db.backup(target)
        with closing(sqlite3.connect(target)) as db:self.assertEqual(db.execute('select count(*) from snapshots').fetchone()[0],1)


if __name__=='__main__':unittest.main()


class SSHErrorClassificationTests(unittest.TestCase):
    def test_classification(self):
        from backend.collector import classify_ssh_error
        cases={'ssh: connect to host 192.168.1.1 port 22: Connection timed out':'did not answer',
               'ssh: connect to host 192.168.1.1 port 22: Connection refused':'refused the SSH',
               'ssh: connect to host 192.168.1.1 port 22: Network is unreachable':'unreachable',
               'Timeout, server 192.168.1.1 not responding.':'dropped mid-read',
               'root@192.168.1.1: Permission denied (publickey).':'authentication',
               'Host key verification failed.':'Host key',
               'Warning: Identity file C:\\x\\k not accessible: No such file or directory.\nno such identity':'key file'}
        for err,expect in cases.items():self.assertIn(expect,classify_ssh_error(err,255))
        self.assertIn('before any read',classify_ssh_error('',255))
        self.assertIn('required read',classify_ssh_error('',1))

    def test_keepalive_tolerates_brief_drops(self):
        args=ssh_args({'username':'root','host':'192.168.1.1','identity_file':''})
        self.assertIn('ServerAliveCountMax=3',args)
        self.assertIn('ConnectTimeout=5',args)

    def test_raw_stderr_not_in_message(self):
        from backend.collector import SSHReadError
        with patch('backend.collector.subprocess.run') as run:
            run.return_value=subprocess.CompletedProcess([],255,'','ssh: connect to host 192.168.1.1 port 22: Connection timed out')
            with self.assertRaises(SSHReadError) as ctx:collect({'username':'root','host':'192.168.1.1','identity_file':''})
        self.assertNotIn('port 22',str(ctx.exception));self.assertIn('port 22',ctx.exception.stderr)


class SSHSerializationTests(unittest.TestCase):
    def test_reads_never_overlap(self):
        import threading as th
        from backend.collector import read_sections
        active=[0];peak=[0];guard=th.Lock()
        def fake(*a,**k):
            with guard:active[0]+=1;peak[0]=max(peak[0],active[0])
            time.sleep(0.05)
            with guard:active[0]-=1
            return subprocess.CompletedProcess([],0,'\n__CF_x__\nok\n','')
        cfg={'username':'root','host':'192.168.1.1','identity_file':''}
        with patch('backend.collector.subprocess.run',side_effect=fake):
            ts=[th.Thread(target=read_sections,args=(cfg,'s',['x'])) for _ in range(3)]
            [t.start() for t in ts];[t.join() for t in ts]
        self.assertEqual(peak[0],1)
