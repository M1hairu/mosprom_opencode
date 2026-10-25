from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health_reports_build_commit(monkeypatch):
    monkeypatch.setenv("GIT_SHA", "abc123-dirty")
    assert client.get("/api/health").json() == {"status": "ok", "sha": "abc123-dirty"}


def test_health_without_commit_says_unknown(monkeypatch):
    monkeypatch.delenv("GIT_SHA", raising=False)
    assert client.get("/api/health").json()["sha"] == "unknown"
