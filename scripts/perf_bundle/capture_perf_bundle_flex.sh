#!/usr/bin/env bash
set -euo pipefail

ROOT=/u01/app/monitor/scripts/perf_bundle
OUT_DIR=/u01/app/monitor/artifacts/perf
mkdir -p "$OUT_DIR"

TS=$(date +%Y%m%d_%H%M%S)
HOST=${FLEX_HOST:-flex}
LAST_MIN=${LAST_MIN:-10}
BUCKET_SEC=${BUCKET_SEC:-20}
MAX_CPU_CORES=${MAX_CPU_CORES:-10}

CSV="$OUT_DIR/aas_waitclass_${TS}.csv"
SVG="$OUT_DIR/aas_waitclass_${TS}.svg"
PNG="$OUT_DIR/aas_waitclass_${TS}.png"
TOP_TXT="$OUT_DIR/top5_sql_${TS}.txt"
TOP_CSV="$OUT_DIR/top5_sql_${TS}.csv"
SUMMARY="$OUT_DIR/perf_bundle_${TS}.txt"

REMOTE_DIR="/tmp/monitor_v2_perf_${TS}"
REMOTE_CSV="$REMOTE_DIR/aas_waitclass.csv"
REMOTE_TOP_TXT="$REMOTE_DIR/top5_sql.txt"
REMOTE_TOP_CSV="$REMOTE_DIR/top5_sql.csv"

ssh "$HOST" "mkdir -p '$REMOTE_DIR'"
scp -q "$ROOT/aas_waitclass_20s.sql" "$ROOT/top5_sql.sql" "$HOST:$REMOTE_DIR/"

# 1) Pull ASH wait-class data from DB flex
ssh "$HOST" "ORACLE_HOME=/u01/app/19.0.0/oracle ORACLE_SID=flex PATH=/u01/app/19.0.0/oracle/bin:\$PATH sqlplus -s / as sysdba @$REMOTE_DIR/aas_waitclass_20s.sql $REMOTE_CSV $LAST_MIN $BUCKET_SEC"
scp -q "$HOST:$REMOTE_CSV" "$CSV"

# 2) Render SVG + convert PNG locally on agent server
python3 "$ROOT/aas_svg.py" -i "$CSV" -o "$SVG" --max-cpu "$MAX_CPU_CORES" --title "Average Active Sessions"
rsvg-convert -o "$PNG" "$SVG"

# 3) Pull top5 SQL from DB flex/FLEXING
ssh "$HOST" "ORACLE_HOME=/u01/app/19.0.0/oracle ORACLE_SID=flex PATH=/u01/app/19.0.0/oracle/bin:\$PATH sqlplus -s / as sysdba @$REMOTE_DIR/top5_sql.sql $REMOTE_TOP_TXT $REMOTE_TOP_CSV"
scp -q "$HOST:$REMOTE_TOP_TXT" "$TOP_TXT"
scp -q "$HOST:$REMOTE_TOP_CSV" "$TOP_CSV"
ssh "$HOST" "rm -rf '$REMOTE_DIR'" || true

# 4) Summary for Telegram
{
  echo "[PERF_BUNDLE] DB=flex target=flex_flex"
  echo "timestamp=$TS"
  echo "last_min=$LAST_MIN bucket_sec=$BUCKET_SEC max_cpu_cores=$MAX_CPU_CORES"
  echo "aas_png=$PNG"
  echo "top5_sql_txt=$TOP_TXT"
  echo "top5_sql_csv=$TOP_CSV"
} > "$SUMMARY"

echo "$SUMMARY"
