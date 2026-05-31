#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/u01/app/agent_monitor')
STATUS_PATH = ROOT / 'docs' / 'flow_test_status.json'
ENV_PATH = ROOT / '.env.runtime'
RENDERER = ROOT / 'scripts' / 'render_flow_board.py'
PYTHON = ROOT / '.venv' / 'bin' / 'python'


def load_env(path: Path) -> dict[str, str]:
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')


def http_json(method: str, url: str, payload: dict | None = None, headers: dict[str, str] | None = None, timeout: int = 30) -> tuple[int, dict | str]:
    data = None
    req_headers = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload, separators=(',', ':')).encode()
        req_headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, method=method, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode(errors='replace')
            try:
                return resp.getcode(), json.loads(body)
            except Exception:
                return resp.getcode(), body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors='replace')
        try:
            return exc.code, json.loads(body)
        except Exception:
            return exc.code, body


def signed_headers(secret: str, payload: dict) -> dict[str, str]:
    body = json.dumps(payload, separators=(',', ':')).encode()
    return {'X-Signature': hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()}


def render_board() -> None:
    os.system(f"{PYTHON} {RENDERER} >/dev/null 2>&1")


def base_status() -> dict:
    return {
        'title': 'Agent Monitor Real Demo Flow Test',
        'updated_at': now(),
        'environment': {
            'agent_health': 'http://127.0.0.1:2020/health',
            'agent_oem_webhook': 'http://127.0.0.1:2020/webhook/oem',
            'agent_google_chat_command': 'http://127.0.0.1:2020/google-chat/command',
            'dashboard_data': 'http://127.0.0.1:2020/dashboard/data',
            'dashboard_audit': 'http://127.0.0.1:2020/dashboard/audit',
            'gateway_health_public': 'http://118.69.205.10:2222/health',
            'gateway_alerts_public': 'http://118.69.205.10:2222/agent/alerts',
            'gateway_google_chat_events_public': 'http://118.69.205.10:2222/google-chat/events',
        },
        'notes': [
            'Real demo runner sends signed OEM-like alerts through the live Agent endpoint.',
            'Dashboard/audit verification is DB-backed via incident_id/audit_id returned by APIs.',
            'Google Chat final room visibility remains manual_verify if room history is not observable from shell.',
        ],
        'tracks': [
            {'id': 'preflight', 'name': 'S0 Preflight', 'steps': [
                {'id': 's0_agent', 'label': 'Agent health', 'status': 'pending', 'detail': ''},
                {'id': 's0_gateway', 'label': 'Gateway health', 'status': 'pending', 'detail': ''},
            ]},
            {'id': 'inbound', 'name': 'OEM -> Agent -> Dashboard/Audit -> Gateway', 'steps': [
                {'id': 's2_cpu', 'label': 'S2 CPU threshold >= 90%', 'status': 'pending', 'detail': ''},
                {'id': 's3_session', 'label': 'S3 Session usage > 70% demo', 'status': 'pending', 'detail': ''},
                {'id': 's1_lock', 'label': 'S1 Application/blocking lock demo', 'status': 'pending', 'detail': ''},
                {'id': 's4_tablespace', 'label': 'S4 Tablespace threshold demo', 'status': 'pending', 'detail': ''},
            ]},
            {'id': 'reverse', 'name': 'Google Chat -> Gateway -> Agent -> Audit', 'steps': [
                {'id': 's5_status', 'label': 'S5 /status FLEXING command audit', 'status': 'pending', 'detail': ''},
                {'id': 's6_blocking_locks', 'label': 'S6 /blocking_locks FLEXING command audit', 'status': 'pending', 'detail': ''},
                {'id': 's7_unauthorized', 'label': 'S7 Unauthorized command rejection', 'status': 'pending', 'detail': ''},
            ]},
        ],
    }


def save(data: dict) -> None:
    data['updated_at'] = now()
    STATUS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    render_board()


def set_step(data: dict, step_id: str, status: str, detail: str) -> None:
    for track in data['tracks']:
        for step in track['steps']:
            if step['id'] == step_id:
                step['status'] = status
                step['detail'] = detail
                step['ended_at'] = now() if status in {'passed', 'failed', 'manual_verify', 'skipped'} else ''
    save(data)


def demo_payload(metric_name: str, metric_value: str, severity: str, message: str, rule_name: str | None = None, metric_column: str | None = None) -> dict:
    demo_id = f"DEMO-{int(time.time())}-{metric_name}"
    return {
        'source': 'oem',
        'target_name': 'FLEXING',
        'target_type': 'oracle_pdb',
        'severity': severity,
        'metric_name': metric_name,
        'metric_column': metric_column or metric_name,
        'metric_value': metric_value,
        'message': f'{demo_id} | {message}',
        'rule_name': rule_name,
        'occurred_at': now(),
    }


