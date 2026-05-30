from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
from pathlib import Path

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from adapters.gcp_gateway_adapter import send_alert_to_gcp
from auth.audit import write_audit_event
from db.models import mark_incident_notified, save_incident
from engine.rca import RCAEngine
from engine.rule_engine import RuleEngine
from utils.masker import mask_payload

log = structlog.get_logger()
router = APIRouter()


class OEMPayload(BaseModel):
    source: str = "oem"
    target_name: str
    target_type: str = "oracle_database"
    severity: str
    metric_name: str
    metric_value: str | None = None
    metric_column: str | None = None
    message: str
    rule_name: str | None = None
    occurred_at: str


WEBHOOK_SECRET = os.getenv("AGENT_WEBHOOK_SECRET", "")
_rule_engine = RuleEngine(os.getenv("RULES_CONFIG_PATH", "/u01/app/agent_monitor/agent/config/rules.yaml"))
_rca_engine = RCAEngine()


def verify_signature(body: bytes, signature: str) -> bool:
    env = os.getenv("ENV", "prod").lower()
    if not WEBHOOK_SECRET:
        log.warning("webhook.secret.not_configured", env=env)
        return env in {"dev", "development", "lab", "test"}
    expected = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


@router.post("/oem", status_code=status.HTTP_202_ACCEPTED)
async def receive_oem_event(request: Request, payload: OEMPayload):
    body = await request.body()
    if not verify_signature(body, request.headers.get("X-Signature", "")):
        log.warning("webhook.invalid_signature", target=payload.target_name)
        raise HTTPException(status_code=401, detail="Invalid signature")

    event = payload.dict()
    safe_payload = mask_payload(event)
    matched_rule = _rule_engine.match(event)
    rca_result = _rca_engine.analyze(event, matched_rule) if matched_rule else None
    incident_id = await save_incident(
        target_name=payload.target_name,
        target_type=payload.target_type,
        severity=payload.severity,
        category=_categorize(payload.metric_name),
        metric_name=payload.metric_name,
        metric_value=payload.metric_value,
        message=payload.message,
        rule_name=payload.rule_name,
        raw_payload=safe_payload,
        rca_result=rca_result,
    )

    gcp_sent = False
    if matched_rule:
        gcp_sent = await send_alert_to_gcp(incident_id, event, matched_rule, rca_result)
        if gcp_sent:
            await mark_incident_notified(incident_id)
        if _should_capture_perf_bundle(event, matched_rule):
            bundle = await _capture_perf_bundle_flex()
            if bundle:
                log.info("perf_bundle.captured", incident_id=incident_id, png=bundle.get("aas_png"))

    await write_audit_event(
        event_type="oem_webhook_received",
        details={"incident_id": incident_id, "target": payload.target_name, "gcp_sent": gcp_sent},
    )
    return {"status": "accepted", "incident_id": incident_id, "gcp_sent": gcp_sent}


def _should_capture_perf_bundle(event: dict, rule: dict) -> bool:
    if os.getenv("PERF_BUNDLE_ENABLED", "true").lower() not in {"1", "true", "yes", "on"}:
        return False
    metric = (event.get("metric_name") or "").lower()
    target = (event.get("target_name") or "").lower()
    rule_id = (rule.get("id") or "").lower()
    return (target in {"flex", "flex_flex", "flexing"} or "flex" in target) and (
        any(k in metric for k in ["cpu", "sessionusage", "aas", "active_session"])
        or any(k in rule_id for k in ["cpu", "session_usage"])
    )


async def _capture_perf_bundle_flex() -> dict | None:
    script = os.getenv("PERF_BUNDLE_SCRIPT", "/u01/app/agent_monitor/scripts/perf_bundle/capture_perf_bundle_flex.sh")
    timeout = int(os.getenv("PERF_BUNDLE_TIMEOUT_SECONDS", "180"))
    if not Path(script).exists():
        log.warning("perf_bundle.script.missing", script=script)
        return None
    proc = await asyncio.create_subprocess_exec(
        script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        log.warning("perf_bundle.timeout", timeout=timeout)
        return None
    if proc.returncode != 0:
        log.warning(
            "perf_bundle.nonzero_exit",
            returncode=proc.returncode,
            stdout=stdout.decode(errors="replace")[-1000:],
            stderr=stderr.decode(errors="replace")[-1000:],
        )
        return None
    summary_path = stdout.decode(errors="replace").strip().splitlines()[-1]
    bundle = {"summary_path": summary_path, "summary": ""}
    p = Path(summary_path)
    if p.exists():
        for line in p.read_text(errors="replace").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                bundle[k.strip()] = v.strip()
        bundle["summary"] = "\n".join(p.read_text(errors="replace").splitlines()[1:4])
    return bundle


def _categorize(metric_name: str) -> str:
    metric_lower = metric_name.lower()
    if "cpu" in metric_lower:
        return "cpu"
    if "tablespace" in metric_lower or "storage" in metric_lower:
        return "tablespace"
    if "session" in metric_lower or "lock" in metric_lower:
        return "locking"
    if "memory" in metric_lower:
        return "memory"
    if "agent" in metric_lower:
        return "agent"
    return "other"
