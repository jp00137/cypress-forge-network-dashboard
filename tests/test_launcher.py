import io
import unittest
from unittest.mock import MagicMock, patch
from backend.launcher import listener_status


class LauncherTests(unittest.TestCase):
    @patch('backend.launcher.socket.create_connection', side_effect=ConnectionRefusedError)
    def test_free_port(self, connect):
        self.assertEqual(listener_status(), 'free')
        connect.assert_called_once_with(('127.0.0.1', 8765), timeout=5)

    @patch('backend.launcher.socket.create_connection', side_effect=TimeoutError)
    def test_unknown_is_not_treated_as_free(self, connect):
        self.assertEqual(listener_status(), 'unknown')

    def check_listener(self, health, page):
        opener = MagicMock()
        opener.open.side_effect = [io.BytesIO(health), io.BytesIO(page)]
        with patch('backend.launcher.socket.create_connection'), patch('backend.launcher.urllib.request.build_opener', return_value=opener):
            return listener_status()

    def test_app_identification_does_not_require_live_router(self):
        self.assertEqual(self.check_listener(b'{"service":"ok","mode":"live","verified":false}', b'<title>Cypress Forge Observatory</title>'), 'running')

    def test_unrelated_service_is_not_reopened(self):
        self.assertEqual(self.check_listener(b'{"service":"ok","mode":"live","verified":true}', b'<title>Another app</title>'), 'occupied')
        self.assertEqual(self.check_listener(b'not json', b'<title>Cypress Forge</title>'), 'occupied')
        self.assertEqual(self.check_listener(b'[]', b'<title>Cypress Forge</title>'), 'occupied')

    @patch('backend.launcher.socket.create_connection')
    @patch('backend.launcher.urllib.request.build_opener')
    def test_http_failure_does_not_start_second_server(self, build, connect):
        build.return_value.open.side_effect = OSError('not available')
        self.assertEqual(listener_status(), 'occupied')
