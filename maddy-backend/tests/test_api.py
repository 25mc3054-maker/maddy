from fastapi.testclient import TestClient

from app.main import app
from app.database.db import initialize_database


def test_health():
    with TestClient(app) as client:
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


def test_create_and_complete_task(monkeypatch, tmp_path):
    from app.database import db

    # Keep this integration test's task writes isolated from the user's DB.
    monkeypatch.setattr(db, "DATABASE_DIR", tmp_path)
    monkeypatch.setattr(db, "DATABASE_PATH", tmp_path / "test-maddy.db")
    with TestClient(app) as client:
        initialize_database()

        create_response = client.post(
            "/api/tasks",
            json={
                "title": "Test MADDY task",
                "description": "Created by automated tests",
                "priority": "high",
                "due_date": None,
            },
        )

        assert create_response.status_code == 201

        task = create_response.json()

        assert task["title"] == "Test MADDY task"
        assert task["completed"] == 0

        complete_response = client.post(
            f"/api/tasks/{task['id']}/complete"
        )

        assert complete_response.status_code == 200
        assert complete_response.json()["completed"] == 1


def test_smart_home_devices_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/smart-home/devices")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["mode"] == "simulation"
        assert any(d["device_id"] == "living_room_light" for d in body["devices"])


def test_chat_returns_safe_error_when_agent_fails(monkeypatch):
    from app import main

    def fail_agent(history):
        raise RuntimeError("mock model failure")

    monkeypatch.setattr(main, "chat_with_maddy", fail_agent)
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 502
    assert "Check server logs" in response.json()["detail"]


def test_chat_classifies_mcp_unavailable(monkeypatch):
    from app import main

    def fail_mcp(history):
        raise main.MCPConnectionError("internal MCP connection detail")

    monkeypatch.setattr(main, "chat_with_maddy", fail_mcp)
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 503
    assert response.json()["error_type"] == "mcp_unavailable"
    assert "internal MCP connection detail" not in response.text


def test_chat_classifies_bedrock_failure(monkeypatch):
    from app import main

    def fail_bedrock(history):
        raise main.BedrockRequestError("internal Bedrock detail")

    monkeypatch.setattr(main, "chat_with_maddy", fail_bedrock)
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 502
    assert response.json()["error_type"] == "bedrock_error"
    assert "internal Bedrock detail" not in response.text
