"""
Monitor_v2 — Database Models & Pool Management
asyncpg connection pool + helper queries.
"""

import json
import os
from typing import Optional

import asyncpg
import structlog

log = structlog.get_logger()

_pool: Optional[asyncpg.Pool] = None


async def get_db_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        raise RuntimeError("DB pool chưa được khởi tạo. Gọi init_db() trước.")
    return _pool


async def init_db():
    global _pool
    dsn = os.getenv("PG_DSN", "postgresql://monitor_user:change_me@localhost:5432/monitor_v2")
    _pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
    log.info("db.pool.initialized")


async def save_incident(
    target_name: str,
    target_type: str,
    severity: str,
    category: str,
    metric_name: str,
    metric_value: Optional[str],
    message: str,
    rule_name: Optional[str],
    raw_payload: dict,
    rca_result: Optional[dict],
) -> int:
    """INSERT incident, trả về incident id."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO incidents(
                target_name, target_type, severity, category,
                metric_name, metric_value, message, rule_name,
                raw_payload, rca_result
            ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            RETURNING id
            """,
            target_name, target_type, severity, category,
            metric_name, metric_value, message, rule_name,
            json.dumps(raw_payload, ensure_ascii=False),
            json.dumps(rca_result, ensure_ascii=False) if rca_result is not None else None,
        )
        incident_id = row["id"]
        log.info("db.incident.saved", incident_id=incident_id, target=target_name)
        return incident_id


async def get_recent_incidents(limit: int = 10, target_name: Optional[str] = None) -> list:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        if target_name:
            rows = await conn.fetch(
                "SELECT id, target_name, severity, message, created_at "
                "FROM incidents WHERE target_name=$1 "
                "ORDER BY created_at DESC LIMIT $2",
                target_name, limit,
            )
        else:
            rows = await conn.fetch(
                "SELECT id, target_name, severity, message, created_at "
                "FROM incidents ORDER BY created_at DESC LIMIT $1",
                limit,
            )
        return [dict(r) for r in rows]


async def mark_incident_notified(incident_id: int):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE incidents SET notified=true WHERE id=$1", incident_id
        )
