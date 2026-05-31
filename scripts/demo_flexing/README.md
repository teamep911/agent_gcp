# Demo FLEXING shortcuts

Chạy từ agent host:

```bash
cd /u01/app/agent_monitor
```

## 1) Lock demo — 5 phút / alert mỗi 1 phút

```bash
scripts/demo_flexing/run_lock_5m_1m.sh
```

Shortcut này tương đương:

```bash
LOCK_DEMO_HOLD_MINUTES=5 \
LOCK_DEMO_ALERT_EVERY_MINUTES=1 \
LOCK_DEMO_WAIT_SECONDS=360 \
scripts/demo_flexing/run_lock_demo.sh
```

Kết quả:
- tạo holder + waiter thật trên FLEXING
- capture owner / sql_id / sql_text / event
- gửi alert `blocking_lock`
- update board/audit theo flow demo

Artifacts:
- `/u01/app/agent_monitor/artifacts/demo_flexing/lock_holder_long_*.log`
- `/u01/app/agent_monitor/artifacts/demo_flexing/lock_waiter_long_*.log`
- `/u01/app/agent_monitor/artifacts/demo_flexing/lock_state_*.log`
- `/u01/app/agent_monitor/artifacts/demo_flexing/lock_payloads_*/`

## 2) Threshold demo — 5 phút / alert mỗi 1 phút

```bash
scripts/demo_flexing/run_threshold_5m_1m.sh
```

Shortcut này tương đương:

```bash
WORKERS=12 \
DURATION_SECONDS=300 \
ALERT_INTERVAL_SECONDS=60 \
ALERT_COUNT=5 \
WARMUP_SECONDS=20 \
MAX_CPU_CORES=10 \
THRESHOLD=90 \
scripts/demo_flexing/run_real_aas_threshold_5m_loop.sh
```

Kết quả:
- tạo active sessions thật trên FLEXING
- tính current từ `gv$session active count`
- gửi alert `cpu_critical_90`
- gateway publish AAS chart + Top SQL lên Google Chat

Artifacts:
- `/u01/app/agent_monitor/artifacts/demo_flexing/real_aas_5m_loop_*.log`
- `/u01/app/monitor/artifacts/perf/`
- `/u01/app/ggchat_app/media/perf/`

## 3) Threshold demo — 1 alert realtime

```bash
WORKERS=12 \
HOLD_SECONDS=240 \
WARMUP_SECONDS=60 \
MAX_CPU_CORES=10 \
THRESHOLD=90 \
scripts/demo_flexing/run_real_aas_threshold_alert.sh
```

## 4) Context check trước khi chạy

```bash
scripts/demo_flexing/check_flexing_context.sh
```

## 5) Board / status

- HTML board: `/u01/app/agent_monitor/docs/flow_test_board.html`
- JSON status: `/u01/app/agent_monitor/docs/flow_test_status.json`
