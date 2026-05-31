#!/usr/bin/env bash
set -euo pipefail
cd /u01/app/agent_monitor
exec env \
  LOCK_DEMO_HOLD_MINUTES=5 \
  LOCK_DEMO_ALERT_EVERY_MINUTES=1 \
  LOCK_DEMO_WAIT_SECONDS=360 \
  scripts/demo_flexing/run_lock_demo.sh
