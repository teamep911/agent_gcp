# Full Demo Track Plan: OEM <-> Google Chat + Dashboard/Audit

Project root: `/u01/app/agent_monitor`
Last updated: 2026-05-31
Owner/operator: Nam DBA

## 1. Mục tiêu demo

Demo phải chứng minh đủ 4 lớp, không chỉ thấy message trên Google Chat:

1. OEM phát sinh event / metric alert.
2. Agent nhận webhook, normalize, rule/dedup, RCA, lưu DB.
3. Gateway chuyển tiếp sang Google Chat và nhận lệnh ngược từ Google Chat.
4. Dashboard + audit ghi nhận được từng bước: incident, notification, command, approval/execution/result.

Luồng cần demo:

- Forward: OEM -> Agent Monitor -> GCP Gateway -> Google Chat -> Dashboard/Audit evidence.
- Reverse: Google Chat -> GCP Gateway -> Agent Monitor -> DB/OEM/script action -> callback/result -> Dashboard/Audit evidence.

## 2. Runtime scope hiện tại

### Openclaw / Agent

- Service: `agent-monitor.service`
- Health: `http://127.0.0.1:2020/health`
- OEM webhook: `http://127.0.0.1:2020/webhook/oem`
- Google Chat command endpoint: `http://127.0.0.1:2020/google-chat/command`
- Dashboard: `http://127.0.0.1:2020/dashboard`
- Flow status API: `http://127.0.0.1:2020/dashboard/flow-status`

### GCP Gateway

- Service: `ggchat-app`
- Current fallback health: `http://118.69.205.10:2222/health`
- Current fallback alert receiver: `http://118.69.205.10:2222/agent/alerts`
- Current fallback Google Chat events: `http://118.69.205.10:2222/google-chat/events`
- Target final endpoint: `https://gcp.leevo.top` once DNS/tunnel is healthy.

## 3. Flow Test Board cần track thêm gì

Board hiện tại đã có A/B flow basic. Cần mở rộng thành board 4 lane:

### Lane A — OEM alert source

Mục tiêu: chứng minh alert từ OEM hoặc synthetic OEM-like payload đã được nhận đúng.

Fields cần hiển thị:

- Scenario ID
- Metric / alert type
- Target DB / target type
- Trigger mode: real OEM, synthetic webhook, manual threshold injection
- Payload fingerprint / nonce
- HTTP status từ Agent
- Incident ID trả về

### Lane B — Agent processing + DB persistence

Mục tiêu: chứng minh Agent không chỉ nhận alert mà còn xử lý và lưu DB.

Fields cần hiển thị:

- Normalize status
- Rule matched / not matched
- Dedup decision: new, duplicate, suppressed
- RCA generated: yes/no
- Incident DB row ID
- Notified flag
- Error nếu có

Evidence source:

- `incidents` table
- Agent journal: `rule_engine.matched`, `db.incident.saved`, `gcp_gateway.alert.sent`
- Dashboard `/dashboard/data`

### Lane C — Gateway + Google Chat delivery

Mục tiêu: chứng minh outbound delivery hoặc ít nhất gateway acceptance.

Fields cần hiển thị:

- Gateway receive status
- Google Chat send status: sent, failed, skipped, manual_verify
- Google Chat space/thread nếu observable
- Response code / error text
- Delivery timestamp

Evidence source:

- GCP gateway log
- Agent notifier result
- Manual confirmation trong Google Chat khi shell không đọc được room history.

### Lane D — Reverse command + audit

Mục tiêu: chứng minh lệnh từ Google Chat được audit trước/sau khi chạy.

Fields cần hiển thị:

- User/email
- Command text
- Authorization result
- Audit ID
- Approval state nếu command nguy hiểm
- Execution status: pending, executed, failed, timeout
- Callback status về Google Chat
- Dashboard audit row visible: yes/no

Evidence source:

- `audit_log` table
- `/dashboard/audit`
- Agent journal: `google_chat.command.accepted`, `audit.command_created`, `audit.status_updated`

## 4. Demo scenarios chi tiết

### S0 — Preflight

Purpose: đảm bảo demo không fail vì runtime chết.

Steps:

1. Check Agent service active.
2. Check Agent health.
3. Check Gateway service active.
4. Check Gateway health public/fallback.
5. Check DB pool ready by loading dashboard data.
6. Check Flow status API readable.
7. Check shared secret configured both sides.

Pass criteria:

- Agent health HTTP 200.
- Gateway health HTTP 200.
- Dashboard `/dashboard/data` trả JSON.
- Flow board status JSON cập nhật được.

Dashboard/audit evidence:

- No incident required.
- Board lane S0 marks `passed` with timestamp.

### S1 — Lock application / blocking lock

Purpose: demo nhóm sự cố application lock/blocking session.

