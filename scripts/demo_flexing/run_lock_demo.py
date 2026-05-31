#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/u01/app/agent_monitor')
STATUS_PATH = ROOT / 'docs' / 'flow_test_status.json'
RENDERER = ROOT / 'scripts' / 'render_flow_board.py'
ENV_PATH = ROOT / '.env.runtime'
ARTIFACT_DIR = Path('/u01/app/agent_monitor/artifacts/demo_flexing')
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
DIR = Path(__file__).resolve().parent

HOLD_MINUTES = int(os.getenv('LOCK_DEMO_HOLD_MINUTES', '20'))
ALERT_EVERY_MINUTES = int(os.getenv('LOCK_DEMO_ALERT_EVERY_MINUTES', '5'))
WAIT_SECONDS = int(os.getenv('LOCK_DEMO_WAIT_SECONDS', '1200'))
PDB_NAME = os.getenv('PDB_NAME', 'FLEXING')
FLEX_HOST = os.getenv('FLEX_HOST', 'flex')
ORACLE_HOME_REMOTE = os.getenv('ORACLE_HOME_REMOTE', '/u01/app/19.0.0/oracle')
ORACLE_SID_REMOTE = os.getenv('ORACLE_SID_REMOTE', 'flex')
REMOTE_DIR = os.getenv('REMOTE_DIR', '/tmp/agent_monitor_demo_flexing')


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')


def load_env() -> dict[str, str]:
    env = {}
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def run(cmd: str, timeout: int = 300) -> str:
    return subprocess.check_output(cmd, shell=True, text=True, timeout=timeout)


def render_board() -> None:
    subprocess.run([str(ROOT / '.venv' / 'bin' / 'python'), str(RENDERER)], check=False)


def save_status(data: dict) -> None:
    data['updated_at'] = now()
    STATUS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    render_board()


def set_step(data: dict, step_id: str, status: str, detail: str) -> None:
    for track in data.get('tracks', []):
        for step in track.get('steps', []):
            if step.get('id') == step_id:
                step['status'] = status
                step['detail'] = detail
                if status in {'passed', 'failed', 'manual_verify', 'skipped'}:
                    step['ended_at'] = now()
    save_status(data)


def ensure_board() -> dict:
    if STATUS_PATH.exists():
        data = json.loads(STATUS_PATH.read_text())
    else:
        data = {
            'title': 'Agent Monitor Real Demo Flow Test',
            'updated_at': now(),
            'environment': {},
            'notes': [],
            'tracks': [],
        }
    track = next((t for t in data['tracks'] if t.get('id') == 'lock_realtime'), None)
    if not track:
        track = {
            'id': 'lock_realtime',
            'name': 'Realtime Lock Demo — FLEXING 20m / alert mỗi 5m',
            'steps': [
                {'id': 'lock_ctx', 'label': 'Check FLEXING context', 'status': 'pending', 'detail': ''},
                {'id': 'lock_start', 'label': 'Start holder/waiter sessions', 'status': 'pending', 'detail': ''},
                {'id': 'lock_evidence', 'label': 'Capture lock evidence sql_id/sql_text/owner', 'status': 'pending', 'detail': ''},
                {'id': 'lock_alert_loop', 'label': 'Repeat alert every 5 minutes while lock remains', 'status': 'pending', 'detail': ''},
                {'id': 'lock_finish', 'label': 'Finish / cleanup', 'status': 'pending', 'detail': ''},
            ],
        }
        data['tracks'].append(track)
    save_status(data)
    return data


def post_oem(payload: dict, secret: str) -> dict:
    body = json.dumps(payload, separators=(',', ':')).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        'http://127.0.0.1:2020/webhook/oem',
        data=body,
        method='POST',
        headers={'Content-Type': 'application/json', 'X-Signature': sig},
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode())


def prepare_remote() -> None:
    run(f"ssh {FLEX_HOST} \"mkdir -p '{REMOTE_DIR}/sql'\"")
    for name in ['assert_flexing_open.sql', 'hold_application_lock.sql', 'wait_application_lock.sql', 'check_application_lock.sql']:
        run(f"scp -q {DIR / 'sql' / name} {FLEX_HOST}:{REMOTE_DIR}/sql/{name}")


def sqlplus_remote(sql_name: str, *args: str, timeout: int = 300) -> str:
    arg_str = ' '.join([f"'{a}'" for a in args])
    cmd = (
        f"ssh {FLEX_HOST} \"ORACLE_HOME='{ORACLE_HOME_REMOTE}' ORACLE_SID='{ORACLE_SID_REMOTE}' "
        f"PATH='{ORACLE_HOME_REMOTE}/bin':\\$PATH sqlplus -s / as sysdba @{REMOTE_DIR}/sql/{sql_name} {arg_str}\""
    )
    return run(cmd, timeout=timeout)


