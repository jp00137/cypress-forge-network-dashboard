"""Fixed read-only OpenWrt commands over the PC's OpenSSH client. No shell locally."""
import ipaddress
import json
import re
import subprocess
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = {
    'board': 'ubus call system board',
    'system': 'ubus call system info',
    'interfaces': 'ubus call network.interface dump',
    'leases': 'cat /tmp/dhcp.leases',
    'neighbors': 'ip -4 neigh show',
    'counters': 'cat /proc/net/dev',
}
PORT_COMMANDS = {**COMMANDS, 'devices': 'ubus call network.device status'}


def request_script(include_ports=False):
    commands = PORT_COMMANDS if include_ports else COMMANDS
    return 'set -e; ' + '; '.join(
        "printf '\\n__CF_%s__\\n'; %s" % (name, cmd) for name, cmd in commands.items())


def settings():
    path = ROOT / 'config.local.json'
    cfg = json.loads(path.read_text()) if path.exists() else {}
    cfg = {'mode': 'demo', 'host': '192.168.1.1', 'username': 'root',
           'identity_file': '', 'poll_seconds': 60, 'retention_days': 7, 'collect_ports': False,
           'collect_firewall': False, 'firewall_seconds': 300,
           'collect_dhcp': False, 'dhcp_seconds': 300, **cfg}
    if cfg['mode'] not in ('demo', 'live'):
        raise ValueError('mode must be demo or live')
    if not ipaddress.ip_address(cfg['host']).is_private:
        raise ValueError('Use a private router IP')
    if not re.fullmatch(r'[a-zA-Z0-9_][a-zA-Z0-9_-]{0,31}', cfg['username']):
        raise ValueError('Invalid SSH username')
    cfg['poll_seconds'] = max(60, min(900, int(cfg['poll_seconds'])))
    cfg['retention_days'] = max(1, min(90, int(cfg['retention_days'])))
    if not isinstance(cfg['collect_ports'], bool):
        raise ValueError('collect_ports must be true or false')
    if not isinstance(cfg['collect_firewall'], bool):
        raise ValueError('collect_firewall must be true or false')
    cfg['firewall_seconds'] = max(300, min(3600, int(cfg['firewall_seconds'])))
    if not isinstance(cfg['collect_dhcp'], bool):
        raise ValueError('collect_dhcp must be true or false')
    cfg['dhcp_seconds'] = max(300, min(3600, int(cfg['dhcp_seconds'])))
    if cfg['identity_file'] and not Path(cfg['identity_file']).is_file():
        raise ValueError('SSH key file does not exist')
    return cfg



class SSHReadError(RuntimeError):
    """Collection failure with a safe summary; raw stderr stays local (CLI diagnose only)."""
    def __init__(self, reason, stderr=''):
        super().__init__(reason)
        self.stderr = stderr or ''


# Ordered: first match wins. Messages are safe to show in the UI and history.
SSH_ERROR_PATTERNS = [
    (('host key verification failed', 'remote host identification has changed', 'host key for'),
     'Host key is unknown or changed; verify it locally'),
    (('permission denied',), 'SSH authentication/read access failed'),
    (('no such identity', 'load key', 'bad permissions', 'unprotected private key'),
     'SSH key file could not be used; check identity_file in config.local.json'),
    (('connection timed out', 'operation timed out', 'timed out during banner'),
     'Router did not answer in time; check that this PC is on the network'),
    (('connection refused',), 'Router refused the SSH connection; SSH service may be down'),
    (('no route to host', 'network is unreachable', 'could not resolve hostname'),
     'Router is unreachable from this PC; check Wi-Fi/Ethernet or sleep'),
    (('timeout, server', 'not responding', 'broken pipe', 'connection reset', 'closed by remote host',
      'connection closed'),
     'SSH session dropped mid-read; network link was interrupted'),
    (('not allowed', 'denied by cypress', 'unsupported request', 'refused request'),
     'Router wrapper rejected the read; check the restricted collector wrapper version'),
]


def classify_ssh_error(stderr, returncode=None):
    err = (stderr or '').lower()
    for needles, reason in SSH_ERROR_PATTERNS:
        if any(n in err for n in needles):
            return reason
    if returncode == 255:
        return 'SSH connection failed before any read ran'
    return 'SSH connection or required read command failed'

def ssh_args(cfg):
    args = ['ssh', '-F', 'NUL' if __import__('os').name == 'nt' else '/dev/null',
            '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'ConnectTimeout=5', '-o', 'ConnectionAttempts=1',
            '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=3',
            '-o', 'ForwardAgent=no', '-o', 'ClearAllForwardings=yes']
    if cfg['identity_file']:
        args += ['-o', 'IdentitiesOnly=yes', '-i', cfg['identity_file']]
    return args + [cfg['username'] + '@' + cfg['host']]


def collect(cfg):
    # Exit on a denied/missing read: never treat partial collection as verified.
    script = request_script(cfg.get('collect_ports', False))
    required = PORT_COMMANDS if cfg.get('collect_ports') else COMMANDS
    return parse(read_sections(cfg, script, required), cfg['host'])


# One SSH session to the router at a time: overlapping startup reads
# (status, firewall, DHCP) timed out on a real OpenWrt MX64.
SSH_LOCK = threading.Lock()


def read_sections(cfg, script, required, max_chars=4_000_000):
    try:
        with SSH_LOCK:
            result = subprocess.run(ssh_args(cfg) + [script], capture_output=True,
                                    text=True, timeout=25, encoding='utf-8', errors='replace')
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('SSH timed out; collection paused') from exc
    if result.returncode:
        # Do not store command output or credential paths in the API/history.
        raise SSHReadError(classify_ssh_error(result.stderr, result.returncode), result.stderr)
    if len(result.stdout) > max_chars:
        raise RuntimeError('Router output exceeded limit')
    parts = re.split(r'\n__CF_(\w+)__\r?\n', result.stdout)
    raw = dict(zip(parts[1::2], parts[2::2]))
    if not all(name in raw for name in required):
        raise RuntimeError('Required response section missing; check the restricted collector wrapper')
    return raw


