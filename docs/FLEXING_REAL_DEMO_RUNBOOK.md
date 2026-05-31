# FLEXING Real Demo Runbook

Goal: all real demo preparations target DB host `flex`, PDB `FLEXING`, aligned with production-style target selection.

Important current fact:
- `FLEXING` must be `READ WRITE`.
- Real demo scripts fail fast before side effects if FLEXING is not open correctly.

Prepared scripts:

- Context check:
  - `/u01/app/agent_monitor/scripts/demo_flexing/check_flexing_context.sh`
- Long real lock demo:
  - `/u01/app/agent_monitor/scripts/demo_flexing/run_lock_demo.sh`
- Long real lock demo engine:
  - `/u01/app/agent_monitor/scripts/demo_flexing/run_lock_demo.py`
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
2. The lock demo now runs production-style:
   - hold lock for 20 minutes by default
   - send first alert immediately
   - resend every 5 minutes while lock is still present
   - update Flow Test Board in realtime for each stage
   - enrich alert message with `sql_id`, `sql_text`, `owner`, wait event, and evidence log path
3. The session demo opens multiple live sleeping sessions on `FLEXING`, captures usage evidence, and then sends an OEM-like alert targeting `FLEXING`.
4. The threshold demo queries live values from `FLEXING`; if the real metric is still below demo threshold, it sends a controlled OEM-like payload for the same `FLEXING` target so the end-to-end board/dashboard path can still be demonstrated.

Suggested operator sequence when Nam asks to run a demo:

```bash
cd /u01/app/agent_monitor

# 1) Confirm PDB state
scripts/demo_flexing/check_flexing_context.sh

# 2a) Long lock demo: 20m hold, alert every 5m
scripts/demo_flexing/run_lock_demo.sh

# Optional override example
LOCK_DEMO_HOLD_MINUTES=10 LOCK_DEMO_ALERT_EVERY_MINUTES=2 scripts/demo_flexing/run_lock_demo.sh

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

Realtime board:
- `/u01/app/agent_monitor/docs/flow_test_board.html`
- long lock flow writes a dedicated realtime track named:
  - `Realtime Lock Demo — FLEXING 20m / alert mỗi 5m`

Evidence artifacts:
- `/u01/app/agent_monitor/artifacts/demo_flexing/`
- lock demo writes holder/waiter logs, rolling state log, and per-round payload JSON files

Notes:
- `scripts/run_demo_flows.py` also targets `FLEXING` in payloads for board/demo consistency.
- Real final Google Chat visibility is still a manual room verification step if shell cannot read room history.
