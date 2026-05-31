#!/usr/bin/env bash
set -euo pipefail
DIR=$(cd "$(dirname "$0")" && pwd)
source "$DIR/flexing_demo_common.sh"

WORKERS=${WORKERS:-12}
DURATION_SECONDS=${DURATION_SECONDS:-300}
ALERT_INTERVAL_SECONDS=${ALERT_INTERVAL_SECONDS:-60}
ALERT_COUNT=${ALERT_COUNT:-5}
WARMUP_SECONDS=${WARMUP_SECONDS:-20}
MAX_CPU_CORES=${MAX_CPU_CORES:-10}
THRESHOLD=${THRESHOLD:-90}
TS=$(date +%Y%m%d_%H%M%S)
PIDS_FILE="$ARTIFACT_DIR/real_aas_5m_loop_pids_$TS.txt"
RUN_LOG="$ARTIFACT_DIR/real_aas_5m_loop_$TS.log"

ssh "$FLEX_HOST" "mkdir -p '$REMOTE_DIR/sql'"
scp -q "$DIR/sql/assert_flexing_open.sql" "$DIR/sql/cpu_active_session.sql" "$DIR/sql/count_demo_active_sessions.sql" "$FLEX_HOST:$REMOTE_DIR/sql/"
ssh "$FLEX_HOST" "ORACLE_HOME='$ORACLE_HOME_REMOTE' ORACLE_SID='$ORACLE_SID_REMOTE' PATH='$ORACLE_HOME_REMOTE/bin':\$PATH sqlplus -s / as sysdba @$REMOTE_DIR/sql/assert_flexing_open.sql '$PDB_NAME'"

: > "$PIDS_FILE"
for i in $(seq 1 "$WORKERS"); do
  ssh "$FLEX_HOST" "ORACLE_HOME='$ORACLE_HOME_REMOTE' ORACLE_SID='$ORACLE_SID_REMOTE' PATH='$ORACLE_HOME_REMOTE/bin':\$PATH sqlplus -s / as sysdba @$REMOTE_DIR/sql/cpu_active_session.sql '$PDB_NAME' '$DURATION_SECONDS' '$i'" \
    > "$ARTIFACT_DIR/real_aas_5m_loop_worker_${TS}_${i}.log" 2>&1 &
  echo "$!" >> "$PIDS_FILE"
  sleep 0.2
done

{
  echo "started_at=$(date -Is)"
  echo "target=$PDB_NAME workers=$WORKERS duration_seconds=$DURATION_SECONDS interval_seconds=$ALERT_INTERVAL_SECONDS alert_count=$ALERT_COUNT threshold=$THRESHOLD max_cpu_cores=$MAX_CPU_CORES"
  echo "pids_file=$PIDS_FILE"
} | tee "$RUN_LOG"

sleep "$WARMUP_SECONDS"
for n in $(seq 1 "$ALERT_COUNT"); do
  ACTIVE_COUNT=$(ssh "$FLEX_HOST" "ORACLE_HOME='$ORACLE_HOME_REMOTE' ORACLE_SID='$ORACLE_SID_REMOTE' PATH='$ORACLE_HOME_REMOTE/bin':\$PATH sqlplus -s / as sysdba @$REMOTE_DIR/sql/count_demo_active_sessions.sql '$PDB_NAME'" | awk '/^[[:space:]]*[0-9]+[[:space:]]*$/ {v=$1} END {print v+0}')
  CURRENT_PCT=$(python3 - "$ACTIVE_COUNT" "$MAX_CPU_CORES" <<'PY'
import sys
aas=float(sys.argv[1]); max_cpu=float(sys.argv[2])
print(round(aas/max_cpu*100) if max_cpu else 0)
PY
)
  PAYLOAD="$ARTIFACT_DIR/real_aas_5m_loop_payload_${TS}_${n}.json"
  python3 - "$PAYLOAD" "$n" "$ACTIVE_COUNT" "$CURRENT_PCT" <<'PY'
import json, datetime, sys
path, n, active, pct = sys.argv[1:5]
payload = {
  'source': 'oem',
  'target_name': 'FLEXING',
  'target_type': 'oracle_pdb',
  'severity': 'CRITICAL',
  'metric_name': 'cpuUtilization',
  'metric_column': 'cpuUtilization',
  'metric_value': str(pct),
  'message': f'REAL_FLEXING_AAS_5M_LOOP alert={n}/5 | threshold=90 | current={pct} | active_sessions={active} | repeat_every=60s | derived_from=gv$session_active_count',
  'rule_name': 'cpu_critical_90',
  'occurred_at': datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec='seconds'),
}
open(path, 'w').write(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
PY
  SEND_RESULT=$(send_oem_payload "$PAYLOAD")
  echo "$(date -Is) alert=$n active_sessions=$ACTIVE_COUNT current_pct=$CURRENT_PCT payload=$PAYLOAD result=$SEND_RESULT" | tee -a "$RUN_LOG"
  if [ "$n" -lt "$ALERT_COUNT" ]; then
    sleep "$ALERT_INTERVAL_SECONDS"
  fi
done

while read -r pid; do wait "$pid" || true; done < "$PIDS_FILE"
echo "finished_at=$(date -Is) run_log=$RUN_LOG" | tee -a "$RUN_LOG"
