from __future__ import annotations

import os
import uuid

import structlog
from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

log = structlog.get_logger()
router = APIRouter()


class GoogleChatCommandPayload(BaseModel):
    command_text: str
    user_email: str | None = None
    thread_name: str | None = None
    space_name: str | None = None
    raw_event: dict | None = None


@router.post("/google-chat/command", status_code=status.HTTP_202_ACCEPTED)
async def receive_google_chat_command(
    payload: GoogleChatCommandPayload,
    x_gateway_secret: str | None = Header(default=None),
):
    expected_secret = os.getenv("GCP_GATEWAY_SHARED_SECRET", "")
    if not expected_secret or x_gateway_secret != expected_secret:
        raise HTTPException(status_code=401, detail="invalid_gateway_secret")
    command_text = (payload.command_text or "").strip()
    if not command_text:
        raise HTTPException(status_code=400, detail="missing_command_text")
    job_id = f"gchat-{uuid.uuid4().hex[:12]}"
    log.info(
        "google_chat.command.accepted",
        job_id=job_id,
        command_text=command_text,
        user_email=payload.user_email,
        thread_name=payload.thread_name,
    )
    return {"status": "accepted", "job_id": job_id, "command_text": command_text}
