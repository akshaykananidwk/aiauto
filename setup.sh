#!/usr/bin/env bash
# AIAuto one-command setup (Linux/macOS)
set -e
cd "$(dirname "$0")"
PYTHON=${PYTHON:-python3}
exec "$PYTHON" scripts/setup.py "$@"
