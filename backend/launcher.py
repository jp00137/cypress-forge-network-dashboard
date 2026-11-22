"""Identify the fixed local listener before attempting to start another server."""
import json
import socket
import urllib.request

URL = 'http://127.0.0.1:8765'


def listener_status():
    try:
        with socket.create_connection(('127.0.0.1', 8765), timeout=5):
            pass
    except ConnectionRefusedError:
        return 'free'
    except OSError:
        return 'unknown'
    # Ignore HTTP proxy settings and never follow a redirect away from localhost.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(URL + '/api/health', timeout=5) as response:
            health = json.loads(response.read(8193))
        with opener.open(URL + '/', timeout=5) as response:
            page = response.read(16384).decode('utf-8')
        if (health.get('service') == 'ok' and health.get('mode') in ('live', 'demo')
                and isinstance(health.get('verified'), bool)
                and ('<title>CF Network Dashboard' in page or '<title>Cypress Forge' in page)):
            return 'running'
    except (OSError, ValueError, AttributeError, UnicodeError):
        pass
    return 'occupied'


def main():
    status = listener_status()
    if status == 'free':
        return 0
    if status == 'running':
        print('CF Network Dashboard is already running: ' + URL)
        print('Use its original server window to stop or restart it. Router verification is shown in the dashboard.')
        return 10
    print('Port 8765 is occupied or could not be checked. No process was stopped.')
    print('Check the existing application before starting CF Network Dashboard again.')
    return 20


if __name__ == '__main__':
    raise SystemExit(main())
