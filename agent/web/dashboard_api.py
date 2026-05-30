"""
Monitor_v2 — Dashboard JSON API
asyncpg-based, adapted từ v1 dashboard_api.py.
Schema mới: incidents + audit_log tables.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from db.models import get_db_pool
from web.auth_web import require_user

logger = logging.getLogger(__name__)
router = APIRouter()

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "../templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)
FLOW_STATUS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../docs/flow_test_status.json'))

_DB_LABEL = {
    "oracle_database": "Oracle DB",
    "rac_database":    "Oracle RAC",
    "host":            "Host",
    "oracle_emd":      "OEM Agent",
}

def _db_label(t: str) -> str:
    return _DB_LABEL.get((t or "").lower(), t or "Unknown")


# ── GET /dashboard ─────────────────────────────────────────────────────────────
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request, user: str = Depends(require_user)):
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user})


# ── GET /dashboard/data ────────────────────────────────────────────────────────
@router.get("/dashboard/data")
async def dashboard_data(days: int = 7, user: str = Depends(require_user)):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # ── KPI stats ──────────────────────────────────────────────────────────
        total    = await conn.fetchval("SELECT COUNT(*) FROM incidents")
        critical = await conn.fetchval("SELECT COUNT(*) FROM incidents WHERE severity='CRITICAL'")
        warning  = await conn.fetchval("SELECT COUNT(*) FROM incidents WHERE severity='WARNING'")
        advisory = await conn.fetchval("SELECT COUNT(*) FROM incidents WHERE severity IN ('ADVISORY','INFO')")
        clear    = await conn.fetchval("SELECT COUNT(*) FROM incidents WHERE severity='CLEAR'")
        notified = await conn.fetchval("SELECT COUNT(*) FROM incidents WHERE notified=true")
        targets  = await conn.fetchval("SELECT COUNT(DISTINCT target_name) FROM incidents")

        # ── Recent incidents (last 100) ────────────────────────────────────────
        rows = await conn.fetch(
            """
            SELECT id, target_name, target_type, severity, category,
                   metric_name, metric_value, message, rule_name,
                   notified, created_at
            FROM incidents
            ORDER BY created_at DESC
            LIMIT 100
            """
        )

        incidents = [
            {
                "id":       r["id"],
                "time":     r["created_at"].strftime("%Y-%m-%d %H:%M") if r["created_at"] else "",
                "target":   r["target_name"] or "",
                "db":       _db_label(r["target_type"] or ""),
                "severity": (r["severity"] or "").upper(),
                "category": r["category"] or "",
                "metric":   r["metric_name"] or "",
                "value":    r["metric_value"] or "",
                "message":  r["message"] or "",
                "rule":     r["rule_name"] or "",
                "notified": r["notified"],
            }
            for r in rows
        ]

        # ── Daily chart ────────────────────────────────────────────────────────
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        daily_rows = await conn.fetch(
            """
            SELECT DATE(created_at) AS day, severity, COUNT(*) AS cnt
            FROM incidents
            WHERE created_at >= $1
            GROUP BY day, severity
            ORDER BY day
            """,
            cutoff,
        )

        labels_d, crit_d, warn_d, adv_d = [], [], [], []
        for i in range(days - 1, -1, -1):
            d = (datetime.now(timezone.utc) - timedelta(days=i)).date()
            labels_d.append(d.strftime("%d/%m"))
            dm = {r["severity"].upper(): r["cnt"] for r in daily_rows if r["day"] == d}
            crit_d.append(dm.get("CRITICAL", 0))
            warn_d.append(dm.get("WARNING", 0))
            adv_d.append(dm.get("ADVISORY", 0) + dm.get("INFO", 0))

        # ── Hourly chart (today) ───────────────────────────────────────────────
        hourly_rows = await conn.fetch(
            """
            SELECT EXTRACT(HOUR FROM created_at)::int AS hr, COUNT(*) AS cnt
            FROM incidents
            WHERE created_at >= CURRENT_DATE
            GROUP BY hr
            ORDER BY hr
            """
        )
        hourly = [0] * 24
        for r in hourly_rows:
            hourly[r["hr"]] = r["cnt"]

        # ── Category breakdown ─────────────────────────────────────────────────
        cat_rows = await conn.fetch(
            """
            SELECT category, COUNT(*) AS cnt
            FROM incidents
            GROUP BY category
            ORDER BY cnt DESC
            LIMIT 8
            """
        )
        categories = [{"label": r["category"] or "other", "count": r["cnt"]} for r in cat_rows]

    return JSONResponse({
        "stats": {
            "total": total, "critical": critical, "warning": warning,
            "advisory": advisory, "clear": clear,
            "notified": notified, "targets": targets,
        },
        "incidents": incidents,
        "chart_daily":  {"labels": labels_d, "critical": crit_d, "warning": warn_d, "advisory": adv_d},
        "chart_hourly": {"labels": [f"{h:02d}:00" for h in range(24)], "data": hourly},
        "categories":   categories,
    })


# ── GET /dashboard/audit ───────────────────────────────────────────────────────
@router.get("/dashboard/audit")
async def audit_data(limit: int = 50, user: str = Depends(require_user)):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, user_id, user_name, command, params, target_name,
                   approved_by, status, error_message, created_at, executed_at
            FROM audit_log
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )
        entries = [
            {
                "id":          r["id"],
                "user_id":     r["user_id"],
                "user_name":   r["user_name"] or r["user_id"],
                "command":     r["command"],
                "target":      r["target_name"] or "—",
                "status":      r["status"],
                "approved_by": r["approved_by"] or "—",
                "error":       r["error_message"] or "",
                "created_at":  r["created_at"].strftime("%Y-%m-%d %H:%M:%S") if r["created_at"] else "",
                "executed_at": r["executed_at"].strftime("%H:%M:%S") if r["executed_at"] else "—",
            }
            for r in rows
        ]

        # Audit stats
        total_cmds   = await conn.fetchval("SELECT COUNT(*) FROM audit_log")
        executed     = await conn.fetchval("SELECT COUNT(*) FROM audit_log WHERE status='executed'")
        failed       = await conn.fetchval("SELECT COUNT(*) FROM audit_log WHERE status='failed'")
        pending      = await conn.fetchval("SELECT COUNT(*) FROM audit_log WHERE status='pending'")
        timeout      = await conn.fetchval("SELECT COUNT(*) FROM audit_log WHERE status='timeout'")

    return JSONResponse({
        "entries": entries,
        "stats": {
            "total": total_cmds, "executed": executed, "failed": failed,
            "pending": pending, "timeout": timeout,
        },
    })


@router.get('/dashboard/flow-status')
async def dashboard_flow_status(user: str = Depends(require_user)):
    try:
        with open(FLOW_STATUS_PATH, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        return JSONResponse(payload)
    except FileNotFoundError:
        return JSONResponse({'detail': 'flow_status_not_found'}, status_code=404)
