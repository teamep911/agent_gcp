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
- Local port: `2222`
- Health: `http://127.0.0.1:2222/health`
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

## Current blocker

Public DNS name `gcp.leevo.top` still does NOT resolve from runtime hosts/tools at test time.

Observed failures:
- from openclaw: `curl https://gcp.leevo.top/health` -> `Could not resolve host`
- from gcp: `curl https://gcp.leevo.top/health` -> `Could not resolve host`
- browser tool: `ERR_NAME_NOT_RESOLVED`

Because of this, true public path is NOT yet proven:
- Agent -> `https://gcp.leevo.top/agent/alerts`
- Google Chat internet callback -> `https://gcp.leevo.top/google-chat/events`

## GCP gateway code changes applied

On host `gcp`, file `/u01/app/ggchat_app/app/main.py` was updated to:
- default Agent URL `http://10.10.10.110:2020`
- send header `X-Gateway-Secret` when posting `/google-chat/command`

Runtime env on `gcp` was updated:
- `AGENT_MONITOR_BASE_URL=http://10.10.10.110:2020`

## Next thing to test once DNS resolves

1. `curl -k https://gcp.leevo.top/health`
2. synthetic signed POST from openclaw to `https://gcp.leevo.top/agent/alerts`
3. real Google Chat event into `https://gcp.leevo.top/google-chat/events`
4. verify Google Chat thread reply callback path
