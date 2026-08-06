#!/usr/bin/env bash
# AIAuto one-command start (Linux/macOS)
cd "$(dirname "$0")"
PYTHON=${PYTHON:-python3}
exec "$PYTHON" scripts/start.py "$@"
