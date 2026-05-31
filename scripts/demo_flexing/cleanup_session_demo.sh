#!/usr/bin/env bash
set -euo pipefail
PIDS_FILE=${1:?Usage: cleanup_session_demo.sh <pids_file>}
while read -r pid; do
  [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
done < "$PIDS_FILE"
echo "cleanup_submitted pids_file=$PIDS_FILE"
