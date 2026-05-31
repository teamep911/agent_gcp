from __future__ import annotations

import os
import uuid

import structlog
from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from auth.audit import create_command_audit, update_audit_status, write_audit_event

log = structlog.get_logger()
router = APIRouter()


class GoogleChatCommandPayload(BaseModel):
    command_text: str
    user_email: str | None = None
    thread_name: str | None = None
    space_name: str | None = None
    raw_event: dict | None = None


def _target_from_command(command_text: str) -> str | None:
    parts = (command_text or "").strip().split()
    if len(parts) >= 2:
        return parts[1]
    return None


async def _safe_write_audit_event(*args, **kwargs) -> None:
    try:
        await write_audit_event(*args, **kwargs)
    except RuntimeError as exc:
        log.warning("audit.write.skipped", error=str(exc))


async def _safe_create_command_audit(*args, **kwargs) -> int | None:
    try:
        return await create_command_audit(*args, **kwargs)
    except RuntimeError as exc:
        log.warning("audit.command_create.skipped", error=str(exc))
        return None


async def _safe_update_audit_status(audit_id: int | None, status_text: str) -> None:
    if audit_id is None:
        return
    try:
        await update_audit_status(audit_id, status_text)
    except RuntimeError as exc:
        log.warning("audit.status_update.skipped", audit_id=audit_id, error=str(exc))


@router.post("/google-chat/command", status_code=status.HTTP_202_ACCEPTED)
async def receive_google_chat_command(
    payload: GoogleChatCommandPayload,
    x_gateway_secret: str | None = Header(default=None),
):
    expected_secret = os.getenv("GCP_GATEWAY_SHARED_SECRET", "")
    if not expected_secret or x_gateway_secret != expected_secret:
        await _safe_write_audit_event(
            event_type="google_chat.command.rejected",
            details={
                "reason": "invalid_gateway_secret",
                "user_email": payload.user_email,
                "command_text": payload.command_text,
            },
            user_id=payload.user_email or "unknown",
            user_name=payload.user_email or "unknown",
        )
        raise HTTPException(status_code=401, detail="invalid_gateway_secret")

    command_text = (payload.command_text or "").strip()
    if not command_text:
        await _safe_write_audit_event(
            event_type="google_chat.command.rejected",
            details={"reason": "missing_command_text", "user_email": payload.user_email},
            user_id=payload.user_email or "unknown",
            user_name=payload.user_email or "unknown",
        )
        raise HTTPException(status_code=400, detail="missing_command_text")

    job_id = f"gchat-{uuid.uuid4().hex[:12]}"
    target_name = _target_from_command(command_text)
    params = {
        "job_id": job_id,
        "command_text": command_text,
        "thread_name": payload.thread_name,
        "space_name": payload.space_name,
        "raw_event_type": (payload.raw_event or {}).get("type") if payload.raw_event else None,
    }
    audit_id = await _safe_create_command_audit(
        user_id=payload.user_email or "google_chat",
        user_name=payload.user_email or "google_chat",
        command=command_text,
        params=params,
        target_name=target_name,
    )
    await _safe_update_audit_status(audit_id, "executed")
    await _safe_write_audit_event(
        event_type="google_chat.command.received",
        details={"job_id": job_id, "audit_id": audit_id, "command_text": command_text, "target": target_name},
        user_id=payload.user_email or "google_chat",
        user_name=payload.user_email or "google_chat",
    )
    log.info(
        "google_chat.command.accepted",
        job_id=job_id,
        audit_id=audit_id,
        command_text=command_text,
        user_email=payload.user_email,
        thread_name=payload.thread_name,
    )
    return {"status": "accepted", "job_id": job_id, "audit_id": audit_id, "command_text": command_text}
