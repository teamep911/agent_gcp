#!/usr/bin/env bash
set -euo pipefail
cd /u01/app/agent_monitor
exec env \
  WORKERS=12 \
  DURATION_SECONDS=300 \
  ALERT_INTERVAL_SECONDS=60 \
  ALERT_COUNT=5 \
  WARMUP_SECONDS=20 \
  MAX_CPU_CORES=10 \
  THRESHOLD=90 \
  scripts/demo_flexing/run_real_aas_threshold_5m_loop.sh
