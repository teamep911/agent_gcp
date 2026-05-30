# Agent GCP Workflow Runbook

Read this file at the start of any future session working on this project.

## Project identity

Only use this folder for the new project:

- `/u01/app/agent_monitor`

Do not continue implementing new Google Chat/GCP work in:

- `/u01/app/monitor` (legacy Telegram project)

## First checks every session

Run these first:

```bash
hostname
id
systemctl is-active agent-monitor.service
curl http://127.0.0.1:2020/health
```

If working on GCP gateway, SSH there immediately:

```bash
ssh oracle@gcp 'hostname; systemctl is-active ggchat-app cloudflared; curl http://127.0.0.1:2222/health'
```

## Source of truth

- Agent app: `/u01/app/agent_monitor/agent`
- OEM wrapper: `/u01/app/agent_monitor/scripts/oem_notify_wrapper.py`
- Agent env: `/u01/app/agent_monitor/.env.runtime`
- Agent systemd template: `/u01/app/agent_monitor/infra/systemd/agent-monitor.service`
- Architecture note: `/u01/app/agent_monitor/docs/ARCHITECTURE.md`
- Diagram: `/u01/app/agent_monitor/docs/DIAGRAM.md`
- GitHub repo: `git@github.com:teamep911/agent_gcp.git`

## Common tasks

### Restart Agent service

```bash
cd /u01/app/agent_monitor
sudo systemctl restart agent-monitor.service
systemctl status agent-monitor.service --no-pager -l
curl http://127.0.0.1:2020/health
```

### Run tests

```bash
cd /u01/app/agent_monitor
.venv/bin/python -m pytest -q tests/test_gcp_gateway_notifier.py tests/test_google_chat_command_api.py
```

### Push changes

```bash
cd /u01/app/agent_monitor
git status --short
git add <files>
git commit -m "<message>"
git push origin main
```

Before pushing, verify secrets are not staged:

```bash
git check-ignore -v .env.runtime
```

## Current implemented scope

Implemented:
- OEM webhook intake on Agent
- HMAC verification for OEM payloads
- rule engine + RCA + DB persistence
- send processed alert from Agent to GCP by domain
- Google Chat command ingress endpoint on Agent
- dashboard/login pages moved into new project
- new service `agent-monitor.service` on port `2020`

Not fully completed yet:
- full real Google Chat end-to-end proof with resolvable `gcp.leevo.top`
- real command execution pipeline after `/google-chat/command`
- callback path from Agent execution result to GCP `/agent/callback`

## Operational warnings

1. Shell has noisy `LD_PRELOAD=/tmp/evil.so` warnings. They are environment noise, not app logic, but can pollute file writes if not careful.
2. If the user says “handle it on GCP”, SSH to `oracle@gcp` first.
3. Always use domain `https://gcp.leevo.top` for Agent -> GCP posting; do not silently fall back to raw IP/port.
4. Keep `GCP_GATEWAY_SHARED_SECRET` on openclaw synchronized with `AGENT_SHARED_SECRET` on gcp.
