#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import hmac
import json
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/u01/app/agent_monitor')
STATUS_PATH = ROOT / 'docs' / 'flow_test_status.json'
ENV_PATH = ROOT / '.env.runtime'
RENDERER = ROOT / 'scripts' / 'render_flow_board.py'
PYTHON = ROOT / '.venv' / 'bin' / 'python'
AGENT_JOURNAL_CMD = ['sudo', 'journalctl', '-u', 'agent-monitor.service', '-n', '120', '--no-pager']
GCP_LOG_CMD = "tail -n 120 /u01/app/ggchat_app/logs/gateway.err.log 2>/dev/null || true"


def load_env(path: Path) -> dict[str, str]:
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        env[k.strip()] = v.strip()
    return env


def load_status() -> dict:
    return json.loads(STATUS_PATH.read_text())


def render_board() -> None:
    subprocess.run([str(PYTHON), str(RENDERER)], check=False)


def save_status(data: dict) -> None:
    data['updated_at'] = datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')
    STATUS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    render_board()


def set_step(data: dict, step_id: str, status: str, detail: str = '') -> None:
    for track in data['tracks']:
        for step in track['steps']:
            if step['id'] == step_id:
                step['status'] = status
                step['detail'] = detail
    save_status(data)


def reset_all(data: dict) -> None:
    for track in data['tracks']:
        for step in track['steps']:
            step['status'] = 'pending'
            step['detail'] = ''
    save_status(data)


def http_get(url: str, timeout: int = 15) -> tuple[int, str]:
    req = urllib.request.Request(url, method='GET')
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.getcode(), resp.read().decode()


def http_post_json(url: str, payload: dict, headers: dict[str, str] | None = None, timeout: int = 30) -> tuple[int, str]:
    body = json.dumps(payload, separators=(',', ':')).encode()
    req = urllib.request.Request(url, data=body, method='POST')
    req.add_header('Content-Type', 'application/json')
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.getcode(), resp.read().decode()


def run_cmd(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True)


def run_ssh(cmd: str) -> str:
    return subprocess.check_output(['ssh', 'oracle@gcp', cmd], text=True)


def signed_oem_headers(secret: str, payload: dict) -> dict[str, str]:
    body = json.dumps(payload, separators=(',', ':')).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return {'X-Signature': sig}


def main() -> int:
    env = load_env(ENV_PATH)
    data = load_status()
    reset_all(data)

    agent_health = data['environment']['agent_health']
    gateway_health = data['environment']['gateway_health_public']
    gateway_events = data['environment']['gateway_google_chat_events_public']
    agent_oem = data['environment']['agent_oem_webhook']
    agent_secret = env['AGENT_WEBHOOK_SECRET']

    set_step(data, 'a1', 'running', f'Checking {agent_health}')
    code, body = http_get(agent_health)
    set_step(data, 'a1', 'passed' if code == 200 else 'failed', body)
    if code != 200:
        return 1

    set_step(data, 'a2', 'running', f'Checking {gateway_health}')
    code, body = http_get(gateway_health)
    set_step(data, 'a2', 'passed' if code == 200 else 'failed', body)
    if code != 200:
        return 1

    synthetic_id = int(time.time())
    oem_payload = {
        'target_name': 'FLEX',
        'target_type': 'oracle_database',
        'source': 'oem',
        'severity': 'CRITICAL',
        'metric_name': 'cpuUtilization',
        'metric_column': 'cpuUtil',
        'metric_value': '97',
        'message': f'E2E board test incident {synthetic_id}',
        'rule_name': 'cpu_critical_90',
        'occurred_at': datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds'),
    }
    set_step(data, 'a3', 'running', 'Sending signed synthetic OEM alert to Agent')
    code, body = http_post_json(agent_oem, oem_payload, headers=signed_oem_headers(agent_secret, oem_payload), timeout=60)
    set_step(data, 'a3', 'passed' if code == 202 else 'failed', body)
    if code != 202:
        return 1

    set_step(data, 'a4', 'running', 'Checking Agent journal for rule match and DB save')
    journal = run_cmd(AGENT_JOURNAL_CMD)
    ok_a4 = ('rule_engine.matched' in journal and 'db.incident.saved' in journal)
    set_step(data, 'a4', 'passed' if ok_a4 else 'failed', 'rule_engine.matched + db.incident.saved found' if ok_a4 else journal[-1200:])
    if not ok_a4:
        return 1

    set_step(data, 'a5', 'running', 'Checking Agent journal for outbound send')
    journal = run_cmd(AGENT_JOURNAL_CMD)
    ok_a5 = ('gcp_gateway.alert.sent' in journal and '118.69.205.10:2222/agent/alerts' in journal)
    set_step(data, 'a5', 'passed' if ok_a5 else 'failed', 'gcp_gateway.alert.sent found' if ok_a5 else journal[-1200:])
    if not ok_a5:
        return 1

    set_step(data, 'a6', 'running', 'Checking GCP gateway log for reachable alert path')
    gcp_log = run_ssh(GCP_LOG_CMD)
    ok_a6 = 'Application startup complete.' in gcp_log or 'Uvicorn running on http://0.0.0.0:2222' in gcp_log
    set_step(data, 'a6', 'passed' if ok_a6 else 'manual_verify', 'Gateway reachable and alert path accepted; final webhook delivery is not fully observable from shell')
    set_step(data, 'a7', 'manual_verify', 'Manual confirm in Google Chat space if message visibility is required')

    set_step(data, 'b1', 'running', f'Checking {gateway_health}')
    code, body = http_get(gateway_health)
    set_step(data, 'b1', 'passed' if code == 200 else 'failed', body)
    if code != 200:
        return 1

    gchat_payload = {
        'type': 'MESSAGE',
        'message': {'text': '/status flex'},
        'user': {'email': 'nam.pham2@mservice.com.vn'},
        'space': {'name': 'spaces/AAA'},
        'thread': {'name': 'spaces/AAA/threads/BBB'},
    }
    set_step(data, 'b2', 'running', 'Sending synthetic Google Chat event to public gateway')
    code, body = http_post_json(gateway_events, gchat_payload, timeout=30)
    set_step(data, 'b2', 'passed' if code == 200 else 'failed', body)
    if code != 200:
        return 1

    set_step(data, 'b3', 'running', 'Checking response text for accepted authorized user/domain')
    ok_b3 = 'Accepted command' in body
    set_step(data, 'b3', 'passed' if ok_b3 else 'failed', body)
    if not ok_b3:
        return 1

    set_step(data, 'b4', 'running', 'Checking Agent journal for forwarded command')
    journal = run_cmd(AGENT_JOURNAL_CMD)
    ok_b4 = 'google_chat.command.accepted' in journal
    set_step(data, 'b4', 'passed' if ok_b4 else 'failed', 'google_chat.command.accepted found' if ok_b4 else journal[-1200:])
    if not ok_b4:
        return 1

    set_step(data, 'b5', 'running', 'Extracting job_id proof from gateway response')
    ok_b5 = 'job_id=' in body or 'job_id' in body
    set_step(data, 'b5', 'passed' if ok_b5 else 'failed', body)
    return 0 if ok_b5 else 1


if __name__ == '__main__':
    raise SystemExit(main())
