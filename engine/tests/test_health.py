"""Phase-0 exit gate: the app boots and /health responds with the backend wiring."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert set(body["backends"]) == {"asr", "llm", "embedding", "blob"}