Trigger options:

- Preferred real DB lab: tạo blocker session trên FLEXING bằng `select ... for update`, session khác wait update cùng row.
- Safe synthetic: POST OEM payload metric/message có category `lock`, metric `blocking_sessions`, severity `CRITICAL`.

Expected payload fields:

- `target_name=FLEX`
- `target_type=oracle_database`
- `severity=CRITICAL`
- `metric_name=blocking_sessions` hoặc OEM metric tương ứng
- `metric_value>=1`
- `message` chứa blocker/waiter/session info nếu có
- unique `demo_id`

Expected Agent behavior:

- Rule match: `lock_blocking_session` hoặc tương đương.
- Category: `lock` / `availability`.
- Incident saved.
- RCA should include blocker/waiter, SQL_ID nếu payload/query có đủ info.
- Notification sent to Gateway.

Dashboard evidence:

- `/dashboard/data` recent incidents có row mới:
  - target FLEX
  - severity CRITICAL
  - metric blocking_sessions
  - message chứa demo_id
  - notified=true sau khi gửi gateway thành công

Audit evidence:

- Nếu chỉ là alert inbound: audit event dạng system nên ghi `oem.alert.received` / `incident.created` / `notification.sent`.
- Nếu reverse command `/blocking_locks FLEX` được gọi từ Chat: audit_log phải có command `/blocking_locks`, user Nam, status executed/failed.

### S2 — Threshold breach / CPU > threshold

Purpose: demo vượt ngưỡng threshold kiểu CPU/AAS/Tablespace.

Trigger options:

- Synthetic current proven path: payload `metric_name=cpuUtilization`, `metric_value=97`, `rule_name=cpu_critical_90`.
- Real OEM: tạo metric alert từ OEM nếu có rule threshold trên target.

Expected Agent behavior:

- Rule match: `cpu_critical_90`.
- Incident saved.
- RCA generated.
- Gateway sent.

Dashboard evidence:

- KPI critical tăng +1.
- Recent incidents có metric `cpuUtilization`, value `97`, rule `cpu_critical_90`.
- Category breakdown tăng category tương ứng.
- Hourly chart tăng count giờ hiện tại.

Audit evidence:

- System audit rows:
  - `oem.alert.received`
  - `rule.matched`
  - `incident.saved`
  - `notification.sent`

### S3 — Session usage > 70%

Purpose: demo ngưỡng session vượt 70%.

Trigger options:

- Real DB lab: mở nhiều session tới PDB FLEXING cho đến khi ratio session_current/session_limit > 70% nếu lab cho phép.
- Safe synthetic: payload `metric_name=session_usage_pct`, `metric_value=75`, severity WARNING/CRITICAL tùy rule.

Expected Agent behavior:

- Rule match: `session_usage_gt_70`.
- Incident category: `capacity` / `session`.
- RCA suggests top sessions/user/program if enrichment available.
- Notification sent.

Dashboard evidence:

- Recent incident row: metric `session_usage_pct`, value `75`, target FLEX.
- KPI warning/critical tăng.
- Notified=true.

Audit evidence:

- For inbound alert: system audit event.
- For Chat command `/sessions FLEX` hoặc `/status flex`: command audit row with user/email and status.

### S4 — Tablespace / disk threshold

Purpose: demo thêm một threshold phổ biến ngoài CPU/session.

Trigger options:

- Synthetic: `metric_name=tablespace_used_pct`, `metric_value=91`, message includes tablespace name.
- Real lab: tạo/resize temp tablespace only nếu có sandbox và đã backup/snapshot.

Expected behavior:

- Rule match: `tablespace_used_90`.
- Incident saved + notified.
- Dashboard category capacity/storage tăng.

### S5 — Reverse command: `/status flex`

Purpose: demo Google Chat -> Gateway -> Agent chiều ngược lại.

Steps:

1. Send Google Chat message `/status flex` from allowed user.
2. Gateway verifies user/domain.
3. Gateway forwards to Agent `/google-chat/command` with `X-Gateway-Secret`.
4. Agent returns `job_id`.
5. Agent writes audit row.
6. If execution worker exists: update audit status executed and callback result to Gateway/Chat.

Expected dashboard/audit evidence:

- `/dashboard/audit` has row:
  - user_name/email: Nam
  - command: `/status flex`
  - target: flex/FLEX
  - status: pending then executed, or accepted/pending if execution worker not implemented yet
  - created_at visible
  - executed_at visible after run

### S6 — Reverse command: `/blocking_locks FLEX`

Purpose: close the loop with lock scenario.

Steps:

1. Create lock/blocker from S1.
2. Send `/blocking_locks FLEX` in Google Chat.
3. Gateway forwards command.
4. Agent runs safe read-only SQL/script.
5. Result callback to Google Chat.
6. Dashboard audit records executed status.

