"""
GCP Gateway — Google Chat Notification Bridge
Nhận alert từ Agent (HMAC-signed), format thành Google Chat card, forward đến webhook.
Port: 2222
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone

import httpx
import structlog
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response

load_dotenv(".env.runtime", override=True)

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)
log = structlog.get_logger()

app = FastAPI(title="GCP Gateway", version="1.0.0", docs_url=None)

SHARED_SECRET = os.getenv("AGENT_SHARED_SECRET", "")
GCHAT_WEBHOOK_URL = os.getenv("GCHAT_WEBHOOK_URL", "")

# ── Severity config ────────────────────────────────────────────────────────────
SEV_EMOJI = {
    "CRITICAL": "🔴",
    "WARNING":  "🟡",
    "ADVISORY": "🔵",
    "CLEAR":    "🟢",
}
SEV_COLOR = {
    "CRITICAL": "#F44336",
    "WARNING":  "#FF9800",
    "ADVISORY": "#2196F3",
    "CLEAR":    "#4CAF50",
}


# ── HMAC verification ──────────────────────────────────────────────────────────
def verify_signature(body: bytes, signature_header: str) -> bool:
    if not SHARED_SECRET:
        log.warning("gateway.secret.not_configured")
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        SHARED_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


# ── Google Chat card builder ───────────────────────────────────────────────────
def build_gchat_card(payload: dict) -> dict:
    severity   = (payload.get("severity") or "ADVISORY").upper()
    target     = payload.get("target_name") or "unknown"
    metric     = payload.get("metric_name") or "-"
    value      = payload.get("metric_value") or "-"
    message    = payload.get("message") or "-"
    incident_id = payload.get("incident_id", "?")
    occurred_at = payload.get("occurred_at") or datetime.now(timezone.utc).isoformat()
    threshold  = payload.get("threshold_value") or "-"

    emoji = SEV_EMOJI.get(severity, "⚪")
    color = SEV_COLOR.get(severity, "#9E9E9E")

    # RCA summary
    rca = payload.get("rca") or {}
    rca_summary = rca.get("summary") or ""
    rca_commands = rca.get("diagnostic_commands") or []

    # Build widgets
    widgets = [
        {"decoratedText": {
            "topLabel": "Target",
            "text": f"<b>{target}</b>",
            "icon": {"knownIcon": "BOOKMARK"},
        }},
        {"decoratedText": {
            "topLabel": "Metric / Value",
            "text": f"<font color='#888'>{metric}</font> = <b>{value}</b>  (threshold: {threshold})",
            "icon": {"knownIcon": "CLOCK"},
        }},
        {"decoratedText": {
            "topLabel": "Message",
            "text": message,
            "icon": {"knownIcon": "DESCRIPTION"},
            "wrapText": True,
        }},
    ]

    if rca_summary:
        widgets.append({"decoratedText": {
            "topLabel": "RCA",
            "text": rca_summary,
            "icon": {"knownIcon": "STAR"},
            "wrapText": True,
        }})

    if rca_commands:
        cmd_text = "\n".join(f"• <font color='#FF9800'>{c}</font>" for c in rca_commands[:4])
        widgets.append({"decoratedText": {
            "topLabel": "Diagnostic Commands",
            "text": cmd_text,
            "icon": {"knownIcon": "HOTEL_ROOM_TYPE"},
            "wrapText": True,
        }})

    widgets.append({"decoratedText": {
        "topLabel": "Incident ID / Time",
        "text": f"INC-{str(incident_id).zfill(4)}  ·  {occurred_at}",
        "icon": {"knownIcon": "INVITE"},
    }})

    return {
        "cardsV2": [{
            "cardId": f"inc-{incident_id}",
            "card": {
                "header": {
                    "title": f"{emoji} {severity} — {target}",
                    "subtitle": "Oracle OEM Alert · Agent Monitor",
                    "imageUrl": "https://www.gstatic.com/images/icons/material/system/2x/warning_red_48dp.png",
                    "imageType": "CIRCLE",
                },
                "sections": [{
                    "collapsible": False,
                    "widgets": widgets,
                }],
                "fixedFooter": {
                    "primaryButton": {
                        "text": "View Dashboard",
                        "onClick": {"openLink": {"url": os.getenv("DASHBOARD_URL", "http://localhost:2020/dashboard")}},
                        "color": {"red": color[1:3] and int(color[1:3], 16)/255,
                                  "green": color[3:5] and int(color[3:5], 16)/255,
                                  "blue": color[5:7] and int(color[5:7], 16)/255,
                                  "alpha": 1},
                    }
                },
            },
        }],
    }


# ── Routes ─────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "gcp-gateway", "version": "1.0.0"}


@app.post("/agent/alerts", status_code=202)
async def receive_alert(request: Request):
    body = await request.body()
    sig  = request.headers.get("X-Agent-Signature", "")

    if not verify_signature(body, sig):
        log.warning("gateway.alert.invalid_signature",
                    sig=sig[:20] if sig else "empty")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    log.info("gateway.alert.received",
             incident_id=payload.get("incident_id"),
             target=payload.get("target_name"),
             severity=payload.get("severity"))

    if not GCHAT_WEBHOOK_URL:
        log.error("gateway.webhook.not_configured")
        raise HTTPException(status_code=500, detail="Webhook not configured")

    card = build_gchat_card(payload)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(GCHAT_WEBHOOK_URL, json=card)
            r.raise_for_status()
        log.info("gateway.gchat.sent", incident_id=payload.get("incident_id"), status=r.status_code)
    except Exception as exc:
        log.error("gateway.gchat.failed", error=str(exc))
        raise HTTPException(status_code=502, detail=f"Google Chat error: {exc}")

    return {"accepted": True, "incident_id": payload.get("incident_id")}


@app.post("/google-chat/event", status_code=200)
async def gchat_event(request: Request):
    """Placeholder for future inbound Google Chat App events."""
    return Response(status_code=200)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=os.getenv("GATEWAY_HOST", "0.0.0.0"),
        port=int(os.getenv("GATEWAY_PORT", "2222")),
        log_level="info",
    )
