#!/bin/sh
# CF Network Dashboard: remove the background service installed by install-service.sh.
# Your data (data/), settings (config.local.json) and router access are not touched.
set -eu
UNIT=cf-network-dashboard.service
DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
if [ -f "$DIR/$UNIT" ]; then
    systemctl --user disable --now "$UNIT" 2>/dev/null || true
    rm -f "$DIR/$UNIT"
    systemctl --user daemon-reload
    echo 'Service removed. Start the dashboard by hand with ./scripts/start.sh'
else
    echo 'No CF Network Dashboard service is installed.'
fi
echo 'If you enabled linger only for this, you can turn it off with:  sudo loginctl disable-linger '"$(id -un)"