Expected evidence:

- Chat result includes blocker/waiter info.
- Audit row command `/blocking_locks`, status `executed`.
- If command fails due missing worker, row must show `failed` with error, not disappear.

### S7 — Unauthorized / denied command

Purpose: chứng minh RBAC/audit hoạt động.

Steps:

1. Send synthetic Google Chat event with unauthorized email/domain.
2. Gateway rejects or Agent rejects.
3. Audit records denied event.

Expected evidence:

- HTTP response explains unauthorized.
- Audit row status `rejected` or system event `auth.denied`.
- No DB action executed.

### S8 — Failure path / gateway down or Google Chat send fail

Purpose: demo failure visible, không silent.

Steps:

1. Temporarily point gateway URL to invalid endpoint in test-only env, or simulate notifier exception.
2. Send synthetic OEM alert.
3. Agent saves incident but notifier fails.
4. Dashboard shows incident with notified=false or notification_status=failed.
5. Audit/system event records failure.

Expected evidence:

- Incident still saved.
- Notification failure visible in board and audit.
- No false `sent` status.

## 5. Dashboard cần bổ sung để demo rõ

### Existing

Dashboard hiện đã có:

- `/dashboard/data`: KPI, recent incidents, daily/hourly chart, category breakdown.
- `/dashboard/audit`: audit entries + stats.
- `/dashboard/flow-status`: JSON cho flow board.

### Gap cần bổ sung

1. Incident detail drilldown

Hiện recent incidents chỉ trả list rút gọn. Demo cần click incident để xem:

- raw_payload
- rca_result
- rule_name
- notified
- created_at
- related notification/audit events

Proposed endpoint:

- `GET /dashboard/incidents/{id}`

2. Notification status/audit

Hiện `incidents.notified=true/false` chưa đủ. Cần bảng hoặc audit event cho notifier:

- incident_id
- channel: gcp_gateway/google_chat
- status: sent/skipped/failed/manual_verify
- endpoint masked
- response_code
- error_message
- created_at

Nếu chưa tạo bảng riêng, trước mắt ghi vào `audit_log` bằng `write_audit_event()`:

- `notification.sent`
- `notification.failed`
- `notification.skipped`

3. Flow board embedded in dashboard

Hiện có HTML riêng `docs/flow_test_board.html` và API `/dashboard/flow-status`. Nên thêm tab/section trong `/dashboard`:

- lane status realtime polling mỗi 2 giây
- link đến latest incident_id/audit_id
- demo scenario selector/filter

4. Audit cho inbound alert

`audit_log` hiện thiên về command. Cần ghi system events cho inbound pipeline:

- `oem.alert.received`
- `rule.matched`
- `incident.saved`
- `rca.generated`
- `notification.sent/failed`

5. Audit cho denied/failed reverse command

Phải thấy được cả reject/fail/timeout, không chỉ command thành công.

## 6. Audit model đề xuất

Dùng `audit_log` hiện tại trước để nhanh demo, không cần migration lớn ngay.

Mapping đề xuất:

### Inbound OEM event

- user_id: `system`
- user_name: `OEM`
- command: event name, ví dụ `oem.alert.received`
- params: JSON chứa demo_id, target, metric, value, severity, incident_id nếu có
- target_name: target DB
- status: `system`, `sent`, `failed`, hoặc `created`

### Reverse Google Chat command

- user_id: Google Chat user email/id
- user_name: display name/email
- command: `/status`, `/blocking_locks`, `/sessions`
- params: command args + space/thread/job_id
- target_name: FLEX/flex
- status lifecycle:
  - `pending`: accepted, waiting execution
  - `approved`: if dangerous command requires approval
  - `executed`: completed successfully
  - `failed`: command ran but failed
  - `rejected`: RBAC/approval denied
  - `timeout`: no result in timeout window

## 7. Flow board status schema đề xuất

Add fields per step:

```json
{
  "id": "s2_a4",
  "scenario": "S2_THRESHOLD_CPU",
  "lane": "agent_processing",
  "label": "Verify incident saved and dashboard visible",
  "status": "passed",
  "started_at": "2026-05-31T10:00:00+07:00",
  "ended_at": "2026-05-31T10:00:03+07:00",
  "detail": "incident_id=123 rule=cpu_critical_90 notified=true",
  "evidence": {
    "incident_id": 123,
    "audit_id": 456,
    "dashboard_url": "/dashboard",
    "api": "/dashboard/data"
  }
}
```

Statuses:

- `pending`
- `running`
- `passed`
- `failed`
- `manual_verify`
- `skipped`

## 8. Implementation tasks để board đủ track

### T1 — Update test plan/board data

