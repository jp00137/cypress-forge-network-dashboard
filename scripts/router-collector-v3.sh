#!/bin/sh
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
REQUEST_SIX=$(cat <<'CF_SIX'
set -e; printf '\n__CF_board__\n'; ubus call system board; printf '\n__CF_system__\n'; ubus call system info; printf '\n__CF_interfaces__\n'; ubus call network.interface dump; printf '\n__CF_leases__\n'; cat /tmp/dhcp.leases; printf '\n__CF_neighbors__\n'; ip -4 neigh show; printf '\n__CF_counters__\n'; cat /proc/net/dev
CF_SIX
)
REQUEST_SEVEN=$(cat <<'CF_SEVEN'
set -e; printf '\n__CF_board__\n'; ubus call system board; printf '\n__CF_system__\n'; ubus call system info; printf '\n__CF_interfaces__\n'; ubus call network.interface dump; printf '\n__CF_leases__\n'; cat /tmp/dhcp.leases; printf '\n__CF_neighbors__\n'; ip -4 neigh show; printf '\n__CF_counters__\n'; cat /proc/net/dev; printf '\n__CF_devices__\n'; ubus call network.device status
CF_SEVEN
)
REQUEST_FIREWALL=$(cat <<'CF_FIREWALL'
set -e; printf '\n__CF_firewall_config__\n'; cat /etc/config/firewall; printf '\n__CF_firewall_active__\n'; nft -j -a list ruleset
CF_FIREWALL
)
case "${SSH_ORIGINAL_COMMAND-}" in
    "$REQUEST_SIX") COLLECT_KIND=base ;;
    "$REQUEST_SEVEN") COLLECT_KIND=ports ;;
    "$REQUEST_FIREWALL") COLLECT_KIND=firewall ;;
    *) printf '%s\n' 'Cypress Forge: command denied (read-only collector key).' >&2; exit 126 ;;
esac
if [ "$COLLECT_KIND" = firewall ]; then
    printf '\n__CF_firewall_config__\n'
    cat /etc/config/firewall
    printf '\n__CF_firewall_active__\n'
    nft -j -a list ruleset
    exit 0
fi
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
if [ "$COLLECT_KIND" = ports ]; then
    printf '\n__CF_devices__\n'
    ubus call network.device status
fi
