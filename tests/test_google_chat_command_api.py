from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from main import app


def test_google_chat_command_requires_shared_secret(monkeypatch):
    monkeypatch.setenv("GCP_GATEWAY_SHARED_SECRET", "secret")
    client = TestClient(app)

    response = client.post("/google-chat/command", json={"command_text": "/status flex"})

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid_gateway_secret"


def test_google_chat_command_accepts_status(monkeypatch):
    monkeypatch.setenv("GCP_GATEWAY_SHARED_SECRET", "secret")
    client = TestClient(app)

    response = client.post(
        "/google-chat/command",
        headers={"X-Gateway-Secret": "secret"},
        json={
            "command_text": "/status flex",
            "user_email": "nam.pham2@mservice.com.vn",
            "thread_name": "spaces/AAA/threads/BBB",
        },
    )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert data["job_id"].startswith("gchat-")
    assert data["command_text"] == "/status flex"


def test_google_chat_command_rejects_empty_command(monkeypatch):
    monkeypatch.setenv("GCP_GATEWAY_SHARED_SECRET", "secret")
    client = TestClient(app)

    response = client.post(
        "/google-chat/command",
        headers={"X-Gateway-Secret": "secret"},
        json={"command_text": "   "},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "missing_command_text"
