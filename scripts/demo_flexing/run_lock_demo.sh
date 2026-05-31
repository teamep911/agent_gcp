#!/usr/bin/env bash
set -euo pipefail
DIR=$(cd "$(dirname "$0")" && pwd)
source "$DIR/flexing_demo_common.sh"
HOLD_SECONDS=${HOLD_SECONDS:-90}
WAIT_SECONDS=${WAIT_SECONDS:-25}
TS=$(date +%Y%m%d_%H%M%S)
HOLDER_LOG="$ARTIFACT_DIR/lock_holder_$TS.log"
WAITER_LOG="$ARTIFACT_DIR/lock_waiter_$TS.log"
CHECK_LOG="$ARTIFACT_DIR/lock_check_$TS.log"
PAYLOAD="$ARTIFACT_DIR/lock_payload_$TS.json"

ssh "$FLEX_HOST" "mkdir -p '$REMOTE_DIR/sql'"
scp -q "$DIR/sql/assert_flexing_open.sql" "$DIR/sql/hold_application_lock.sql" "$DIR/sql/wait_application_lock.sql" "$DIR/sql/check_application_lock.sql" "$FLEX_HOST:$REMOTE_DIR/sql/"
ssh "$FLEX_HOST" "ORACLE_HOME='$ORACLE_HOME_REMOTE' ORACLE_SID='$ORACLE_SID_REMOTE' PATH='$ORACLE_HOME_REMOTE/bin':\$PATH sqlplus -s / as sysdba @$REMOTE_DIR/sql/assert_flexing_open.sql '$PDB_NAME'"

ssh "$FLEX_HOST" "ORACLE_HOME='$ORACLE_HOME_REMOTE' ORACLE_SID='$ORACLE_SID_REMOTE' PATH='$ORACLE_HOME_REMOTE/bin':\$PATH sqlplus -s / as sysdba @$REMOTE_DIR/sql/hold_application_lock.sql '$PDB_NAME' '$HOLD_SECONDS'" > "$HOLDER_LOG" 2>&1 &
HOLDER_PID=$!
sleep 5
ssh "$FLEX_HOST" "ORACLE_HOME='$ORACLE_HOME_REMOTE' ORACLE_SID='$ORACLE_SID_REMOTE' PATH='$ORACLE_HOME_REMOTE/bin':\$PATH sqlplus -s / as sysdba @$REMOTE_DIR/sql/wait_application_lock.sql '$PDB_NAME' '$WAIT_SECONDS'" > "$WAITER_LOG" 2>&1 &
WAITER_PID=$!
sleep 5
ssh "$FLEX_HOST" "ORACLE_HOME='$ORACLE_HOME_REMOTE' ORACLE_SID='$ORACLE_SID_REMOTE' PATH='$ORACLE_HOME_REMOTE/bin':\$PATH sqlplus -s / as sysdba @$REMOTE_DIR/sql/check_application_lock.sql '$PDB_NAME'" > "$CHECK_LOG" 2>&1 || true

python3 - <<PY
import json, datetime
payload={
 'source':'oem','target_name':'FLEXING','target_type':'oracle_pdb','severity':'CRITICAL',
 'metric_name':'userBlockedSessionCount','metric_column':'userBlockedSessionCount','metric_value':'1',
 'message':'REAL_FLEXING_LOCK_DEMO | DBMS_LOCK application lock wait observed on PDB FLEXING | holder_log=$HOLDER_LOG waiter_log=$WAITER_LOG check_log=$CHECK_LOG',
 'rule_name':'blocking_lock','occurred_at':datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec='seconds')}
open('$PAYLOAD','w').write(json.dumps(payload, ensure_ascii=False, indent=2)+'\n')
PY
send_oem_payload "$PAYLOAD"
echo "holder_pid=$HOLDER_PID waiter_pid=$WAITER_PID"
echo "holder_log=$HOLDER_LOG"
echo "waiter_log=$WAITER_LOG"
echo "check_log=$CHECK_LOG"
echo "payload=$PAYLOAD"
