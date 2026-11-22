#!/bin/sh
# CF Network Dashboard: run every test on Linux (the Linux counterpart of test.ps1).
# Backend unit tests (including the router-gate tests, which need a POSIX sh), then the
# frontend tests and production build.
set -eu
cd "$(dirname "$0")/.."
PY="${PYTHON:-.venv/bin/python}"
"$PY" -m unittest discover -s tests -v
cd frontend
npm test
npm run build
