#!/usr/bin/env bash
set -euo pipefail
DIR=$(cd "$(dirname "$0")" && pwd)
source "$DIR/flexing_demo_common.sh"

WORKERS=${WORKERS:-12}
HOLD_SECONDS=${HOLD_SECONDS:-180}
WARMUP_SECONDS=${WARMUP_SECONDS:-40}
LAST_MIN=${LAST_MIN:-10}
BUCKET_SEC=${BUCKET_SEC:-20}
MAX_CPU_CORES=${MAX_CPU_CORES:-10}
TS=$(date +%Y%m%d_%H%M%S)
PIDS_FILE="$ARTIFACT_DIR/real_aas_cpu_pids_$TS.txt"
RUN_LOG="$ARTIFACT_DIR/real_aas_cpu_$TS.log"
SUMMARY_FILE="$ARTIFACT_DIR/real_aas_cpu_summary_$TS.txt"
PERF_SCRIPT="/u01/app/agent_monitor/scripts/perf_bundle/capture_perf_bundle_flex.sh"
PERF_STDOUT="$ARTIFACT_DIR/real_aas_perf_stdout_$TS.log"

ssh "$FLEX_HOST" "mkdir -p '$REMOTE_DIR/sql'"
scp -q "$DIR/sql/assert_flexing_open.sql" "$DIR/sql/cpu_active_session.sql" "$FLEX_HOST:$REMOTE_DIR/sql/"
ssh "$FLEX_HOST" "ORACLE_HOME='$ORACLE_HOME_REMOTE' ORACLE_SID='$ORACLE_SID_REMOTE' PATH='$ORACLE_HOME_REMOTE/bin':\$PATH sqlplus -s / as sysdba @$REMOTE_DIR/sql/assert_flexing_open.sql '$PDB_NAME'"

: > "$PIDS_FILE"
for i in $(seq 1 "$WORKERS"); do
  ssh "$FLEX_HOST" "ORACLE_HOME='$ORACLE_HOME_REMOTE' ORACLE_SID='$ORACLE_SID_REMOTE' PATH='$ORACLE_HOME_REMOTE/bin':\$PATH sqlplus -s / as sysdba @$REMOTE_DIR/sql/cpu_active_session.sql '$PDB_NAME' '$HOLD_SECONDS' '$i'" \
    > "$ARTIFACT_DIR/real_aas_cpu_worker_${TS}_${i}.log" 2>&1 &
  echo "$!" >> "$PIDS_FILE"
  sleep 0.2
done

echo "started_workers=$WORKERS hold_seconds=$HOLD_SECONDS pids_file=$PIDS_FILE" | tee "$RUN_LOG"
sleep "$WARMUP_SECONDS"

LAST_MIN="$LAST_MIN" BUCKET_SEC="$BUCKET_SEC" MAX_CPU_CORES="$MAX_CPU_CORES" "$PERF_SCRIPT" > "$PERF_STDOUT"
PERF_SUMMARY=$(tail -n 1 "$PERF_STDOUT" | tr -d '\r')
if [[ ! -f "$PERF_SUMMARY" ]]; then
  echo "perf_bundle summary path not found: $PERF_SUMMARY" >&2
  echo "perf_stdout=$PERF_STDOUT" >&2
  exit 1
fi
printf '%s\n' "$PERF_SUMMARY" | tee -a "$RUN_LOG"
cat "$PERF_SUMMARY" > "$SUMMARY_FILE"

echo "workers=$WORKERS" >> "$SUMMARY_FILE"
echo "hold_seconds=$HOLD_SECONDS" >> "$SUMMARY_FILE"
echo "warmup_seconds=$WARMUP_SECONDS" >> "$SUMMARY_FILE"
echo "pids_file=$PIDS_FILE" >> "$SUMMARY_FILE"
echo "perf_stdout=$PERF_STDOUT" >> "$SUMMARY_FILE"

while read -r pid; do
  wait "$pid"
done < "$PIDS_FILE"

echo "summary=$SUMMARY_FILE"
echo "run_log=$RUN_LOG"
