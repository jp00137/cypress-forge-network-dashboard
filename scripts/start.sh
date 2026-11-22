#!/bin/sh
# CF Network Dashboard: start on Linux (the Linux counterpart of start.ps1).
# If the dashboard is already running it says so (and opens the browser on a desktop);
# otherwise it serves on http://127.0.0.1:8765 in the foreground until Ctrl+C.
# Usage: ./scripts/start.sh [--no-browser]
set -eu
cd "$(dirname "$0")/.."
[ -x .venv/bin/python ] || { echo 'Run ./scripts/setup.sh first.' >&2; exit 1; }
[ -f frontend/dist/index.html ] || { echo 'Frontend missing. Run ./scripts/setup.sh first.' >&2; exit 1; }

open_browser() {
    [ "${1-}" = '--no-browser' ] && return 0
    if [ -n "${DISPLAY-}${WAYLAND_DISPLAY-}" ] && command -v xdg-open >/dev/null 2>&1; then
        xdg-open 'http://127.0.0.1:8765/' >/dev/null 2>&1 || true
    fi
}

set +e
.venv/bin/python -m backend.launcher
status=$?
set -e
if [ "$status" -eq 10 ]; then
    open_browser "${1-}"
    exit 0
fi
[ "$status" -eq 0 ] || exit "$status"

echo 'CF Network Dashboard: http://127.0.0.1:8765   (Ctrl+C to stop)'
exec .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765 --no-proxy-headers
