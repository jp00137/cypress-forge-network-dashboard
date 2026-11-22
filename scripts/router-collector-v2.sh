#!/bin/sh
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
REQUEST_SIX=$(cat <<'CF_REQUEST_SIX'
set -e; printf '\n__CF_board__\n'; ubus call system board; printf '\n__CF_system__\n'; ubus call system info; printf '\n__CF_interfaces__\n'; ubus call network.interface dump; printf '\n__CF_leases__\n'; cat /tmp/dhcp.leases; printf '\n__CF_neighbors__\n'; ip -4 neigh show; printf '\n__CF_counters__\n'; cat /proc/net/dev
CF_REQUEST_SIX
)
REQUEST_SEVEN=$(cat <<'CF_REQUEST_SEVEN'
set -e; printf '\n__CF_board__\n'; ubus call system board; printf '\n__CF_system__\n'; ubus call system info; printf '\n__CF_interfaces__\n'; ubus call network.interface dump; printf '\n__CF_leases__\n'; cat /tmp/dhcp.leases; printf '\n__CF_neighbors__\n'; ip -4 neigh show; printf '\n__CF_counters__\n'; cat /proc/net/dev; printf '\n__CF_devices__\n'; ubus call network.device status
CF_REQUEST_SEVEN
)
case "${SSH_ORIGINAL_COMMAND-}" in
    "$REQUEST_SIX") COLLECT_PORTS=0 ;;
    "$REQUEST_SEVEN") COLLECT_PORTS=1 ;;
    *) printf '%s\n' 'Cypress Forge: command denied (read-only collector key).' >&2; exit 126 ;;
esac
printf '\n__CF_board__\n'
ubus call system board
printf '\n__CF_system__\n'
ubus call system info
printf '\n__CF_interfaces__\n'
ubus call network.interface dump
printf '\n__CF_leases__\n'
cat /tmp/dhcp.leases
printf '\n__CF_neighbors__\n'
ip -4 neigh show
printf '\n__CF_counters__\n'
cat /proc/net/dev
if [ "$COLLECT_PORTS" = 1 ]; then
    printf '\n__CF_devices__\n'
    ubus call network.device status
fi
