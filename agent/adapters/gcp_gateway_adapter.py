from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid

import httpx
import structlog

log = structlog.get_logger()
DEFAULT_GCP_GATEWAY_BASE_URL = "https://gcp.leevo.top"


def build_gateway_alert_payload(incident_id: int, event: dict, rule: dict, rca_result: dict | None) -> dict:
    return {
        "source": "agent_monitor",
        "incident_id": incident_id,
        "target_name": event.get("target_name"),
        "target_type": event.get("target_type", "oracle_database"),
        "severity": event.get("severity"),
        "metric_name": event.get("metric_name"),
        "metric_value": event.get("metric_value"),
        "metric_column": event.get("metric_column"),
        "message": event.get("message"),
        "rule_name": event.get("rule_name"),
        "occurred_at": event.get("occurred_at"),
        "rule": rule,
        "rca": rca_result,
    }


def build_signed_headers(body: bytes, secret: str, nonce: str | None = None, timestamp: str | None = None) -> dict[str, str]:
    nonce = nonce or str(uuid.uuid4())
    timestamp = timestamp or str(int(time.time()))
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-Agent-Timestamp": timestamp,
        "X-Agent-Nonce": nonce,
        "X-Agent-Signature": f"sha256={signature}",
    }


async def send_alert_to_gcp(incident_id: int, event: dict, rule: dict, rca_result: dict | None) -> bool:
    base_url = os.getenv("GCP_GATEWAY_BASE_URL", DEFAULT_GCP_GATEWAY_BASE_URL).rstrip("/")
    secret = os.getenv("GCP_GATEWAY_SHARED_SECRET", "")
    if not secret:
        log.warning("gcp_gateway.secret.not_configured")
        return False
    payload = build_gateway_alert_payload(incident_id, event, rule, rca_result)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = build_signed_headers(body, secret)
    url = f"{base_url}/agent/alerts"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(url, content=body, headers=headers)
            response.raise_for_status()
        log.info("gcp_gateway.alert.sent", incident_id=incident_id, url=url)
        return True
    except Exception as exc:
        log.warning("gcp_gateway.alert.failed", incident_id=incident_id, url=url, error=str(exc))
        return False
