"""
Monitor_v2 — Audit Logger
Ghi tất cả event vào audit_log table (immutable — INSERT only).
"""

import json
from datetime import datetime, timezone
from typing import Optional

import structlog

from db.models import get_db_pool

log = structlog.get_logger()


async def write_audit_event(
    event_type: str,
    details: dict,
    user_id: Optional[str] = None,
    user_name: Optional[str] = None,
):
    """Ghi event hệ thống (không phải command từ chat)."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO audit_log(user_id, user_name, command, params, status, created_at)
            VALUES($1, $2, $3, $4, 'system', now())
            """,
            user_id or "system",
            user_name or "system",
            event_type,
            json.dumps(details, ensure_ascii=False),
        )


async def create_command_audit(
    user_id: str,
    user_name: str,
    command: str,
    params: dict,
    target_name: Optional[str] = None,
) -> int:
    """
    Tạo audit record cho command từ Telegram.
    Trả về audit_id để update status sau.
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO audit_log(user_id, user_name, command, params, target_name, status, created_at)
            VALUES($1, $2, $3, $4, $5, 'pending', now())
            RETURNING id
            """,
            user_id, user_name, command, json.dumps(params, ensure_ascii=False), target_name,
        )
        audit_id = row["id"]
        log.info("audit.command_created", audit_id=audit_id, user=user_name, command=command)
        return audit_id


async def update_audit_status(
    audit_id: int,
    status: str,
    approved_by: Optional[str] = None,
    error_message: Optional[str] = None,
):
    """Update trạng thái của command: approved | rejected | timeout | executed | failed."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE audit_log
            SET status=$2,
                approved_by=COALESCE($3, approved_by),
                error_message=COALESCE($4, error_message),
                executed_at=CASE WHEN $2 IN ('executed', 'failed') THEN now() ELSE executed_at END
            WHERE id=$1
            """,
            audit_id, status, approved_by, error_message,
        )
        log.info("audit.status_updated", audit_id=audit_id, status=status)
