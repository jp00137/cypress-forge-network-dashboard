#!/bin/sh
# CF Network Dashboard: connect to your OpenWrt router on Linux (the counterpart of connect-router.ps1).
# Creates a dedicated read-only dashboard key, installs it on the router over one password SSH
# session (the password is typed into SSH, never stored), writes config.local.json and verifies
# everything. Re-running it is safe.
# Usage: ./scripts/connect-router.sh [--router IP] [--user root] [--key-name cypress_forge_collector]
set -eu
cd "$(dirname "$0")/.."

ROUTER=''
USER_NAME='root'
KEY_NAME='cypress_forge_collector'
while [ $# -gt 0 ]; do
    case "$1" in
        --router) ROUTER="$2"; shift 2 ;;
        --user) USER_NAME="$2"; shift 2 ;;
        --key-name) KEY_NAME="$2"; shift 2 ;;
        -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

PY=.venv/bin/python
[ -x "$PY" ] || { echo 'Run ./scripts/setup.sh first.' >&2; exit 1; }
command -v ssh >/dev/null 2>&1 || { echo 'The OpenSSH client is missing: sudo apt install openssh-client' >&2; exit 1; }
command -v ssh-keygen >/dev/null 2>&1 || { echo 'ssh-keygen is missing: sudo apt install openssh-client' >&2; exit 1; }

step() { printf '\n[%s/5] %s\n' "$1" "$2"; }
ok() { printf '  OK  %s\n' "$1"; }
fail() { printf '  !!  %s\n' "$1" >&2; exit 1; }

echo 'CF Network Dashboard router connection'
echo 'This adds ONE read-only key to your router. No firewall, network, password or service changes.'

# 1. Router address
step 1 'Router address'
if [ -z "$ROUTER" ]; then
    GW=$(ip -4 route show default 2>/dev/null | awk '{print $3; exit}')
    [ -n "$GW" ] || GW='192.168.1.1'
    printf '  Router IP [%s]: ' "$GW"
    read -r ANSWER || ANSWER=''
    ROUTER=${ANSWER:-$GW}
fi
if command -v ping >/dev/null 2>&1 && ! ping -c 2 -W 2 "$ROUTER" >/dev/null 2>&1; then
    fail "No answer from $ROUTER. Check the address and that this computer is on the router's network."
fi
ok "$ROUTER answers"

# 2. Dedicated key (no passphrase: it can only run the dashboard's fixed reads)
step 2 'Dashboard key'
SSH_DIR="$HOME/.ssh"
KEY="$SSH_DIR/$KEY_NAME"
if [ -f "$KEY.pub" ]; then
    ok "Using existing key $KEY_NAME"
else
    mkdir -p "$SSH_DIR" && chmod 700 "$SSH_DIR"
    ssh-keygen -q -t ed25519 -N '' -C 'Cypress Forge collector' -f "$KEY" || fail 'Could not create the key.'
    ok "Created $KEY_NAME (private half stays in $SSH_DIR)"
fi

# 3. Install on the router (password typed into SSH once)
step 3 'Install read-only access on the router'
INSTALLER=$(mktemp "${TMPDIR:-/tmp}/cf-router-install.XXXXXX")
trap 'rm -f "$INSTALLER"' EXIT
"$PY" -m backend.cli router-installer --pubkey "$KEY.pub" --out "$INSTALLER" >/dev/null \
    || fail 'Could not prepare the router installer.'
echo "  SSH will connect to $USER_NAME@$ROUTER."
echo "  - If asked to confirm the router's fingerprint, compare it with LuCI (System > Administration > SSH Keys)"
echo '    or answer yes on a network you trust.'
echo '  - Then type the router password. It is not shown or saved.'
set +e
ssh -o PubkeyAuthentication=no -o PreferredAuthentications=password,keyboard-interactive \
    -o StrictHostKeyChecking=ask "$USER_NAME@$ROUTER" sh -s < "$INSTALLER"
CODE=$?
set -e
[ "$CODE" -ne 2 ] || fail 'This key already has a different entry on the router. Nothing was changed; see docs/ROUTER-ACCESS.md.'
[ "$CODE" -eq 0 ] || fail "Router install did not finish. Nothing in this computer's config was changed."
ok 'Router access installed'

# 4. Save settings
step 4 'Save dashboard settings'
"$PY" -m backend.cli configure --host "$ROUTER" --user "$USER_NAME" --identity-file "$KEY" \
    || fail 'Settings could not be saved.'

# 5. Verify reads work and nothing else does
step 5 'Verify'
FAILED=0
for CHECK in verify-ports verify-firewall verify-dhcp verify-locked; do
    if OUT=$("$PY" -m backend.cli "$CHECK" 2>&1); then
        ok "$(printf '%s\n' "$OUT" | head -n 1)"
    else
        printf '  !!  %s : %s\n' "$CHECK" "$(printf '%s' "$OUT" | tr '\n' ' ')" >&2
        FAILED=1
    fi
done
[ "$FAILED" -eq 0 ] || fail "Some checks failed. Run:  $PY -m backend.cli diagnose"

echo
echo 'All set. Start (or restart) the dashboard with ./scripts/start.sh'
echo "To revoke access later:  $PY -m backend.cli router-remover --pubkey \"$KEY.pub\" --out remove.sh  then run it on the router."
