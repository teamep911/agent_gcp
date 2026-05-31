#!/usr/bin/env bash
set -euo pipefail
DIR=$(cd "$(dirname "$0")" && pwd)
# Default lock demo is long-running for production-like demo:
# - hold lock for 20 minutes
# - send alert immediately and every 5 minutes while lock remains
# Override via LOCK_DEMO_HOLD_MINUTES / LOCK_DEMO_ALERT_EVERY_MINUTES if needed.
exec /u01/app/agent_monitor/.venv/bin/python "$DIR/run_lock_demo.py"