def parse_ports(raw):
    devices = json.loads(raw)
    if not isinstance(devices, dict) or any(not isinstance(v, dict) for v in devices.values()):
        raise ValueError('Unexpected device-status response')
    bridges = {member: name for name, row in devices.items()
               if row.get('type') == 'bridge' for member in row.get('bridge-members', [])}
    ports = []
    for name, row in devices.items():
        # MX64 DSA external ports only. eth0 is the CPU conduit, not a sixth socket.
        if row.get('devtype') != 'dsa':
            continue
        boolean = lambda key: row.get(key) if isinstance(row.get(key), bool) else None
        carrier = boolean('carrier')
        speed = re.fullmatch(r'(\d+)([FH])', str(row.get('speed', ''))) if carrier is True else None
        stats = row.get('statistics', {})
        if not isinstance(stats, dict):
            raise ValueError('Unexpected port statistics')
        keys = {'rx': 'rx_bytes', 'tx': 'tx_bytes', 'rx_errors': 'rx_errors',
                'tx_errors': 'tx_errors', 'rx_dropped': 'rx_dropped', 'tx_dropped': 'tx_dropped'}
        counters = {key: stats[source] for key, source in keys.items()
                    if type(stats.get(source)) is int and stats[source] >= 0}
        ports.append(dict(name=name, present=boolean('present'), up=boolean('up'), carrier=carrier,
            speed_mbps=int(speed[1]) if speed else None,
            duplex=('Full' if speed[2] == 'F' else 'Half') if speed else None,
            autoneg=boolean('autoneg'), bridge=bridges.get(name), conduit=row.get('conduit'),
            counters=counters, rx_mbps=None, tx_mbps=None))
    return sorted(ports, key=lambda p: p['name'])


def parse(raw, host, now=None):
    now = now or time.time()
    board, system, interfaces = (json.loads(raw[k]) for k in ('board', 'system', 'interfaces'))
    if not isinstance(board, dict) or not board.get('model') or not isinstance(system.get('uptime'), (int, float)):
        raise ValueError('Unexpected system read response')
    if not isinstance(interfaces.get('interface'), list):
        raise ValueError('Unexpected interface response')
    clients = {}
    for line in raw['leases'].splitlines():
        fields = line.split()
        if len(fields) < 4:
            continue
        expiry, mac, ip, name = fields[:4]
        if not expiry.isdigit() or (int(expiry) != 0 and int(expiry) < now):
            continue
        clients[mac.lower()] = dict(id=mac.lower(), name=name if name != '*' else ip,
            ip=ip, mac=mac.lower(), source='DHCP lease', state='Lease only', evidence='confirmed',
            lease_expires=int(expiry) or None)
    for line in raw['neighbors'].splitlines():
        fields = line.split()
        if 'lladdr' not in fields:
            continue
        mac = fields[fields.index('lladdr') + 1].lower()
        row = clients.setdefault(mac, dict(id=mac, name=fields[0], ip=fields[0], mac=mac, evidence='confirmed'))
        row.update(source='Neighbor table' + (' + DHCP' if row.get('source') == 'DHCP lease' else ''), state=fields[-1])
    counters = {}
    for line in raw['counters'].splitlines():
        if ':' not in line:
            continue
        name, values = line.split(':', 1)
        v = values.split()
        if len(v) >= 16:
            counters[name.strip()] = {'rx': int(v[0]), 'tx': int(v[8]),
                'rx_errors': int(v[2]), 'rx_dropped': int(v[3]),
                'tx_errors': int(v[10]), 'tx_dropped': int(v[11])}
    memory = system.get('memory', {})
    total, available = memory.get('total', 0), memory.get('available', memory.get('free', 0))
    return dict(timestamp=now, mode='live', router=dict(name=board.get('hostname', 'MX64'),
        model=board['model'], ip=host, release=board.get('release', {}).get('version', 'Unknown'),
        uptime=system['uptime'], load=round((system.get('load') or [0])[0] / 65536, 2),
        memory=round(100 * (total - available) / total, 1) if total else None),
        interfaces=[dict(name=x.get('interface'), device=x.get('l3_device', x.get('device', '—')),
                         up=x.get('up', False), addresses=[a['address'] for a in x.get('ipv4-address', [])],
                         counters=counters.get(x.get('l3_device', x.get('device')), {}),
                         ipv4=x.get('ipv4-address', []))
                    for x in interfaces['interface']], clients=list(clients.values()),
        rx_mbps=None, tx_mbps=None,
        ports=parse_ports(raw['devices']) if 'devices' in raw else [])


def sample():
    return dict(timestamp=time.time(), mode='demo', router=dict(name='Cypress MX64', model='Cisco Meraki MX64 · OpenWrt',
        ip='192.168.1.1', release='Sample only', uptime=183462, load=0.18, memory=34.2),
        interfaces=[dict(name='wan', device='eth0', up=True, addresses=['192.0.2.2'], counters={}),
                    dict(name='lan', device='br-lan', up=True, addresses=['192.168.1.1'], counters={})],
        clients=[dict(id=str(i), name=n, ip=f'192.168.1.{i+110}', mac=f'02:00:00:00:00:{i:02x}',
            source='Sample fixture', state='Sample', evidence='sample')
            for i, n in enumerate(['Workstation', 'Living room TV', 'Mobile device', 'Home office', 'Smart speaker', 'Tablet'])],
        rx_mbps=24.8, tx_mbps=3.6)