def parse_evidence(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith(('HOLDER|', 'WAITER|')):
            continue
        prefix, rest = line.split('|', 1)
        parts = {'role': prefix}
        for token in rest.split('|'):
            if '=' in token:
                k, v = token.split('=', 1)
                parts[k] = v
        if prefix == 'WAITER':
            result = {
                'sql_id': parts.get('sql_id', '-'),
                'sql_text': parts.get('sql_text', '-'),
                'owner': parts.get('owner', '-'),
                'sid_serial': parts.get('sid_serial', '-'),
                'event': parts.get('event', '-'),
                'wait_class': parts.get('wait_class', '-'),
            }
    return result


def main() -> int:
    env = load_env()
    secret = env['AGENT_WEBHOOK_SECRET']
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    holder_log = ARTIFACT_DIR / f'lock_holder_long_{ts}.log'
    waiter_log = ARTIFACT_DIR / f'lock_waiter_long_{ts}.log'
    state_log = ARTIFACT_DIR / f'lock_state_{ts}.log'
    payload_dir = ARTIFACT_DIR / f'lock_payloads_{ts}'
    payload_dir.mkdir(parents=True, exist_ok=True)

    data = ensure_board()
    set_step(data, 'lock_ctx', 'running', 'Checking FLEXING open mode and preparing remote sql files')
    prepare_remote()
    ctx = sqlplus_remote('assert_flexing_open.sql', PDB_NAME)
    set_step(data, 'lock_ctx', 'passed', ctx.strip())

    hold_seconds = HOLD_MINUTES * 60
    set_step(data, 'lock_start', 'running', f'Starting holder for {HOLD_MINUTES}m and waiter loop on {PDB_NAME}')
    holder_cmd = (
        f"ssh {FLEX_HOST} \"ORACLE_HOME='{ORACLE_HOME_REMOTE}' ORACLE_SID='{ORACLE_SID_REMOTE}' "
        f"PATH='{ORACLE_HOME_REMOTE}/bin':\\$PATH sqlplus -s / as sysdba @{REMOTE_DIR}/sql/hold_application_lock.sql '{PDB_NAME}' '{hold_seconds}'\""
    )
    waiter_cmd = (
        f"ssh {FLEX_HOST} \"ORACLE_HOME='{ORACLE_HOME_REMOTE}' ORACLE_SID='{ORACLE_SID_REMOTE}' "
        f"PATH='{ORACLE_HOME_REMOTE}/bin':\\$PATH sqlplus -s / as sysdba @{REMOTE_DIR}/sql/wait_application_lock.sql '{PDB_NAME}' '{WAIT_SECONDS}'\""
    )
    holder = subprocess.Popen(holder_cmd, shell=True, stdout=holder_log.open('w'), stderr=subprocess.STDOUT)
    time.sleep(5)
    waiter = subprocess.Popen(waiter_cmd, shell=True, stdout=waiter_log.open('w'), stderr=subprocess.STDOUT)
    time.sleep(5)
    set_step(data, 'lock_start', 'passed', f'holder_pid={holder.pid} waiter_pid={waiter.pid} holder_log={holder_log} waiter_log={waiter_log}')

    set_step(data, 'lock_evidence', 'running', 'Capturing realtime lock evidence from gv$session + gv$sql')
    evidence_text = sqlplus_remote('check_application_lock.sql', PDB_NAME)
    state_log.write_text(evidence_text)
    evidence = parse_evidence(evidence_text)
    if not evidence:
        set_step(data, 'lock_evidence', 'failed', f'No waiter evidence found. state_log={state_log}')
        return 1
    ev_detail = f"owner={evidence['owner']} sql_id={evidence['sql_id']} wait_class={evidence['wait_class']} event={evidence['event']} sql_text={evidence['sql_text']} state_log={state_log}"
    set_step(data, 'lock_evidence', 'passed', ev_detail)

    set_step(data, 'lock_alert_loop', 'running', f'Lock loop started for {HOLD_MINUTES}m; repeat alert every {ALERT_EVERY_MINUTES}m')
    total_rounds = max(1, HOLD_MINUTES // ALERT_EVERY_MINUTES)
    incident_ids: list[int] = []
    for round_no in range(1, total_rounds + 1):
        if round_no > 1:
            time.sleep(ALERT_EVERY_MINUTES * 60)
        evidence_text = sqlplus_remote('check_application_lock.sql', PDB_NAME)
        state_log.write_text(state_log.read_text() + '\n\n===== ROUND %d %s =====\n%s' % (round_no, now(), evidence_text))
        evidence = parse_evidence(evidence_text)
        if not evidence:
            set_step(data, 'lock_alert_loop', 'manual_verify', f'Lock evidence disappeared before round {round_no}; previous incidents={incident_ids} state_log={state_log}')
            break
        payload = {
            'source': 'oem',
            'target_name': 'FLEXING',
            'target_type': 'oracle_pdb',
            'severity': 'CRITICAL',
            'metric_name': 'userBlockedSessionCount',
            'metric_column': 'userBlockedSessionCount',
            'metric_value': '1',
            'message': (
                f"REAL_FLEXING_LOCK_LONG_DEMO round={round_no}/{total_rounds} | owner={evidence['owner']} | "
                f"sql_id={evidence['sql_id']} | sql_text={evidence['sql_text']} | event={evidence['event']} | "
                f"state_log={state_log}"
            ),
            'rule_name': 'blocking_lock',
            'occurred_at': now(),
        }
        payload_path = payload_dir / f'lock_round_{round_no}.json'
        payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
        response = post_oem(payload, secret)
        incident_ids.append(int(response.get('incident_id', 0)))
        set_step(
            data,
            'lock_alert_loop',
            'running',
            f"round={round_no}/{total_rounds} incident_id={response.get('incident_id')} owner={evidence['owner']} sql_id={evidence['sql_id']} next_alert_in={ALERT_EVERY_MINUTES}m payload={payload_path}",
        )

    holder.wait(timeout=hold_seconds + 60)
    waiter.wait(timeout=WAIT_SECONDS + 120)
    set_step(data, 'lock_finish', 'passed', f'holder_done rc={holder.returncode} waiter_done rc={waiter.returncode} incidents={incident_ids} state_log={state_log}')
    if incident_ids:
        set_step(data, 'lock_alert_loop', 'passed', f'Completed {len(incident_ids)} repeated alerts; incidents={incident_ids} state_log={state_log}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
