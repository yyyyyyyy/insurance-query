"""API stream endpoint tests."""

from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


class TestQueryStream:
    def test_stream_returns_event_stream(self):
        with client.stream(
            "POST", "/query/stream", json={"query": "重疾险保障什么？"},
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")
            body = "".join(response.iter_text())
            assert "event: done" in body
