#!/usr/bin/env python3
"""
Monitor_v2 — OEM OS Command Notification Wrapper
Script này được OEM Notification Rule gọi khi có alert.
OEM tự inject biến môi trường vào process.

Cách cấu hình trong OEM:
  1. OEM → Setup → Notifications → Notification Methods
  2. Create OS Command Method
  3. Command: /opt/monitor_v2/scripts/oem_notify_wrapper.py
  4. Gán method này vào Notification Rule tương ứng

Script nhận OEM env vars → build JSON → POST lên Agent webhook.
"""

import hashlib
import hmac
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

# ── Config (set qua environment hoặc hardcode cho script này) ─────────────────
AGENT_WEBHOOK_URL = os.getenv("MONITOR_AGENT_URL", "http://agent-server:8080/webhook/oem")
WEBHOOK_SECRET    = os.getenv("MONITOR_WEBHOOK_SECRET", "")


def _normalize_severity(value: str) -> str:
    value = (value or "WARNING").strip().upper()
    mapping = {
        "CR": "CRITICAL",
        "CRITICAL": "CRITICAL",
        "W": "WARNING",
        "WARNING": "WARNING",
        "WARN": "WARNING",
        "I": "INFO",
        "INFO": "INFO",
        "CLEAR": "CLEAR",
        "OK": "CLEAR",
    }
    return mapping.get(value, value)


def _normalize_metric_name(metric_name: str, metric_group: str, metric_column: str, message: str) -> str:
    metric_name = (metric_name or "").strip()
    metric_group = (metric_group or "").strip()
    metric_column = (metric_column or "").strip()
    message = (message or "").strip()
    haystack = " ".join([metric_name, metric_group, metric_column, message]).lower()

    if any(k in haystack for k in ["user block chain", "blocking session", "blocking lock", "row lock", "enq: tx"]):
        return "userBlockedSessionCount"
    if "cpu" in haystack:
        return "cpuUtilization"
    if "tablespace" in haystack:
        return "tablespaceUsedPercent"
    if "agent" in haystack and any(k in haystack for k in ["status", "unreachable", "down"]):
        return "agentStatus"
    if "session" in haystack and any(k in haystack for k in ["usage", "used", "limit", "%"]):
        return "sessionUsagePercent"

    return metric_name or ":".join([p for p in [metric_group, metric_column] if p]) or "unknown"


def get_oem_env() -> dict:
    """
    Đọc biến môi trường do OEM inject khi gọi OS Command Notification.
    Ref: OEM 13.5 Administrator's Guide — Notification OS Command variables.
    """
    raw_severity = os.getenv("SEVERITY", os.getenv("SEVERITY_SHORT", "WARNING"))
    raw_metric_name = os.getenv("METRIC_NAME", os.getenv("EVENT_NAME", ""))
    metric_group = os.getenv("METRIC_GROUP", "")
    metric_column = os.getenv("METRIC_COLUMN", "")
    message = os.getenv("MESSAGE", os.getenv("EMD_MESSAGE", os.getenv("EVENT_MSG", "")))
    return {
        "source":        "oem",
        "target_name":   os.getenv("EMD_TARGET_NAME", os.getenv("TARGET_NAME", "UNKNOWN")),
        "target_type":   os.getenv("EMD_TARGET_TYPE", os.getenv("TARGET_TYPE", "oracle_database")),
        "severity":      _normalize_severity(raw_severity),
        "metric_name":   _normalize_metric_name(raw_metric_name, metric_group, metric_column, message),
        "metric_value":  os.getenv("METRIC_VALUE", None),
        "metric_column": metric_column or None,
        "message":       message,
        "rule_name":     os.getenv("RULE_NAME", os.getenv("NOTIFICATION_RULE", None)),
        "occurred_at":   datetime.now(timezone.utc).isoformat(),
    }


def sign_payload(body: bytes) -> str:
    """HMAC-SHA256 signature cho webhook body."""
    if not WEBHOOK_SECRET:
        return ""
    return hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


def post_to_agent(payload: dict) -> bool:
    """POST JSON payload lên Agent webhook."""
    body = json.dumps(payload).encode("utf-8")
    sig  = sign_payload(body)

    req = urllib.request.Request(
        AGENT_WEBHOOK_URL,
        data=body,
        headers={
            "Content-Type":  "application/json",
            "X-Signature":   sig,
            "X-Source":      "oem-os-command",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.getcode()
            if status == 202:
                print(f"[OK] Agent accepted event for target: {payload.get('target_name')}")
                return True
            else:
                print(f"[WARN] Unexpected status: {status}", file=sys.stderr)
                return False
    except Exception as e:
        print(f"[ERROR] Failed to POST to agent: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    payload = get_oem_env()

    # Debug log (OEM ghi stdout vào notification log)
    print(f"[INFO] OEM notification: {payload['target_name']} | {payload['severity']} | {payload['metric_name']}")

    success = post_to_agent(payload)
    sys.exit(0 if success else 1)