- Expand `docs/flow_test_status.json` from 2 tracks to scenario-based lanes.
- Add scenarios S0-S8.
- Add evidence fields: incident_id, audit_id, metric, target, dashboard_check.

### T2 — Update runner

File: `scripts/run_flow_tests.py`

Add payload templates:

- lock/blocking session
- CPU threshold
- session usage >70%
- tablespace threshold
- unauthorized command
- notifier failure simulation if safe

Add verification functions:

- query `/dashboard/data` for latest incident by demo_id
- query `/dashboard/audit` for command/system events
- optionally query DB directly for incident_id/audit_id when API not enough

### T3 — Add system audit writes

Files likely touched:

- `agent/handlers/webhook_handler.py`
- `agent/engine/rule_engine.py` or main flow area
- `agent/adapters/gcp_gateway_adapter.py`
- `agent/auth/audit.py`

Minimum events:

- `oem.alert.received`
- `rule.matched`
- `incident.saved`
- `notification.sent`
- `notification.failed`
- `google_chat.command.received`
- `google_chat.command.rejected`

### T4 — Add incident detail API

File: `agent/web/dashboard_api.py`

Add:

- `GET /dashboard/incidents/{incident_id}`

Return:

- main incident columns
- raw_payload JSON
- rca_result JSON
- related audit rows by incident_id/demo_id if present in params

### T5 — Embed flow board in dashboard

Files likely touched:

- `agent/templates/dashboard.html`
- `agent/web/dashboard_api.py`

Add a tab/section:

- Flow Test Board
- auto-refresh `/dashboard/flow-status`
- scenario cards + evidence links

### T6 — Real DB scenario scripts, read-only first

Create under:

- `scripts/demo_scenarios/`

Scripts:

- `check_sessions_pct.sql` read-only
- `check_blocking_locks.sql` read-only
- optional `create_blocking_lock_lab.sql` only for lab schema, clearly marked DANGER/DEMO

Because anh Nam prefers backup before production-like changes, any state-changing lock/table setup must be lab-only and explicitly confirmed.

## 9. Demo run order đề xuất

1. S0 Preflight.
2. S2 CPU threshold synthetic: fastest proof full forward flow.
3. S3 Session >70 synthetic: proves threshold variant.
4. S1 Lock synthetic or real lab lock: proves application issue class.
5. Open Dashboard:
   - KPI changed
   - Recent incidents show 3 demo rows
   - Category breakdown changed
   - Flow board lanes passed/manual_verify
6. Open Audit:
   - system events for alert received/rule/incident/notifier
7. S5 `/status flex` from Google Chat or synthetic event:
   - command accepted
   - audit row visible
8. S6 `/blocking_locks FLEX` if command worker/read-only SQL exists.
9. S7 unauthorized event:
   - rejected visible in audit
10. Optional S8 failure path:
   - incident saved but notification failed visible.

## 10. Acceptance criteria

### Demo-ready minimum

- S0 passed.
- At least 3 inbound scenarios passed: CPU threshold, session >70, lock/blocking.
- Each inbound scenario has:
  - incident_id
  - dashboard recent incident visible
  - audit/system event visible
  - gateway accepted or Google Chat manual verification noted
- Reverse `/status flex` creates audit row.
- Flow board shows current status and evidence IDs.

### Full demo success

- Real Google Chat room message is visible for forward alert.
- Real Google Chat command is sent from room, not only synthetic POST.
- Agent command execution finishes and callback result appears in Chat.
- Audit lifecycle changes from pending -> executed/failed/timeout.
- Incident detail page shows raw_payload + RCA.

## 11. Known caveats

1. Final Google Chat delivery may require manual verification because shell may not read Google Chat room history.
2. Current fallback endpoint is plain HTTP public IP `118.69.205.10:2222`; final target should be HTTPS domain.
3. Current reverse command pipeline may accept command and return job_id before full execution worker/callback is complete.
4. Shell environment currently prints `LD_PRELOAD=/tmp/evil.so` warning. This must be treated as environment compromise/noise risk and should be cleaned before production demo scripts are finalized.

## 12. Quick evidence commands

```bash
cd /u01/app/agent_monitor

# Run existing E2E board runner
.venv/bin/python scripts/run_flow_tests.py

# Health
curl -s http://127.0.0.1:2020/health
curl -s http://118.69.205.10:2222/health

# Dashboard APIs require login cookie in browser, but endpoint names are:
# /dashboard/data
# /dashboard/audit
# /dashboard/flow-status

# Agent logs
sudo journalctl -u agent-monitor.service -n 120 --no-pager

# GCP gateway quick check
ssh oracle@gcp 'hostname; systemctl is-active ggchat-app; curl -s http://127.0.0.1:2222/health; tail -n 120 /u01/app/ggchat_app/logs/gateway.err.log 2>/dev/null || true'
```
