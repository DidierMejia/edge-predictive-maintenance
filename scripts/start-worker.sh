#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
export WORKER_ID="${WORKER_ID:-edge-worker1}"
python worker/app.py
