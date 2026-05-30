"""
Monitor_v2 — Web Dashboard Auth
JWT cookie-based auth cho web dashboard.
"""

import hmac
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import jwt
from fastapi import APIRouter, Cookie, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)
router = APIRouter()

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "../templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

JWT_SECRET   = os.getenv("DASHBOARD_JWT_SECRET", "monitor_v2_change_me")
JWT_EXPIRE   = int(os.getenv("DASHBOARD_JWT_EXPIRE_MINUTES", "480"))   # 8 hours
DASH_USER    = os.getenv("DASHBOARD_USER", "dba")
DASH_PASS    = os.getenv("DASHBOARD_PASSWORD", "change_me")
COOKIE_SECURE = os.getenv("DASHBOARD_COOKIE_SECURE", os.getenv("ENV", "prod").lower() == "prod")
if isinstance(COOKIE_SECURE, str):
    COOKIE_SECURE = COOKIE_SECURE.lower() in {"1", "true", "yes", "on"}
ALGORITHM    = "HS256"


def create_token(username: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE)
    return jwt.encode({"sub": username, "exp": exp}, JWT_SECRET, algorithm=ALGORITHM)


def verify_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        return payload.get("sub")
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def require_user(access_token: Optional[str] = Cookie(default=None)) -> str:
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    sub = verify_token(access_token)
    if not sub:
        raise HTTPException(status_code=401, detail="Session expired")
    return sub


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    valid = (
        hmac.compare_digest(username, DASH_USER) and
        hmac.compare_digest(password, DASH_PASS)
    )
    if not valid:
        logger.warning("Failed login | user=%s | src=%s", username, request.client.host)
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Sai username hoặc password.", "username": username},
            status_code=401,
        )
    token = create_token(username)
    logger.info("Login OK | user=%s | src=%s", username, request.client.host)
    resp = RedirectResponse(url="/dashboard", status_code=302)
    resp.set_cookie("access_token", token, httponly=True, secure=COOKIE_SECURE,
                    samesite="lax", max_age=JWT_EXPIRE * 60)
    return resp


@router.get("/logout")
async def logout():
    resp = RedirectResponse(url="/login", status_code=302)
    resp.delete_cookie("access_token")
    return resp
