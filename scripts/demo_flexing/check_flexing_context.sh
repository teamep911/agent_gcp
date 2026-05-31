#!/usr/bin/env bash
set -euo pipefail
DIR=$(cd "$(dirname "$0")" && pwd)
source "$DIR/flexing_demo_common.sh"
remote_sqlplus "$DIR/sql/check_context.sql"
