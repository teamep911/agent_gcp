# Live Test Status

Updated during cutover to project `/u01/app/agent_monitor`.

## Current runtime

### openclaw
- Service: `agent-monitor.service`
- Port: `2020`
- Health: `http://127.0.0.1:2020/health`
- Status: active

### gcp
- Service: `ggchat-app`
- Local/public bind port: `2222`
- Health local: `http://127.0.0.1:2222/health`
- Health public fallback: `http://118.69.205.10:2222/health`
- Status: active

## What was proven

### 1. OEM -> Agent
Synthetic signed OEM POST to Agent succeeded.

Result:
- HTTP `202`
- incident created: `incident_id=80`
- rule matched: `cpu_critical_90`
- RCA generated
- DB saved

### 2. Reverse flow GCP -> Agent command
Local GCP gateway event test succeeded.

Test:
- POST `http://127.0.0.1:2222/google-chat/events`
- authorized user: `nam.pham2@mservice.com.vn`
- command: `/status flex`

Result:
- HTTP `200`
- response text confirmed accepted command
- returned job id like `gchat-0669c7d82e5e`

### 3. Direct Agent command endpoint
Direct POST to Agent command endpoint succeeded.

Test:
- POST `http://127.0.0.1:2020/google-chat/command`
- with valid header `X-Gateway-Secret`

Result:
- HTTP `202`
- accepted with generated `job_id`

### 4. Public IP fallback path works
Because DNS `gcp.leevo.top` did not resolve from runtime hosts, temporary fallback was enabled using public IP and port 2222.

Current fallback path:
- Agent posts to `http://118.69.205.10:2222/agent/alerts`
- Public health: `http://118.69.205.10:2222/health`
- Google Chat event endpoint fallback: `http://118.69.205.10:2222/google-chat/events`

Changes applied:
- On `gcp`, `ggchat-app` now binds `0.0.0.0:2222`
- On `openclaw`, Agent env now has:
  - `GCP_GATEWAY_BASE_URL=http://118.69.205.10:2222`

Verification:
- `curl http://118.69.205.10:2222/health` -> OK
- Synthetic OEM webhook into Agent created `incident_id=81`
- Agent log confirmed:
  - `gcp_gateway.alert.sent`
  - URL `http://118.69.205.10:2222/agent/alerts`
  - `gcp_sent=true`

## Remaining caveat

Public IP fallback is plain HTTP, not HTTPS, and is only a temporary workaround until DNS/tunnel path is healthy.

Preferred final state remains:
- `https://gcp.leevo.top/agent/alerts`
- `https://gcp.leevo.top/google-chat/events`

## Runtime files changed during fallback

### openclaw
- `/u01/app/agent_monitor/.env.runtime`
  - `GCP_GATEWAY_BASE_URL=http://118.69.205.10:2222`
- backup:
  - `/u01/app/agent_monitor/.env.runtime.bak_ip_fallback_20260531_030623`

### gcp
- `/u01/app/ggchat_app/.env.runtime`
  - `GCP_GATEWAY_HOST=0.0.0.0`
  - `GCP_GATEWAY_PORT=2222`
  - `AGENT_MONITOR_BASE_URL=http://10.10.10.110:2020`
- backups:
  - `/u01/app/ggchat_app/.env.runtime.bak_20260531_021234`
  - `/u01/app/ggchat_app/.env.runtime.bak_bind_public_20260531_030543`
- `/u01/app/ggchat_app/app/main.py`
  - sends `X-Gateway-Secret` to Agent command endpoint
  - default Agent URL updated to port `2020`

## Next thing to do once DNS resolves

1. Restore Agent base URL to `https://gcp.leevo.top`
2. Optionally bind GCP gateway back to loopback only if tunnel is healthy
3. Re-test:
   - `curl -k https://gcp.leevo.top/health`
   - Agent alert post via domain
   - real Google Chat event via domain
4. Remove temporary public-IP fallback note from docs
