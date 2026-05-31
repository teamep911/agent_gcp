#!/usr/bin/env bash
set -euo pipefail

ROOT=${FLEXING_DEMO_ROOT:-/u01/app/agent_monitor/scripts/demo_flexing}
ARTIFACT_DIR=${FLEXING_DEMO_ARTIFACT_DIR:-/u01/app/agent_monitor/artifacts/demo_flexing}
FLEX_HOST=${FLEX_HOST:-flex}
ORACLE_HOME_REMOTE=${ORACLE_HOME_REMOTE:-/u01/app/19.0.0/oracle}
ORACLE_SID_REMOTE=${ORACLE_SID_REMOTE:-flex}
PDB_NAME=${PDB_NAME:-FLEXING}
REMOTE_DIR=${REMOTE_DIR:-/tmp/agent_monitor_demo_flexing}
mkdir -p "$ARTIFACT_DIR"

remote_sqlplus() {
  local sql_file="$1"; shift || true
  local base
  base=$(basename "$sql_file")
  ssh "$FLEX_HOST" "mkdir -p '$REMOTE_DIR/sql'"
  scp -q "$sql_file" "$FLEX_HOST:$REMOTE_DIR/sql/$base"
  ssh "$FLEX_HOST" "ORACLE_HOME='$ORACLE_HOME_REMOTE' ORACLE_SID='$ORACLE_SID_REMOTE' PATH='$ORACLE_HOME_REMOTE/bin':\$PATH sqlplus -s / as sysdba @$REMOTE_DIR/sql/$base '$PDB_NAME' $*"
}

send_oem_payload() {
  local payload_file="$1"
  /u01/app/agent_monitor/.venv/bin/python "$ROOT/send_oem_payload.py" "$payload_file"
}
