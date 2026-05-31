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
    await write_audit_event(
        event_type="oem.alert.received",
        details={
            "target": payload.target_name,
            "severity": payload.severity,
            "metric_name": payload.metric_name,
            "metric_value": payload.metric_value,
            "message": payload.message,
        },
        user_name="OEM",
    )
    matched_rule = _rule_engine.match(event)
    if matched_rule:
        await write_audit_event(
            event_type="rule.matched",
            details={
                "target": payload.target_name,
                "metric_name": payload.metric_name,
                "rule_id": matched_rule.get("id"),
                "rule_name": matched_rule.get("name"),
            },
            user_name="OEM",
        )
    rca_result = _rca_engine.analyze(event, matched_rule) if matched_rule else None
    if rca_result:
        await write_audit_event(
            event_type="rca.generated",
            details={
                "target": payload.target_name,
                "metric_name": payload.metric_name,
                "summary": rca_result.get("summary") if isinstance(rca_result, dict) else None,
            },
            user_name="OEM",
        )
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
    await write_audit_event(
        event_type="incident.saved",
        details={
            "incident_id": incident_id,
            "target": payload.target_name,
            "severity": payload.severity,
            "metric_name": payload.metric_name,
            "metric_value": payload.metric_value,
        },
        user_name="OEM",
    )

    gcp_sent = False
    if matched_rule:
        if _should_capture_perf_bundle(event, matched_rule):
            bundle = await _capture_perf_bundle_flex()
            if bundle:
                event["perf_bundle"] = bundle
                event["threshold_value"] = _rule_threshold_value(matched_rule)
                log.info("perf_bundle.captured", incident_id=incident_id, png=bundle.get("aas_png"))
        gcp_sent = await send_alert_to_gcp(incident_id, event, matched_rule, rca_result)
        if gcp_sent:
            await mark_incident_notified(incident_id)
            await write_audit_event(
                event_type="notification.sent",
                details={
                    "incident_id": incident_id,
                    "target": payload.target_name,
                    "channel": "gcp_gateway",
                    "metric_name": payload.metric_name,
                },
                user_name="OEM",
            )
        else:
            await write_audit_event(
                event_type="notification.failed",
                details={
                    "incident_id": incident_id,
                    "target": payload.target_name,
                    "channel": "gcp_gateway",
                    "metric_name": payload.metric_name,
                },
                user_name="OEM",
            )
    await write_audit_event(
        event_type="oem_webhook_received",
        details={"incident_id": incident_id, "target": payload.target_name, "gcp_sent": gcp_sent},
        user_name="OEM",
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
    await _publish_perf_files_to_gateway(bundle)
    bundle["aas_image_url"] = _public_perf_url(bundle.get("aas_png"))
    bundle["top_sql"] = _top_sql_rows(bundle.get("top5_sql_csv"), limit=3)
    return bundle


async def _publish_perf_files_to_gateway(bundle: dict) -> None:
    target = os.getenv("GCP_GATEWAY_MEDIA_SSH_TARGET", "oracle@gcp")
    remote_dir = os.getenv("GCP_GATEWAY_MEDIA_DIR", "/u01/app/ggchat_app/media/perf")
    files = [bundle.get("aas_png"), bundle.get("aas_svg"), bundle.get("top5_sql_txt"), bundle.get("top5_sql_csv"), bundle.get("summary_path")]
    files = [str(Path(f)) for f in files if f and Path(f).exists()]
    if not files:
        return
    mkdir = await asyncio.create_subprocess_exec("ssh", target, "mkdir", "-p", remote_dir, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    await mkdir.communicate()
    if mkdir.returncode != 0:
        log.warning("perf_bundle.publish.mkdir_failed", target=target, remote_dir=remote_dir)
        return
    proc = await asyncio.create_subprocess_exec("scp", "-q", *files, f"{target}:{remote_dir}/", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        log.warning("perf_bundle.publish.failed", target=target, stderr=stderr.decode(errors="replace")[-1000:])
    else:
        log.info("perf_bundle.publish.ok", target=target, remote_dir=remote_dir, count=len(files))


def _rule_threshold_value(rule: dict) -> str | None:
    match = rule.get("match") or {}
    for key in ("metric_value_min", "metric_value_max", "threshold", "value"):
        if key in match:
            return str(match.get(key))
    return None


def _public_perf_url(path_value: str | None) -> str | None:
    if not path_value:
        return None
    filename = Path(path_value).name
    if not filename:
        return None
    base = os.getenv("GCP_GATEWAY_PUBLIC_BASE_URL", os.getenv("GCP_GATEWAY_BASE_URL", "")).rstrip("/")
    if not base:
        return None
    return f"{base}/media/perf/{filename}"


def _top_sql_rows(csv_path: str | None, limit: int = 3) -> list[dict]:
    if not csv_path:
        return []
    p = Path(csv_path)
    if not p.exists():
        return []
    import csv
    rows = []
    with p.open(newline="", errors="replace") as f:
        for row in csv.DictReader(f):
            if not (row.get("sql_id") or "").strip():
                continue
            rows.append({
                "owner": (row.get("username") or "-").strip(),
                "sql_id": (row.get("sql_id") or "-").strip(),
                "active_sessions": (row.get("active_sessions") or "-").strip(),
                "sql_text": (row.get("sql_text") or "-").strip()[:500],
            })
            if len(rows) >= limit:
                break
    return rows


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
