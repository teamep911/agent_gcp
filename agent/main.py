from __future__ import annotations

import os

import structlog
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

load_dotenv()

from db.models import init_db
from handlers.google_chat_handler import router as google_chat_router
from handlers.webhook_handler import router as webhook_router
from web.auth_web import router as auth_router
from web.dashboard_api import router as dashboard_router

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
    title="Agent Monitor for GCP/Google Chat",
    version="0.1.0",
    docs_url="/docs" if os.getenv("ENV", "prod") != "prod" else None,
)
app.include_router(webhook_router, prefix="/webhook")
app.include_router(google_chat_router)
app.include_router(auth_router)
app.include_router(dashboard_router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        accept = (request.headers.get("accept") or "").lower()
        path = request.url.path
        is_api = path.endswith("/data") or path.endswith("/audit") or "application/json" in accept
        if "text/html" in accept and not is_api and not path.startswith("/login"):
            return RedirectResponse(url="/login", status_code=302)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


def _preflight_check():
    env = os.getenv("ENV", "prod").lower()
    required = ["PG_DSN", "AGENT_WEBHOOK_SECRET", "GCP_GATEWAY_BASE_URL", "GCP_GATEWAY_SHARED_SECRET", "DASHBOARD_JWT_SECRET", "DASHBOARD_PASSWORD"]
    missing = [name for name in required if not os.getenv(name)]
    if env == "prod" and missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


@app.on_event("startup")
async def startup():
    log.info("agent_monitor.startup")
    _preflight_check()
    await init_db()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "agent_monitor", "version": "0.1.0"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=os.getenv("AGENT_HOST", "0.0.0.0"),
        port=int(os.getenv("AGENT_PORT", "2020")),
        reload=os.getenv("ENV") == "dev",
    )
