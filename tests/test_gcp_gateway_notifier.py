from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from urllib.parse import urlparse

from agent.adapters.gcp_gateway_adapter import build_signed_headers, build_gateway_alert_payload, send_alert_to_gcp


class FakeResponse:
    def __init__(self, status_code: int = 202):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


class FakeAsyncClient:
    calls = []

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, url, content=None, headers=None):
        self.calls.append({"url": url, "content": content, "headers": headers})
        return FakeResponse()


def test_build_signed_headers_uses_hmac_sha256():
    body = b'{"hello":"world"}'
    headers = build_signed_headers(body, "secret", nonce="nonce-1", timestamp="1710000000")

    expected = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert headers["X-Agent-Timestamp"] == "1710000000"
    assert headers["X-Agent-Nonce"] == "nonce-1"
    assert headers["X-Agent-Signature"] == f"sha256={expected}"


def test_build_gateway_alert_payload_contains_agent_processed_fields():
    event = {
        "target_name": "flex_flex",
        "target_type": "oracle_database",
        "severity": "CRITICAL",
        "metric_name": "cpuUtilization",
        "metric_value": "95",
        "metric_column": "CPU Used %",
        "message": "CPU high",
        "rule_name": "cpu_critical_90",
        "occurred_at": "2026-05-30T10:00:00Z",
    }
    payload = build_gateway_alert_payload(123, event, {"id": "cpu_critical_90"}, {"summary": "RCA"})

    assert payload["incident_id"] == 123
    assert payload["target_name"] == "flex_flex"
    assert payload["rule"] == {"id": "cpu_critical_90"}
    assert payload["rca"] == {"summary": "RCA"}
    assert payload["source"] == "agent_monitor"


def test_send_alert_to_gcp_posts_to_domain_not_raw_ip(monkeypatch):
    FakeAsyncClient.calls.clear()
    monkeypatch.setenv("GCP_GATEWAY_BASE_URL", "https://gcp.leevo.top")
    monkeypatch.setenv("GCP_GATEWAY_SHARED_SECRET", "secret")
    monkeypatch.setattr("agent.adapters.gcp_gateway_adapter.httpx.AsyncClient", FakeAsyncClient)

    ok = asyncio.run(send_alert_to_gcp(123, {"target_name": "flex_flex"}, {"id": "r"}, {"summary": "RCA"}))

    assert ok is True
    call = FakeAsyncClient.calls[0]
    assert call["url"] == "https://gcp.leevo.top/agent/alerts"
    parsed = urlparse(call["url"])
    assert not parsed.hostname.replace(".", "").isdigit()
    body = call["content"]
    headers = call["headers"]
    expected_sig = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert headers["X-Agent-Signature"] == f"sha256={expected_sig}"
    assert abs(int(headers["X-Agent-Timestamp"]) - int(time.time())) < 10
