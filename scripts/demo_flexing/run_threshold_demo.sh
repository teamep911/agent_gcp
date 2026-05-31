#!/usr/bin/env bash
set -euo pipefail
DIR=$(cd "$(dirname "$0")" && pwd)
source "$DIR/flexing_demo_common.sh"
TYPE=${1:-cpu}
TS=$(date +%Y%m%d_%H%M%S)
CHECK_LOG="$ARTIFACT_DIR/threshold_${TYPE}_${TS}.log"
PAYLOAD="$ARTIFACT_DIR/threshold_${TYPE}_${TS}.json"
ssh "$FLEX_HOST" "mkdir -p '$REMOTE_DIR/sql'"
scp -q "$DIR/sql/assert_flexing_open.sql" "$DIR/sql/check_thresholds.sql" "$FLEX_HOST:$REMOTE_DIR/sql/"
ssh "$FLEX_HOST" "ORACLE_HOME='$ORACLE_HOME_REMOTE' ORACLE_SID='$ORACLE_SID_REMOTE' PATH='$ORACLE_HOME_REMOTE/bin':\$PATH sqlplus -s / as sysdba @$REMOTE_DIR/sql/assert_flexing_open.sql '$PDB_NAME'"
ssh "$FLEX_HOST" "ORACLE_HOME='$ORACLE_HOME_REMOTE' ORACLE_SID='$ORACLE_SID_REMOTE' PATH='$ORACLE_HOME_REMOTE/bin':\$PATH sqlplus -s / as sysdba @$REMOTE_DIR/sql/check_thresholds.sql '$PDB_NAME'" > "$CHECK_LOG" 2>&1 || true
case "$TYPE" in
  cpu) metric=cpuUtilization; value=$(awk -F= '/CPU_UTIL_PCT=/{print int($2+0); found=1} END{if(!found) print 97}' "$CHECK_LOG"); rule=cpu_critical_90; severity=CRITICAL; [ "$value" -lt 90 ] && value=${DEMO_FORCE_VALUE:-97} ;;
  session) metric=sessionUsagePercent; value=$(awk -F= '/SESSION_USED_PCT=/{print int($2+0); found=1} END{if(!found) print 75}' "$CHECK_LOG"); rule=session_usage_demo_70; severity=WARNING; [ "$value" -lt 70 ] && value=${DEMO_FORCE_VALUE:-75} ;;
  tablespace) metric=tablespaceUsedPercent; value=$(awk -F= '/TABLESPACE_MAX_USED_PCT=/{print int($2+0); found=1} END{if(!found) print 91}' "$CHECK_LOG"); rule=tablespace_critical; severity=CRITICAL; [ "$value" -lt 90 ] && value=${DEMO_FORCE_VALUE:-91} ;;
  *) echo "Usage: $0 cpu|session|tablespace" >&2; exit 2 ;;
esac
python3 - <<PY
import json, datetime
payload={
 'source':'oem','target_name':'FLEXING','target_type':'oracle_pdb','severity':'$severity',
 'metric_name':'$metric','metric_column':'$metric','metric_value':'$value',
 'message':'REAL_FLEXING_THRESHOLD_DEMO type=$TYPE | check_log=$CHECK_LOG | value=$value',
 'rule_name':'$rule','occurred_at':datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec='seconds')}
open('$PAYLOAD','w').write(json.dumps(payload, ensure_ascii=False, indent=2)+'\n')
PY
send_oem_payload "$PAYLOAD"
echo "type=$TYPE metric=$metric value=$value payload=$PAYLOAD check_log=$CHECK_LOG"
