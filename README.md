# agent_gcp

Project riêng cho luồng OEM -> Agent Monitor -> GCP Gateway -> Google Chat.

Host chạy: openclaw (10.10.10.110), user oracle.
Folder chuẩn từ nay về sau: `/u01/app/agent_monitor`.

## Flow

1. OEM `umarket` gửi OS Command alert vào Agent:
   `POST /webhook/oem`
2. Agent validate HMAC, normalize/match rule/RCA, lưu incident.
3. Agent gửi alert đã xử lý sang GCP Gateway bằng domain:
   `POST https://gcp.leevo.top/agent/alerts`
4. GCP Gateway verify HMAC rồi gửi Google Chat.
5. Google Chat command đi về GCP, GCP relay vào Agent:
   `POST /google-chat/command`
6. Dashboard nằm trong cùng project mới này.

## Runtime

- App: `agent/main.py`
- Env runtime: `.env.runtime` (600, không commit secret)
- Systemd template: `infra/systemd/agent-monitor.service`
- OEM wrapper: `scripts/oem_notify_wrapper.py`
- Dashboard routes:
  - `/login`
  - `/dashboard`
  - `/dashboard/data`
  - `/dashboard/audit`

## Install

```bash
cd /u01/app/agent_monitor
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
sudo cp infra/systemd/agent-monitor.service /etc/systemd/system/agent-monitor.service
sudo systemctl daemon-reload
sudo systemctl enable --now agent-monitor.service
curl http://127.0.0.1:2020/health
```

Note: chưa cutover khỏi project cũ `/u01/app/monitor`; kiểm tra kỹ trước khi đổi OEM URL/service port.
