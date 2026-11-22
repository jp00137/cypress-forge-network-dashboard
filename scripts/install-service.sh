#!/bin/sh
# CF Network Dashboard: run as a background service on Linux (systemd user service, optional).
# The dashboard then starts at login (or at boot with "linger"), restarts if it stops, and needs no
# terminal window. It still listens on 127.0.0.1:8765 only. Undo with ./scripts/uninstall-service.sh.
set -eu
cd "$(dirname "$0")/.."
ROOT=$(pwd)
UNIT=cf-network-dashboard.service
DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

[ -x .venv/bin/python ] || { echo 'Run ./scripts/setup.sh first.' >&2; exit 1; }
[ -f frontend/dist/index.html ] || { echo 'Frontend missing. Run ./scripts/setup.sh first.' >&2; exit 1; }
command -v systemctl >/dev/null 2>&1 || { echo 'systemd was not found; run ./scripts/start.sh instead.' >&2; exit 1; }

if .venv/bin/python -m backend.launcher >/dev/null 2>&1; then :; else
    if [ $? -eq 10 ] && ! systemctl --user is-active --quiet "$UNIT"; then
        echo 'A dashboard is already running on port 8765 (probably ./scripts/start.sh). Stop it first (Ctrl+C), then re-run this.' >&2
        exit 1
    fi
fi

mkdir -p "$DIR"
cat > "$DIR/$UNIT" <<EOF
[Unit]
Description=CF Network Dashboard (local, read-only OpenWrt dashboard on 127.0.0.1:8765)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
ExecStart=$ROOT/.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765 --no-proxy-headers
Restart=on-failure
RestartSec=10
NoNewPrivileges=yes

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable "$UNIT"
systemctl --user restart "$UNIT"
sleep 2
if systemctl --user is-active --quiet "$UNIT"; then
    echo "Running: http://127.0.0.1:8765   (logs: journalctl --user -u $UNIT -f)"
else
    echo "The service did not start. See: journalctl --user -u $UNIT -n 50" >&2
    exit 1
fi

if [ "$(loginctl show-user "$(id -un)" -p Linger --value 2>/dev/null)" != 'yes' ]; then
    echo
    echo 'Optional: to keep it running after you log out and start it at boot, run once:'
    echo "    sudo loginctl enable-linger $(id -un)"
fi
