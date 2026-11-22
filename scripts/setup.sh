#!/bin/sh
# CF Network Dashboard: one-time setup on Linux (the Linux counterpart of setup.ps1).
# Creates .venv, installs the Python requirements and builds the frontend. Never runs sudo:
# if a system package is missing it prints the command to install it, then stops.
set -eu
cd "$(dirname "$0")/.."

missing() {
    echo "!! $1" >&2
    echo "   Install it, for example on Debian/Ubuntu:  sudo apt install $2" >&2
    echo "   or on Fedora:                             sudo dnf install $3" >&2
    exit 1
}

command -v python3 >/dev/null 2>&1 || missing 'python3 not found.' 'python3 python3-venv' 'python3'
python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' \
    || missing "Python 3.11 or newer is needed (found $(python3 -V 2>&1))." 'python3' 'python3'
python3 -c 'import venv, ensurepip' 2>/dev/null || missing 'The Python venv module is missing.' 'python3-venv' 'python3'
command -v node >/dev/null 2>&1 || missing 'Node.js not found (20.19+ or 22.12+ is needed to build the frontend).' 'nodejs npm' 'nodejs npm'
command -v npm >/dev/null 2>&1 || missing 'npm not found.' 'npm' 'npm'
node -e '
const [a, b] = process.versions.node.split(".").map(Number);
process.exit((a === 20 && b >= 19) || (a === 22 && b >= 12) || a > 22 ? 0 : 1);  // Vite 7: ^20.19 || >=22.12
' || missing "Node.js 20.19+ or 22.12+ is needed (found $(node --version))." 'nodejs' 'nodejs'

if [ ! -x .venv/bin/python ]; then
    echo 'Creating .venv ...'
    python3 -m venv .venv
fi
echo 'Installing Python requirements ...'
.venv/bin/python -m pip install -q -r requirements.txt

echo 'Building the frontend ...'
cd frontend
if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi
npm run build
cd ..

echo
echo 'Setup complete. Start the dashboard with:  ./scripts/start.sh'
echo 'Connect your router with:                    ./scripts/connect-router.sh'
