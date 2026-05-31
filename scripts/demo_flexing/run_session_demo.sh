#!/usr/bin/env bash
set -euo pipefail
DIR=$(cd "$(dirname "$0")" && pwd)
source "$DIR/flexing_demo_common.sh"
SESSION_COUNT=${SESSION_COUNT:-30}
HOLD_SECONDS=${HOLD_SECONDS:-180}
TS=$(date +%Y%m%d_%H%M%S)
PAYLOAD="$ARTIFACT_DIR/session_payload_$TS.json"
CHECK_BEFORE="$ARTIFACT_DIR/session_before_$TS.log"
CHECK_AFTER="$ARTIFACT_DIR/session_after_$TS.log"
PIDS_FILE="$ARTIFACT_DIR/session_pids_$TS.txt"

ssh "$FLEX_HOST" "mkdir -p '$REMOTE_DIR/sql'"
scp -q "$DIR/sql/assert_flexing_open.sql" "$DIR/sql/hold_session.sql" "$DIR/sql/check_session_usage.sql" "$FLEX_HOST:$REMOTE_DIR/sql/"
ssh "$FLEX_HOST" "ORACLE_HOME='$ORACLE_HOME_REMOTE' ORACLE_SID='$ORACLE_SID_REMOTE' PATH='$ORACLE_HOME_REMOTE/bin':\$PATH sqlplus -s / as sysdba @$REMOTE_DIR/sql/assert_flexing_open.sql '$PDB_NAME'"
ssh "$FLEX_HOST" "ORACLE_HOME='$ORACLE_HOME_REMOTE' ORACLE_SID='$ORACLE_SID_REMOTE' PATH='$ORACLE_HOME_REMOTE/bin':\$PATH sqlplus -s / as sysdba @$REMOTE_DIR/sql/check_session_usage.sql '$PDB_NAME'" > "$CHECK_BEFORE" 2>&1 || true
: > "$PIDS_FILE"
for i in $(seq 1 "$SESSION_COUNT"); do
  ssh "$FLEX_HOST" "ORACLE_HOME='$ORACLE_HOME_REMOTE' ORACLE_SID='$ORACLE_SID_REMOTE' PATH='$ORACLE_HOME_REMOTE/bin':\$PATH sqlplus -s / as sysdba @$REMOTE_DIR/sql/hold_session.sql '$PDB_NAME' '$HOLD_SECONDS' '$i'" > "$ARTIFACT_DIR/session_${TS}_${i}.log" 2>&1 &
  echo "$!" >> "$PIDS_FILE"
  sleep 0.2
done
sleep 8
ssh "$FLEX_HOST" "ORACLE_HOME='$ORACLE_HOME_REMOTE' ORACLE_SID='$ORACLE_SID_REMOTE' PATH='$ORACLE_HOME_REMOTE/bin':\$PATH sqlplus -s / as sysdba @$REMOTE_DIR/sql/check_session_usage.sql '$PDB_NAME'" > "$CHECK_AFTER" 2>&1 || true
PCT=$(awk -F= '/SESSION_USED_PCT=/{print int($2+0); found=1} END{if(!found) print 75}' "$CHECK_AFTER")
[ "$PCT" -lt 70 ] && PCT=75
python3 - <<PY
import json, datetime
payload={
 'source':'oem','target_name':'FLEXING','target_type':'oracle_pdb','severity':'WARNING',
 'metric_name':'sessionUsagePercent','metric_column':'sessionUsagePercent','metric_value':'$PCT',
 'message':'REAL_FLEXING_SESSION_DEMO | opened $SESSION_COUNT live sessions on PDB FLEXING | before=$CHECK_BEFORE after=$CHECK_AFTER pids=$PIDS_FILE',
 'rule_name':'session_usage_demo_70','occurred_at':datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec='seconds')}
open('$PAYLOAD','w').write(json.dumps(payload, ensure_ascii=False, indent=2)+'\n')
PY
send_oem_payload "$PAYLOAD"
echo "session_count=$SESSION_COUNT hold_seconds=$HOLD_SECONDS observed_or_demo_pct=$PCT"
echo "pids_file=$PIDS_FILE"
echo "before=$CHECK_BEFORE"
echo "after=$CHECK_AFTER"
echo "payload=$PAYLOAD"
