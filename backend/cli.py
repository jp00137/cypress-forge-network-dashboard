"""Local console controls only; never exposed through HTTP."""
import argparse
import json
import datetime
import sys
from pathlib import Path
from .collector import ROOT, SSHReadError, collect, settings
from .store import Store
from .firewall import collect_firewall
from .dhcp import collect_dhcp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['verify', 'verify-ports', 'verify-firewall', 'verify-dhcp', 'diagnose',
                                           'backup', 'router-installer', 'router-remover', 'configure', 'verify-locked'])
    parser.add_argument('--pubkey', help='public key file (router-installer/router-remover)')
    parser.add_argument('--out', help='output script path (router-installer/router-remover)')
    parser.add_argument('--host')
    parser.add_argument('--user')
    parser.add_argument('--identity-file')
    args = parser.parse_args()
    if args.action in ('router-installer', 'router-remover'):
        return write_router_script(args)
    if args.action == 'configure':
        return configure(args)
    if args.action == 'verify-locked':
        return verify_locked()
    if args.action == 'diagnose':
        return diagnose()
    if args.action in ('verify', 'verify-ports', 'verify-firewall', 'verify-dhcp'):
        try:
            cfg = settings()
            if args.action == 'verify-dhcp':
                snapshot = collect_dhcp(cfg)
                print('PASS: read-only DHCP/DNS configuration command and format verified.')
                print('Configured sections:', len(snapshot['config']))
                print('DHCP sections:', len(snapshot['pools']))
                print('Static host sections in this file:', len(snapshot['reservations']))
                print('Local DNS record sections in this file:', len(snapshot['records']))
                print('No history was written. Configuration and polling were not changed.')
                return 0
            if args.action == 'verify-firewall':
                snapshot = collect_firewall(cfg)
                print('PASS: both read-only firewall commands and response formats verified.')
                print('Configured sections:', len(snapshot['config']))
                print('Active chains:', len(snapshot['active']['chains']))
                print('Active rules:', len(snapshot['active']['rules']))
                print('No history was written. Firewall polling and configuration were not changed.')
                return 0
            if args.action == 'verify-ports':
                cfg['collect_ports'] = True
            result = collect(cfg)
            print('PASS: SSH authentication and all ' + ('seven' if cfg['collect_ports'] else 'six') + ' read commands verified.')
            print('Router model:', result['router']['model'])
            print('Observed clients:', len(result['clients']))
            if cfg['collect_ports']:
                for port in result['ports']:
                    state = 'Link' if port['carrier'] is True else 'No link' if port['carrier'] is False else 'Unknown'
                    print(f"Port {port['name']}: {state}; {port['speed_mbps'] or 'unknown'} Mbps; {port['duplex'] or 'unknown'} duplex")
            print('No history was written. Configuration and polling were not changed.')
        except Exception as exc:
            print('NOT VERIFIED:', str(exc), file=sys.stderr)
            return 1
    else:
        folder = ROOT / 'backups'
        folder.mkdir(exist_ok=True)
        target = folder / (datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.sqlite3')
        Store().backup(target)
        print('Database backup:', target)
    return 0


def write_router_script(args):
    from .router_access import installer_script, removal_script
    if not args.pubkey or not args.out:
        print('--pubkey and --out are required', file=sys.stderr)
        return 2
    try:
        text = Path(args.pubkey).read_text(encoding='utf-8')
        script = installer_script(text) if args.action == 'router-installer' else removal_script(text)
    except (OSError, ValueError) as exc:
        print('NOT CREATED:', exc, file=sys.stderr)
        return 1
    with open(args.out, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(script)
    print('Router script written:', args.out)
    return 0


def configure(args):
    """Merge connection settings into config.local.json and switch to live mode."""
    path = ROOT / 'config.local.json'
    current = json.loads(path.read_text()) if path.exists() else {}
    if path.exists():
        (ROOT / 'config.local.json.bak').write_text(path.read_text())
    current.update(mode='live', collect_ports=True, collect_firewall=True, collect_dhcp=True)
    if args.host:
        current['host'] = args.host
    if args.user:
        current['username'] = args.user
    if args.identity_file:
        current['identity_file'] = args.identity_file
    path.write_text(json.dumps(current, indent=2) + '\n')
    try:
        settings()
    except ValueError as exc:
        print('Saved, but the configuration is not valid yet:', exc, file=sys.stderr)
        return 1
    print('Saved config.local.json (live mode; previous copy in config.local.json.bak).')
    return 0


def verify_locked():
    """The collector key must refuse anything except the app's exact reads."""
    import subprocess
    from .collector import ssh_args
    cfg = settings()
    try:
        result = subprocess.run(ssh_args(cfg) + ['id'], capture_output=True, text=True, timeout=25)
    except subprocess.TimeoutExpired:
        print('NOT VERIFIED: router did not answer')
        return 1
    if result.returncode == 126 and 'command denied' in result.stderr:
        print('PASS: the collector key refuses other commands (read-only lock works).')
        return 0
    if result.returncode == 0:
        print('WARNING: the collector key ran an arbitrary command. It is NOT restricted.')
    else:
        print('NOT VERIFIED: unexpected answer (exit %s).' % result.returncode)
    return 1


def diagnose():
    """Run one collection and print the real SSH error locally. Nothing is stored."""
    cfg = settings()
    print('Target:', cfg['username'] + '@' + cfg['host'],
          '| key:', 'configured' if cfg['identity_file'] else 'default keys/agent')
    try:
        collect(cfg)
    except SSHReadError as exc:
        print('FAILED:', str(exc))
        lines = [l for l in exc.stderr.strip().splitlines() if l.strip()][-8:]
        if cfg['identity_file']:
            lines = [l.replace(cfg['identity_file'], '<identity_file>') for l in lines]
        print('SSH said:' if lines else 'SSH printed no error text (exit code only).')
        for line in lines:
            print('   ', line)
        print('Paste the lines above into chat if you want help; they contain no password or key.')
        return 1
    except Exception as exc:
        print('FAILED:', str(exc))
        return 1
    print('PASS: router answered and all required reads returned. The failure is intermittent;')
    print('check whether this PC sleeps or drops Wi-Fi when the dashboard shows failures.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
