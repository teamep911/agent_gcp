"""
Monitor_v2 — Dashboard-only ASGI app.

Chạy riêng (port 2121, TLS) để thay thế dashboard v1 'monitor-vps'.
Không khởi động Telegram polling — bot đã chạy bên main:app (port 8080)
nên polling 2 nơi cùng token sẽ xung đột.
"""
import os

import structlog
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from db.models import init_db
from web.auth_web import router as auth_router
from web.dashboard_api import router as dashboard_router

load_dotenv()

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)
log = structlog.get_logger()

app = FastAPI(
    title="Monitor_v2 Dashboard",
    version="0.1.0",
    description="DBA Web Dashboard — replaces v1 monitor-vps",
    docs_url=None,
    redoc_url=None,
)

app.include_router(auth_router, prefix="/auth")
app.include_router(dashboard_router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Browser hit HTML route mà chưa auth → redirect /auth/login (v1-style UX).
    API call (Accept: application/json hoặc path /dashboard/data) vẫn trả JSON 401."""
    if exc.status_code == 401:
        accept = (request.headers.get("accept") or "").lower()
        path = request.url.path
        is_api = path.endswith("/data") or path.endswith("/audit") or "application/json" in accept
        wants_html = "text/html" in accept
        if wants_html and not is_api and not path.startswith("/auth"):
            return RedirectResponse(url="/auth/login", status_code=302)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard")


@app.on_event("startup")
async def startup():
    log.info("dashboard.startup", version="0.1.0")
    await init_db()


@app.on_event("shutdown")
async def shutdown():
    log.info("dashboard.shutdown")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "dashboard", "version": "0.1.0"}


if __name__ == "__main__":
    uvicorn.run(
        "dashboard_app:app",
        host=os.getenv("DASHBOARD_HOST", "0.0.0.0"),
        port=int(os.getenv("DASHBOARD_PORT", 2121)),
        ssl_certfile=os.getenv("DASHBOARD_TLS_CERT"),
        ssl_keyfile=os.getenv("DASHBOARD_TLS_KEY"),
    )
