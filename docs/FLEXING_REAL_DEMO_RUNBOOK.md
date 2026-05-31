# FLEXING Real Demo Runbook

Goal: all real demo preparations target DB host `flex`, PDB `FLEXING`, aligned with production-style target selection.

Important current fact:
- `FLEXING` is currently `MOUNTED`, not `READ WRITE`.
- Because of that, the prepared real demo scripts are designed to fail fast before doing side effects.
- Sam should only run the real scripts after anh Nam confirms FLEXING is open for demo.

Prepared scripts:

- Context check:
  - `/u01/app/agent_monitor/scripts/demo_flexing/check_flexing_context.sh`
- Real lock demo:
  - `/u01/app/agent_monitor/scripts/demo_flexing/run_lock_demo.sh`
- Real session demo:
  - `/u01/app/agent_monitor/scripts/demo_flexing/run_session_demo.sh`
- Session cleanup:
  - `/u01/app/agent_monitor/scripts/demo_flexing/cleanup_session_demo.sh <pids_file>`
- Real threshold demo from FLEXING evidence:
  - `/u01/app/agent_monitor/scripts/demo_flexing/run_threshold_demo.sh cpu`
  - `/u01/app/agent_monitor/scripts/demo_flexing/run_threshold_demo.sh session`
  - `/u01/app/agent_monitor/scripts/demo_flexing/run_threshold_demo.sh tablespace`

Behavior:

1. Every stateful script checks that `FLEXING` is `READ WRITE` first.
2. The lock demo uses `DBMS_LOCK` on `FLEXING` and then sends an OEM-like alert targeting `FLEXING`.
3. The session demo opens multiple live sleeping sessions on `FLEXING`, captures usage evidence, and then sends an OEM-like alert targeting `FLEXING`.
4. The threshold demo queries live values from `FLEXING`; if the real metric is still below demo threshold, it sends a controlled OEM-like payload for the same `FLEXING` target so the end-to-end board/dashboard path can still be demonstrated.

Suggested operator sequence when Nam asks to run a demo:

```bash
cd /u01/app/agent_monitor

# 1) Confirm PDB state
scripts/demo_flexing/check_flexing_context.sh

# 2a) Lock demo
HOLD_SECONDS=90 WAIT_SECONDS=25 scripts/demo_flexing/run_lock_demo.sh

# 2b) Session demo
SESSION_COUNT=30 HOLD_SECONDS=180 scripts/demo_flexing/run_session_demo.sh
# save pids file from output for cleanup later

# 2c) Threshold demo
scripts/demo_flexing/run_threshold_demo.sh cpu
scripts/demo_flexing/run_threshold_demo.sh session
scripts/demo_flexing/run_threshold_demo.sh tablespace

# 3) Cleanup after session demo
scripts/demo_flexing/cleanup_session_demo.sh /u01/app/agent_monitor/artifacts/demo_flexing/session_pids_<timestamp>.txt
```

Notes:
- `scripts/run_demo_flows.py` has also been switched to target `FLEXING` in payloads for board/demo consistency.
- Real final Google Chat visibility is still a manual room verification step if shell cannot read room history.
