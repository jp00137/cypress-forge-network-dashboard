import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from backend.router_access import (REQUESTS, WRAPPER_PATH, installer_script, parse_public_key,
                                   removal_script, wrapper_script)

PUB = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFakeFakeFakeFakeFakeFakeFakeFakeFakeFakeFake test@pc'
OTHER = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOtherOtherOtherOtherOtherOtherOtherOther admin@pc'


def fake_bin(folder):
    """Stand-ins for ubus/ip/nft/cat so the gate can run off-router."""
    folder.mkdir()
    for name, body in {'ubus': 'echo "ubus $*"', 'ip': 'echo "ip $*"', 'nft': 'echo "nft $*"',
                       'cat': '[ $# -eq 0 ] && exec %s; echo "cat $*"' % shutil.which('cat')}.items():
        p = folder / name
        p.write_text('#!/bin/sh\n' + body + '\n')
        p.chmod(0o755)


class WrapperTests(unittest.TestCase):
    def run_gate(self, request):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            fake_bin(tmp / 'bin')
            gate = tmp / 'gate.sh'
            gate.write_text(wrapper_script().replace('PATH=/usr/sbin:/usr/bin:/sbin:/bin', 'PATH=%s' % (tmp / 'bin')))
            env = {'SSH_ORIGINAL_COMMAND': request} if request is not None else {}
            return subprocess.run(['/bin/sh', str(gate)], capture_output=True, text=True, env=env)

    def test_every_app_request_is_accepted_and_runs_only_fixed_commands(self):
        for label, request, commands in REQUESTS:
            result = self.run_gate(request)
            self.assertEqual(result.returncode, 0, label + result.stderr)
            for name, cmd in commands.items():
                self.assertIn('__CF_%s__' % name, result.stdout)
                self.assertIn(cmd, result.stdout)

    def test_anything_else_is_denied(self):
        base = REQUESTS[0][1]
        for request in ['id', '', None, base + '; id', base + '\n', 'sh', base.replace('board', 'boards')]:
            result = self.run_gate(request)
            self.assertEqual(result.returncode, 126, repr(request))
            self.assertIn('command denied', result.stderr)
            self.assertEqual(result.stdout, '')

    def test_gate_syntax(self):
        with tempfile.NamedTemporaryFile('w', suffix='.sh', delete=False) as fh:
            fh.write(wrapper_script())
        try:
            self.assertEqual(subprocess.run(['/bin/sh', '-n', fh.name]).returncode, 0)
        finally:
            os.unlink(fh.name)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'etc/dropbear').mkdir(parents=True)
        self.keys = self.root / 'etc/dropbear/authorized_keys'

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, text):
        return subprocess.run(['/bin/sh', '-s'], input=text, capture_output=True, text=True,
                              env={'CF_TEST_ROOT': str(self.root), 'PATH': os.environ['PATH']})

    def test_fresh_install_then_idempotent(self):
        self.keys.write_text(OTHER + '\n')
        first = self.run_script(installer_script(PUB))
        self.assertEqual(first.returncode, 0, first.stderr)
        content = self.keys.read_text()
        self.assertTrue(content.startswith(OTHER + '\n'), 'existing access must be preserved')
        self.assertIn('command="%s"' % WRAPPER_PATH, content)
        self.assertIn('no-pty', content)
        self.assertEqual(stat.S_IMODE(self.keys.stat().st_mode), 0o600)
        gate = self.root / WRAPPER_PATH.lstrip('/')
        self.assertEqual(gate.read_text(), wrapper_script())
        self.assertEqual(stat.S_IMODE(gate.stat().st_mode), 0o700)
        second = self.run_script(installer_script(PUB))
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn('already current', second.stdout)
        self.assertIn('already installed', second.stdout)
        self.assertEqual(self.keys.read_text(), content)

    def test_existing_restricted_entry_with_other_comment_counts_as_installed(self):
        from backend.router_access import KEY_OPTIONS
        line = '%s %s old comment' % (KEY_OPTIONS, ' '.join(PUB.split()[:2]))
        self.keys.write_text(line + '\n')
        result = self.run_script(installer_script(PUB))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.keys.read_text(), line + '\n')

    def test_no_authorized_keys_file_yet(self):
        result = self.run_script(installer_script(PUB))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.keys.read_text().splitlines()), 1)

    def test_upgrades_an_older_gate_with_backup(self):
        gate = self.root / WRAPPER_PATH.lstrip('/')
        gate.write_text('#!/bin/sh\nold\n')
        result = self.run_script(installer_script(PUB))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(gate.read_text(), wrapper_script())
        backups = list((self.root / 'etc/dropbear').glob('cypress-forge-backup.*/gate.before'))
        self.assertEqual(backups[0].read_text(), '#!/bin/sh\nold\n')

    def test_same_key_with_unrestricted_entry_is_not_touched(self):
        self.keys.write_text(PUB + '\n')
        result = self.run_script(installer_script(PUB))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.keys.read_text(), PUB + '\n')

    def test_removal_keeps_other_entries(self):
        self.keys.write_text(OTHER + '\n')
        self.run_script(installer_script(PUB))
        result = self.run_script(removal_script(PUB))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.keys.read_text(), OTHER + '\n')

    def test_rejects_bad_keys(self):
        for bad in ['', 'ssh-rsa AAAAB3Nza x', PUB + '\n' + OTHER, "ssh-ed25519 AAAA' ; rm -rf /"]:
            with self.assertRaises(ValueError):
                installer_script(bad)
        self.assertEqual(parse_public_key(PUB + '\n')[0], 'ssh-ed25519')
