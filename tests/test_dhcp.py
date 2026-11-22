import copy
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from backend.dhcp import collect_dhcp,dhcp_request_script,parse_dhcp
from backend.collector import parse
from backend.main import create_app
from backend.store import Store
from test_observations import inline
from test_backend import fixture

CONFIG="""config dnsmasq
 option domain 'lan'
 option rebind_protection '1'
 option readethers '1'
 option resolvfile '/tmp/resolv.conf.d/resolv.conf.auto'
config dhcp 'lan'
 option interface 'lan'
 option start '100'
 option limit '150'
 option leasetime '12h'
 option dhcpv6 'server'
 option ra 'server'
 list ra_flags 'managed-config'
 list ra_flags 'other-config'
config dhcp 'wan'
 option interface 'wan'
 option ignore '1'
config odhcpd 'odhcpd'
 option maindhcp '0'
"""


class DHCPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=Store(Path(self.temp.name)/'dhcp.sqlite3')
    def tearDown(self):self.temp.cleanup()
    def test_supplied_shape_lists_and_ignored_wan(self):
        d=parse_dhcp(CONFIG)
        self.assertEqual(len(d['config']),4);self.assertEqual(len(d['pools']),2)
        self.assertEqual(d['pools'][0]['options']['ra_flags'],['managed-config','other-config'])
        self.assertEqual(d['pools'][1]['options']['ignore'],'1')
        self.assertEqual(d['reservations'],[]);self.assertEqual(d['records'],[])
        self.assertEqual(d['dnsmasq'][0]['options']['readethers'],'1')
    def test_host_and_domain_sections_preserved_without_external_execution(self):
        text=CONFIG+"config host\n option name 'printer'\n list mac 'aa:bb:cc:dd:ee:ff'\n option ip '192.0.2.15'\nconfig domain\n option name 'nas.lan'\n option ip '192.0.2.20'\n"
        d=parse_dhcp(text)
        self.assertEqual(len(d['reservations']),1);self.assertEqual(len(d['records']),1)
        self.assertEqual(d['reservations'][0]['options']['mac'],['aa:bb:cc:dd:ee:ff'])
        with self.assertRaises(ValueError):parse_dhcp('config dnsmasq\n sh malicious-script')
    def test_fixed_one_read_request_and_no_config_changes(self):
        result=subprocess.CompletedProcess([],0,'\n__CF_dhcp_config__\n'+CONFIG,'')
        cfg={'username':'root','host':'192.168.1.1','identity_file':''}
        with patch('backend.collector.subprocess.run',return_value=result) as run:
            self.assertEqual(len(collect_dhcp(cfg)['config']),4)
            self.assertEqual(run.call_args.args[0][-1],dhcp_request_script())
        self.assertEqual(dhcp_request_script().count('cat /etc/config/dhcp'),1)
        self.assertNotIn('uci set',dhcp_request_script());self.assertNotIn('restart',dhcp_request_script())
    def test_latest_only_storage_and_change_events(self):
        a=parse_dhcp(CONFIG);self.db.save_dhcp(a);self.db.save_dhcp(a)
        self.assertEqual(len(self.db.events()),1)
        b=parse_dhcp(CONFIG.replace("'12h'","'6h'"));self.db.save_dhcp(b)
        self.assertEqual(self.db.events()[0]['kind'],'dhcp_config_changed')
        self.assertEqual(self.db.dhcp()['pools'][0]['options']['leasetime'],'6h')
        self.assertEqual(self.db.history(),[])
    def test_demo_isolation_disabled_and_stale_configuration(self):
        self.db.save_dhcp(parse_dhcp(CONFIG))
        app=create_app({'mode':'demo','poll_seconds':60},self.db)
        data=next(r.endpoint for r in app.routes if r.path=='/api/dhcp')()
        self.assertFalse(data['enabled']);self.assertIsNone(data['snapshot'])
        app=create_app({'mode':'live','poll_seconds':60},self.db)
        data=next(r.endpoint for r in app.routes if r.path=='/api/dhcp')()
        self.assertTrue(data['stale']);self.assertFalse(data['enabled']);self.assertIsNotNone(data['snapshot'])
    def test_failures_do_not_change_network_or_firewall_status(self):
        def fail(_):raise RuntimeError('Denied')
        app=create_app({'mode':'live','poll_seconds':60},self.db,dhcp_collector=fail)
        app.state.collector_state['verified']=True;app.state.firewall_state['verified']=True
        async def direct(fn,*args):return fn(*args)
        with patch('backend.main.asyncio.to_thread',direct):
            inline(app.state.poll_dhcp_once());inline(app.state.poll_dhcp_once())
        self.assertTrue(app.state.collector_state['verified']);self.assertTrue(app.state.firewall_state['verified'])
        self.assertEqual(len(self.db.events()),1)
    def test_live_lease_metadata_and_subnet_are_preserved(self):
        raw=fixture(1000);raw['interfaces']='{"interface":[{"interface":"lan","up":true,"l3_device":"br-lan","ipv4-address":[{"address":"192.168.1.1","mask":24}]}]}'
        d=parse(raw,'192.168.1.1',1000)
        self.assertEqual(d['clients'][0]['lease_expires'],2000)
        self.assertEqual(d['interfaces'][0]['ipv4'][0]['mask'],24)
        raw['leases']='0 aa:bb:cc:dd:ee:ff 192.168.1.2 laptop *'
        self.assertIsNone(parse(raw,'192.168.1.1',1000)['clients'][0]['lease_expires'])
