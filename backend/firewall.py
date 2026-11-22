"""Committed configuration and active nftables reads. No apply/reload operations."""
import hashlib
import json
import time
from .collector import read_sections
from .uci import parse_uci as parse_config

FIREWALL_COMMANDS = {'firewall_config': 'cat /etc/config/firewall',
                     'firewall_active': 'nft -j -a list ruleset'}


def firewall_request_script():
    return 'set -e; ' + '; '.join("printf '\\n__CF_%s__\\n'; %s" % (name, cmd) for name, cmd in FIREWALL_COMMANDS.items())


def parse_active(text):
    raw = json.loads(text)
    if not isinstance(raw, dict) or not isinstance(raw.get('nftables'), list):
        raise ValueError('Expected nftables JSON ruleset; nft -j support is required')
    rules, chains, objects, positions = [], [], [], {}
    for item in raw['nftables']:
        if not isinstance(item, dict):
            raise ValueError('Unexpected nftables entry')
        if 'chain' in item:
            chain = item['chain']
            if not isinstance(chain, dict) or not all(k in chain for k in ('family', 'table', 'name')):
                raise ValueError('Unexpected chain entry')
            chains.append(chain)
        elif 'rule' in item:
            rule = item['rule']
            if not isinstance(rule, dict) or not all(k in rule for k in ('family', 'table', 'chain')) or not isinstance(rule.get('expr'), list):
                raise ValueError('Unexpected rule entry')
            key = (rule['family'], rule['table'], rule['chain'])
            positions[key] = positions.get(key, 0) + 1
            packets = byte_count = None
            actions, unknown = [], []
            known = ('match', 'counter', 'log', 'accept', 'drop', 'reject', 'return', 'jump', 'goto', 'dnat', 'snat', 'masquerade', 'redirect', 'queue', 'continue')
            for expression in rule['expr']:
                if not isinstance(expression, dict):
                    raise ValueError('Unexpected rule expression')
                if 'counter' in expression and isinstance(expression['counter'], dict):
                    counter = expression['counter']
                    if type(counter.get('packets')) is int:
                        packets = counter['packets']
                    if type(counter.get('bytes')) is int:
                        byte_count = counter['bytes']
                for action in known[3:]:
                    if action in expression:
                        actions.append(action.upper() + (': ' + json.dumps(expression[action], ensure_ascii=False) if expression[action] is not None else ''))
                unknown.extend(k for k in expression if k not in known)
            rules.append({**rule, 'order': positions[key], 'packets': packets, 'bytes': byte_count,
                          'actions': actions, 'unfamiliar_expressions': unknown})
        elif 'metainfo' not in item:
            objects.append(item)
    return dict(rules=rules, chains=chains, objects=objects, raw=raw)


def structure_hash(raw):
    def clean(value):
        if isinstance(value, list):
            return [clean(v) for v in value if not (isinstance(v, dict) and 'metainfo' in v)]
        if isinstance(value, dict):
            result = {}
            for key, child in value.items():
                if key == 'handle':
                    continue
                if key == 'counter' and isinstance(child, dict):
                    result[key] = {k: clean(v) for k, v in child.items() if k not in ('packets', 'bytes')}
                else:
                    result[key] = clean(child)
            return result
        return value
    return hashlib.sha256(json.dumps(clean(raw), sort_keys=True).encode()).hexdigest()


def collect_firewall(cfg):
    sections = read_sections(cfg, firewall_request_script(), FIREWALL_COMMANDS, max_chars=2_000_000)
    config = parse_config(sections['firewall_config'])
    active = parse_active(sections['firewall_active'])
    return dict(timestamp=time.time(), config=config, active=active, config_raw=sections['firewall_config'],
                config_hash=hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
                active_hash=structure_hash(active['raw']))
