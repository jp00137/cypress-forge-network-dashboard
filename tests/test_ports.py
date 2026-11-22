import copy
import json
import subprocess
import unittest
from unittest.mock import patch
from backend.collector import COMMANDS, PORT_COMMANDS, collect, parse, parse_ports, request_script
from backend.observations import changes
from backend.store import rates
from test_backend import fixture


def devices():
    def port(link, **extra):
        return dict(devtype='dsa',present=True,up=True,carrier=link,speed='1000F',autoneg=True,
            conduit='eth0',statistics={'rx_bytes':100,'tx_bytes':200,'rx_errors':0,'tx_errors':0,'rx_dropped':0,'tx_dropped':0},**extra)
    return {'br-lan':{'type':'bridge','speed':'1000F','bridge-members':['lan1','lan2','lan3','lan4']},
        'eth0':{'devtype':'ethernet','speed':'1000F','carrier':True},
        'lan1':port(False),'lan2':port(False),'lan3':port(True),'lan4':port(True),'wan':port(True)}


class PortTests(unittest.TestCase):
    def test_only_five_external_ports_and_bridge_membership(self):
        ports=parse_ports(json.dumps(devices()))
        self.assertEqual([p['name'] for p in ports],['lan1','lan2','lan3','lan4','wan'])
        self.assertEqual(ports[3]['bridge'],'br-lan');self.assertIsNone(ports[4]['bridge'])
        self.assertEqual(ports[3]['speed_mbps'],1000);self.assertEqual(ports[3]['duplex'],'Full')

    def test_no_carrier_is_not_administrative_down_or_speed(self):
        p=parse_ports(json.dumps(devices()))[0]
        self.assertTrue(p['up']);self.assertFalse(p['carrier']);self.assertIsNone(p['speed_mbps']);self.assertIsNone(p['duplex'])

    def test_missing_and_unknown_speed_preserved(self):
        raw=devices();del raw['lan3']['carrier'];raw['lan4']['speed']='unknown'
        ports=parse_ports(json.dumps(raw))
        self.assertIsNone(ports[2]['carrier']);self.assertIsNone(ports[2]['speed_mbps']);self.assertIsNone(ports[3]['speed_mbps'])
        with self.assertRaises(ValueError):parse_ports('[]')
        raw['lan4']['statistics']=[]
        with self.assertRaises(ValueError):parse_ports(json.dumps(raw))

    def test_six_read_compatibility_and_seven_read_response(self):
        raw=fixture(1000);self.assertEqual(parse(raw,'192.168.1.1',1000)['ports'],[])
        raw['devices']=json.dumps(devices())
        self.assertEqual(len(parse(raw,'192.168.1.1',1000)['ports']),5)
        self.assertNotIn('network.device status',request_script())
        self.assertEqual(request_script(True).count('ubus call network.device status'),1)
        output=''.join(f'\n__CF_{k}__\n{raw[k]}\n' for k in PORT_COMMANDS)
        cfg={'username':'root','host':'192.168.1.1','identity_file':'','collect_ports':True}
        with patch('backend.collector.subprocess.run',return_value=subprocess.CompletedProcess([],0,output,'')):
            self.assertEqual(len(collect(cfg)['ports']),5)
        output=''.join(f'\n__CF_{k}__\n{raw[k]}\n' for k in COMMANDS)
        with patch('backend.collector.subprocess.run',return_value=subprocess.CompletedProcess([],0,output,'')):
            with self.assertRaisesRegex(RuntimeError,'section missing'):collect(cfg)

    def test_rates_require_two_linked_samples_and_handle_reset(self):
        raw=fixture(1000);raw['devices']=json.dumps(devices());a=parse(raw,'192.168.1.1',1000);b=copy.deepcopy(a)
        b['timestamp']+=60;b['router']['uptime']+=60;b['ports'][3]['counters']['rx']+=7_500_000
        rates(b,a);self.assertEqual(b['ports'][3]['rx_mbps'],1)
        b['ports'][3]['rx_mbps']=None;b['ports'][3]['counters']['rx']=0
        rates(b,a);self.assertIsNone(b['ports'][3]['rx_mbps'])
        b['ports'][3]['counters']['rx']=99_999_999;b['ports'][3]['carrier']=False
        rates(b,a);self.assertIsNone(b['ports'][3]['rx_mbps'])
        b['ports'][3]['carrier']=True;b['router']['uptime']=1
        rates(b,a);self.assertIsNone(b['ports'][3]['rx_mbps'])

    def test_port_changes_only_when_prior_evidence_exists(self):
        raw=fixture(1000);raw['devices']=json.dumps(devices());a=parse(raw,'192.168.1.1',1000);b=copy.deepcopy(a)
        b['ports'][3]['speed_mbps']=100;b['ports'][3]['counters']['rx_dropped']=3;b['ports'][2]['carrier']=False
        kinds={e['kind'] for e in changes(a,b)}
        self.assertTrue({'port_speed_changed','port_errors','port_link_down'}<=kinds)
        a.pop('ports');self.assertFalse(any(e['kind'].startswith('port_') for e in changes(a,b)))
