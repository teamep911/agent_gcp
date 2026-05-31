# FLEXING real demo scripts

All scripts target DB host `flex`, CDB SID `flex`, PDB `FLEXING` by default. They are prepared so Sam can run them immediately when Nam asks for a real demo.

Safety defaults:
- No script is auto-run by deployment.
- `check_flexing_context.sh` is read-only.
- Lock demo uses `DBMS_LOCK`, no test table required.
- Session demo opens live sleeping sessions and provides a cleanup script.
- Threshold demo queries FLEXING first, then sends an OEM-like payload with target `FLEXING` to prove the full Agent/Gateway/Dashboard flow.

Commands:

```bash
cd /u01/app/agent_monitor

# Read-only validation
scripts/demo_flexing/check_flexing_context.sh

# Real application-lock demo on FLEXING
HOLD_SECONDS=90 WAIT_SECONDS=25 scripts/demo_flexing/run_lock_demo.sh

# Real session demo on FLEXING; keep pids_file from output for cleanup
SESSION_COUNT=30 HOLD_SECONDS=180 scripts/demo_flexing/run_session_demo.sh
scripts/demo_flexing/cleanup_session_demo.sh /u01/app/agent_monitor/artifacts/demo_flexing/session_pids_<timestamp>.txt

# Threshold demos using FLEXING evidence then alert payload
scripts/demo_flexing/run_threshold_demo.sh cpu
scripts/demo_flexing/run_threshold_demo.sh session
scripts/demo_flexing/run_threshold_demo.sh tablespace
```

Important: if PDB `FLEXING` is not OPEN READ WRITE, the scripts will fail fast. Do not open/alter PDB state without Nam approval.
