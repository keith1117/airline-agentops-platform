#!/usr/bin/env bash
set -euo pipefail

HOST="${LOCUST_HOST:-http://127.0.0.1:8001}"
USERS="${LOCUST_USERS:-20}"
SPAWN_RATE="${LOCUST_SPAWN_RATE:-5}"
RUN_TIME="${LOCUST_RUN_TIME:-1m}"
CSV_PREFIX="${LOCUST_CSV_PREFIX:-logs/locust_smoke}"
PYTHON_BIN="${PYTHON_BIN:-python}"

if [ -x ".venv/bin/python" ] && [ "$PYTHON_BIN" = "python" ]; then
  PYTHON_BIN=".venv/bin/python"
fi

mkdir -p "$(dirname "$CSV_PREFIX")"

"$PYTHON_BIN" -m locust \
  -f load_tests/locustfile.py \
  --headless \
  --host "$HOST" \
  --users "$USERS" \
  --spawn-rate "$SPAWN_RATE" \
  --run-time "$RUN_TIME" \
  --csv "$CSV_PREFIX" \
  --only-summary