def send_oem(data: dict, step_id: str, payload: dict, secret: str, agent_oem: str) -> None:
    set_step(data, step_id, 'running', f"Sending {payload['metric_name']}={payload.get('metric_value')} to {agent_oem}")
    code, body = http_json('POST', agent_oem, payload, signed_headers(secret, payload), timeout=90)
    if code != 202 or not isinstance(body, dict):
        set_step(data, step_id, 'failed', f'HTTP {code}: {body}')
        return
    status = 'passed' if body.get('incident_id') else 'failed'
    detail = f"incident_id={body.get('incident_id')} gcp_sent={body.get('gcp_sent')} metric={payload['metric_name']} value={payload.get('metric_value')} message={payload['message']}"
    set_step(data, step_id, status, detail)


def send_command(data: dict, step_id: str, url: str, secret: str, command: str, user: str = 'nam.pham2@mservice.com.vn') -> None:
    set_step(data, step_id, 'running', f'Sending command {command} to Agent command endpoint')
    payload = {'command_text': command, 'user_email': user, 'space_name': 'spaces/DEMO', 'thread_name': 'spaces/DEMO/threads/FLOW', 'raw_event': {'type': 'MESSAGE'}}
    code, body = http_json('POST', url, payload, {'X-Gateway-Secret': secret}, timeout=30)
    if code == 202 and isinstance(body, dict) and body.get('job_id'):
        set_step(data, step_id, 'passed', f"job_id={body.get('job_id')} audit_id={body.get('audit_id')} command={command}")
    else:
        set_step(data, step_id, 'failed', f'HTTP {code}: {body}')


def send_bad_command(data: dict, step_id: str, url: str) -> None:
    set_step(data, step_id, 'running', 'Sending command with invalid gateway secret; expect HTTP 401')
    payload = {'command_text': '/status FLEXING', 'user_email': 'bad.actor@example.com'}
    code, body = http_json('POST', url, payload, {'X-Gateway-Secret': 'bad-secret'}, timeout=30)
    if code == 401:
        set_step(data, step_id, 'passed', f'Unauthorized rejected as expected: {body}')
    else:
        set_step(data, step_id, 'failed', f'Expected 401, got HTTP {code}: {body}')


def main() -> int:
    env = load_env(ENV_PATH)
    data = base_status()
    save(data)
    agent_health = data['environment']['agent_health']
    agent_oem = data['environment']['agent_oem_webhook']
    agent_cmd = data['environment']['agent_google_chat_command']
    gateway_health = data['environment']['gateway_health_public']
    webhook_secret = env['AGENT_WEBHOOK_SECRET']
    gateway_secret = env['GCP_GATEWAY_SHARED_SECRET']

    set_step(data, 's0_agent', 'running', agent_health)
    code, body = http_json('GET', agent_health)
    set_step(data, 's0_agent', 'passed' if code == 200 else 'failed', f'HTTP {code}: {body}')

    set_step(data, 's0_gateway', 'running', gateway_health)
    code, body = http_json('GET', gateway_health)
    set_step(data, 's0_gateway', 'passed' if code == 200 else 'failed', f'HTTP {code}: {body}')

    send_oem(data, 's2_cpu', demo_payload('cpuUtilization', '97', 'CRITICAL', 'CPU threshold breach demo', 'cpu_critical_90', 'cpuUtil'), webhook_secret, agent_oem)
    send_oem(data, 's3_session', demo_payload('sessionUsagePercent', '75', 'WARNING', 'Session usage above 70 percent demo', 'session_usage_demo_70'), webhook_secret, agent_oem)
    send_oem(data, 's1_lock', demo_payload('userBlockedSessionCount', '3', 'CRITICAL', 'Application lock/blocking session demo', 'blocking_lock'), webhook_secret, agent_oem)
    send_oem(data, 's4_tablespace', demo_payload('tablespaceUsedPercent', '91', 'CRITICAL', 'Tablespace threshold demo USERS 91 percent used', 'tablespace_critical'), webhook_secret, agent_oem)

    send_command(data, 's5_status', agent_cmd, gateway_secret, '/status FLEXING')
    send_command(data, 's6_blocking_locks', agent_cmd, gateway_secret, '/blocking_locks FLEXING')
    send_bad_command(data, 's7_unauthorized', agent_cmd)

    failed = [s for t in data['tracks'] for s in t['steps'] if s['status'] == 'failed']
    print(f"Flow board: {STATUS_PATH}")
    print(f"HTML board: {ROOT / 'docs' / 'flow_test_board.html'}")
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
