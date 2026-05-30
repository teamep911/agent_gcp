# Agent GCP Architecture

This document is the handoff note for future sessions. Read this first before changing runtime.

## Hosts and responsibilities

| Role | Host | IP | User | Folder | Responsibility |
|---|---|---:|---|---|---|
| OEM source | `umarket` | `10.10.10.112` | oracle/root by ops | OEM server | Emits OEM OS Command alerts |
| Agent brain | `openclaw` | `10.10.10.110` | `oracle` | `/u01/app/agent_monitor` | Validates OEM webhook, rule/RCA processing, DB persistence, dashboard, sends processed alert to GCP by domain |
| GCP gateway | `gcp` | `10.10.10.113` | `oracle` | `/u01/app/ggchat_app` | Public Google Chat gateway; verifies Agent HMAC; sends cards to Google Chat; relays Google Chat commands back to Agent |

## Current cutover state

Project old `/u01/app/monitor` is disabled:

- `monitor-v2-agent.service`: disabled/inactive
- `monitor-v2-dashboard.service`: disabled/inactive

Project new `/u01/app/agent_monitor` is active:

- `agent-monitor.service`: enabled/active
- Port: `2020`
- Health: `http://127.0.0.1:2020/health`
- Dashboard: `http://127.0.0.1:2020/login` and `/dashboard`

Backup before cutover:

- `/u01/app/backups/agent_cutover_20260531_014439`

## Runtime services

### openclaw / Agent

Systemd unit:

- `/etc/systemd/system/agent-monitor.service`
- Template in repo: `/u01/app/agent_monitor/infra/systemd/agent-monitor.service`

Important commands:

```bash
systemctl status agent-monitor.service --no-pager -l
journalctl -u agent-monitor.service -n 100 --no-pager
curl http://127.0.0.1:2020/health
```

### gcp / Google Chat gateway

SSH first:

```bash
ssh oracle@gcp
```

Runtime:

- Folder: `/u01/app/ggchat_app`
- Service: `ggchat-app.service`
- Local port: `127.0.0.1:2222`
- Cloudflare tunnel should map `gcp.leevo.top` directly to `http://localhost:2222`.

Check:

```bash
ssh oracle@gcp 'systemctl is-active ggchat-app cloudflared; curl http://127.0.0.1:2222/health'
```

## Logical flow

### Alert flow

1. OEM `umarket` runs OS Command wrapper for an alert.
2. Wrapper POSTs signed payload to Agent:
   - `POST http://10.10.10.110:2020/webhook/oem`
   - Header: `X-Signature: <hmac-sha256>` using `AGENT_WEBHOOK_SECRET`.
3. Agent `openclaw` validates OEM HMAC.
4. Agent masks payload, matches rule, runs RCA, persists incident to PostgreSQL.
5. If a rule matched, Agent sends processed alert to GCP using domain, not raw IP:
   - `POST https://gcp.leevo.top/agent/alerts`
   - Headers: `X-Agent-Timestamp`, `X-Agent-Nonce`, `X-Agent-Signature: sha256=<hmac>` using `GCP_GATEWAY_SHARED_SECRET`.
6. GCP gateway verifies Agent HMAC and sends Google Chat card/webhook.

### Command flow

1. Google Chat event hits GCP gateway:
   - `POST https://gcp.leevo.top/google-chat/events`
2. GCP validates domain/user and relays command to Agent:
   - `POST http://10.10.10.110:2020/google-chat/command`
   - Header: `X-Gateway-Secret: <same shared secret>`.
3. Agent accepts command and returns `202 accepted` with `job_id`.
4. Future implementation should execute approved DBA/OEM actions and callback to GCP `/agent/callback` for threaded Google Chat reply.

## Environment files

Do not commit runtime secrets.

Agent runtime:

- `/u01/app/agent_monitor/.env.runtime` mode `600`
- Required keys:
  - `AGENT_PORT=2020`
  - `PG_DSN=...`
  - `AGENT_WEBHOOK_SECRET=...`
  - `GCP_GATEWAY_BASE_URL=https://gcp.leevo.top`
  - `GCP_GATEWAY_SHARED_SECRET=...`
  - `DASHBOARD_JWT_SECRET=...`
  - `DASHBOARD_PASSWORD=...`

GCP gateway runtime:

- `/u01/app/ggchat_app/.env.runtime` mode `600`
- `AGENT_SHARED_SECRET` must equal Agent `GCP_GATEWAY_SHARED_SECRET`.
- `GOOGLE_CHAT_WEBHOOK_URL` must be real Google Chat webhook URL.

## Rollback

If new Agent fails and old service needs temporary restore:

```bash
sudo systemctl disable --now agent-monitor.service
sudo systemctl enable --now monitor-v2-agent.service monitor-v2-dashboard.service
curl http://127.0.0.1:8080/health
```

Prefer fixing `/u01/app/agent_monitor` instead of editing `/u01/app/monitor`.
