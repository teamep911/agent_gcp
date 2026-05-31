#!/usr/bin/env bash
set -euo pipefail
DIR=$(cd "$(dirname "$0")" && pwd)
source "$DIR/flexing_demo_common.sh"

WORKERS=${WORKERS:-12}
HOLD_SECONDS=${HOLD_SECONDS:-240}
WARMUP_SECONDS=${WARMUP_SECONDS:-60}
LAST_MIN=${LAST_MIN:-10}
BUCKET_SEC=${BUCKET_SEC:-20}
MAX_CPU_CORES=${MAX_CPU_CORES:-10}
THRESHOLD=${THRESHOLD:-90}
TS=$(date +%Y%m%d_%H%M%S)
PIDS_FILE="$ARTIFACT_DIR/real_aas_alert_pids_$TS.txt"
PAYLOAD="$ARTIFACT_DIR/real_aas_alert_payload_$TS.json"
RUN_LOG="$ARTIFACT_DIR/real_aas_alert_$TS.log"
PERF_SCRIPT="/u01/app/agent_monitor/scripts/perf_bundle/capture_perf_bundle_flex.sh"
PERF_STDOUT="$ARTIFACT_DIR/real_aas_alert_perf_stdout_$TS.log"

ssh "$FLEX_HOST" "mkdir -p '$REMOTE_DIR/sql'"
scp -q "$DIR/sql/assert_flexing_open.sql" "$DIR/sql/cpu_active_session.sql" "$FLEX_HOST:$REMOTE_DIR/sql/"
ssh "$FLEX_HOST" "ORACLE_HOME='$ORACLE_HOME_REMOTE' ORACLE_SID='$ORACLE_SID_REMOTE' PATH='$ORACLE_HOME_REMOTE/bin':\$PATH sqlplus -s / as sysdba @$REMOTE_DIR/sql/assert_flexing_open.sql '$PDB_NAME'"

: > "$PIDS_FILE"
for i in $(seq 1 "$WORKERS"); do
  ssh "$FLEX_HOST" "ORACLE_HOME='$ORACLE_HOME_REMOTE' ORACLE_SID='$ORACLE_SID_REMOTE' PATH='$ORACLE_HOME_REMOTE/bin':\$PATH sqlplus -s / as sysdba @$REMOTE_DIR/sql/cpu_active_session.sql '$PDB_NAME' '$HOLD_SECONDS' '$i'" \
    > "$ARTIFACT_DIR/real_aas_alert_worker_${TS}_${i}.log" 2>&1 &
  echo "$!" >> "$PIDS_FILE"
  sleep 0.2
done

echo "started_workers=$WORKERS hold_seconds=$HOLD_SECONDS pids_file=$PIDS_FILE" | tee "$RUN_LOG"
sleep "$WARMUP_SECONDS"
LAST_MIN="$LAST_MIN" BUCKET_SEC="$BUCKET_SEC" MAX_CPU_CORES="$MAX_CPU_CORES" "$PERF_SCRIPT" > "$PERF_STDOUT"
PERF_SUMMARY=$(tail -n 1 "$PERF_STDOUT" | tr -d '\r')
ACTIVE_COUNT=$(remote_sqlplus "$DIR/sql/count_demo_active_sessions.sql" | awk '/^[[:space:]]*[0-9]+[[:space:]]*$/ {v=$1} END {print v+0}')
read -r MAX_AAS CURRENT_PCT < <(python3 - "$ACTIVE_COUNT" "$MAX_CPU_CORES" <<'PY'
import sys
aas=float(sys.argv[1]); max_cpu=float(sys.argv[2])
print(f"{aas:.2f} {round(aas/max_cpu*100) if max_cpu else 0}")
PY
)
SEVERITY=CRITICAL
python3 - <<PY
import json, datetime
payload={
 'source':'oem','target_name':'FLEXING','target_type':'oracle_pdb','severity':'$SEVERITY',
 'metric_name':'cpuUtilization','metric_column':'cpuUtilization','metric_value':'$CURRENT_PCT',
 'message':'REAL_FLEXING_AAS_THRESHOLD | threshold=$THRESHOLD | current=$CURRENT_PCT | max_aas=$MAX_AAS | max_cpu_cores=$MAX_CPU_CORES | workers=$WORKERS | perf_summary=$PERF_SUMMARY',
 'rule_name':'cpu_critical_90','occurred_at':datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec='seconds')}
open('$PAYLOAD','w').write(json.dumps(payload, ensure_ascii=False, indent=2)+'\n')
PY
send_oem_payload "$PAYLOAD" | tee -a "$RUN_LOG"

echo "threshold=$THRESHOLD current=$CURRENT_PCT max_aas=$MAX_AAS payload=$PAYLOAD perf_summary=$PERF_SUMMARY" | tee -a "$RUN_LOG"
while read -r pid; do wait "$pid"; done < "$PIDS_FILE"
echo "run_log=$RUN_LOG"
