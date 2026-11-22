import copy
import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from backend.firewall import parse_config,parse_active,structure_hash,collect_firewall,firewall_request_script
from backend.main import create_app
from backend.store import Store
from test_observations import inline

CONFIG="""# Committed test config
config defaults
 option input 'REJECT'
 option output 'ACCEPT'
config zone
 option name 'lan'
 list network 'lan'
 list network 'guest'
 option input 'ACCEPT'
config rule 'https'
 option name 'Allow HTTPS'
 option proto 'tcp'
 option src 'lan'
 option dest 'wan'
 option dest_port '443'
 option target 'ACCEPT'
 option enabled '0'
config redirect
 option src_dport '8443'
 option dest_ip '192.0.2.10'
 option dest_port '443'
config include
 option path '/etc/custom-firewall.nft'
"""


def active():
    return {'nftables':[{'metainfo':{'version':'test'}},
        {'chain':{'family':'inet','table':'fw4','name':'forward','hook':'forward','policy':'drop','prio':0}},
        {'set':{'family':'inet','table':'fw4','name':'test_set','type':'ipv4_addr'}},
        {'rule':{'family':'inet','table':'fw4','chain':'forward','handle':12,'comment':'test rule',
            'expr':[{'match':{'op':'==','left':{'payload':{'protocol':'tcp','field':'dport'}},'right':443}},
                    {'counter':{'packets':2,'bytes':150}},{'accept':None}]}},
        {'rule':{'family':'inet','table':'fw4','chain':'forward','handle':14,'expr':[{'mangle':{'key':{'meta':{'key':'mark'}},'value':1}},{'jump':{'target':'custom'}}]}}]}


def snapshot():
    raw=active()
    return dict(timestamp=time.time(),config=parse_config(CONFIG),config_raw=CONFIG,active=parse_active(json.dumps(raw)),config_hash='config-a',active_hash=structure_hash(raw))


class FirewallTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=Store(Path(self.temp.name)/'fw.sqlite3')
    def tearDown(self):self.temp.cleanup()
    def test_config_order_lists_disabled_and_include_reference(self):
        rows=parse_config(CONFIG)
        self.assertEqual([r['type'] for r in rows],['defaults','zone','rule','redirect','include'])
        self.assertEqual(rows[1]['options']['network'],['lan','guest'])
        self.assertFalse(rows[2]['enabled']);self.assertEqual(rows[2]['name'],'https')
        self.assertEqual(rows[-1]['options']['path'],'/etc/custom-firewall.nft')
        with self.assertRaises(ValueError):parse_config('config defaults\n arbitrary shell command')
        with self.assertRaises(ValueError):parse_config('config rule\n option name "unterminated')
    def test_runtime_order_counters_and_unknown_expressions_preserved(self):
        result=parse_active(json.dumps(active()))
        self.assertEqual(result['rules'][0]['packets'],2)
        self.assertEqual(result['rules'][0]['actions'],['ACCEPT'])
        self.assertEqual(result['rules'][1]['order'],2)
        self.assertIsNone(result['rules'][1]['packets'])
        self.assertIn('mangle',result['rules'][1]['unfamiliar_expressions'])
        self.assertEqual(result['chains'][0]['policy'],'drop')
        self.assertEqual(result['objects'][0]['set']['name'],'test_set')
        with self.assertRaises(ValueError):parse_active('{}')
    def test_structure_hash_ignores_traffic_counters_handles_and_metainfo(self):
        a=active();b=copy.deepcopy(a)
        b['nftables'][0]['metainfo']['version']='new';b['nftables'][3]['rule']['handle']=999
        b['nftables'][3]['rule']['expr'][1]['counter']['packets']=100000
        self.assertEqual(structure_hash(a),structure_hash(b))
        b['nftables'][3]['rule']['expr'][-1]={'drop':None}
        self.assertNotEqual(structure_hash(a),structure_hash(b))
    def test_fixed_two_read_envelope_and_no_commands_are_executed_from_config(self):
        output=f'\n__CF_firewall_config__\n{CONFIG}\n__CF_firewall_active__\n{json.dumps(active())}'
        cfg={'username':'root','host':'192.168.1.1','identity_file':''}
        with patch('backend.collector.subprocess.run',return_value=subprocess.CompletedProcess([],0,output,'')) as run:
            result=collect_firewall(cfg)
            self.assertEqual(len(result['active']['rules']),2)
            self.assertEqual(run.call_args.args[0][-1],firewall_request_script())
            self.assertNotIn('shell',run.call_args.kwargs)
        self.assertNotIn('reload',firewall_request_script());self.assertNotIn('uci set',firewall_request_script())
    def test_firewall_storage_latest_only_and_change_events(self):
        a=snapshot();self.db.save_firewall(a);self.db.save_firewall(a)
        self.assertEqual(len(self.db.events()),1)
        b=copy.deepcopy(a);b['config_hash']='config-b';self.db.save_firewall(b)
        self.assertEqual(self.db.firewall()['config_hash'],'config-b')
        self.assertEqual(self.db.events()[0]['kind'],'firewall_config_changed')
        self.assertEqual(self.db.history(),[]) # full firewall blobs never enter network history
    def test_failed_firewall_reads_do_not_change_network_collector_state(self):
        def fail(_):raise RuntimeError('Denied')
        app=create_app({'mode':'live','poll_seconds':60,'collect_firewall':True},self.db,firewall_collector=fail)
        app.state.collector_state['verified']=True
        async def direct(fn,*args):return fn(*args)
        with patch('backend.main.asyncio.to_thread',direct):inline(app.state.poll_firewall_once())
        self.assertTrue(app.state.collector_state['verified']);self.assertFalse(app.state.firewall_state['verified'])
    def test_cached_endpoint_disabled_demo_and_stale_are_explicit(self):
        self.db.save_firewall(snapshot())
        app=create_app({'mode':'demo','poll_seconds':60},self.db)
        result=next(r.endpoint for r in app.routes if r.path=='/api/firewall')()
        self.assertIsNone(result['snapshot']);self.assertFalse(result['enabled'])
        app=create_app({'mode':'live','poll_seconds':60,'collect_firewall':False},self.db)
        result=next(r.endpoint for r in app.routes if r.path=='/api/firewall')()
        self.assertTrue(result['stale']);self.assertFalse(result['enabled']);self.assertIsNotNone(result['snapshot'])
