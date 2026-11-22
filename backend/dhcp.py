"""One fixed committed DHCP/DNS configuration read. No service/configuration changes."""
import hashlib
import json
import time
from .collector import read_sections
from .uci import parse_uci

DHCP_COMMANDS = {'dhcp_config': 'cat /etc/config/dhcp'}


def dhcp_request_script():
    return "set -e; printf '\\n__CF_dhcp_config__\\n'; cat /etc/config/dhcp"


def parse_dhcp(text, now=None):
    config = parse_uci(text)
    return dict(timestamp=now or time.time(), config=config, config_raw=text,
                dnsmasq=[s for s in config if s['type'] == 'dnsmasq'],
                pools=[s for s in config if s['type'] == 'dhcp'],
                reservations=[s for s in config if s['type'] == 'host'],
                records=[s for s in config if s['type'] in ('domain', 'cname')],
                odhcpd=[s for s in config if s['type'] == 'odhcpd'],
                config_hash=hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest())


def collect_dhcp(cfg):
    raw = read_sections(cfg, dhcp_request_script(), DHCP_COMMANDS, max_chars=500_000)
    return parse_dhcp(raw['dhcp_config'])
