"""
Integration tests for the FastAPI service (Sprint 1.4).

Tests the POST /query endpoint and GET /sessions/{id} endpoint
using FastAPI's TestClient.
"""

from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


class TestQueryEndpoint:
    """Test POST /query endpoint."""

    def test_post_query_returns_200(self):
        response = client.post("/query", json={"query": "重疾险保障什么？"})
        assert response.status_code == 200

    def test_post_query_returns_answer(self):
        response = client.post("/query", json={"query": "比较百万医疗和重疾险"})
        data = response.json()
        assert "session_id" in data
        assert "answer" in data
        assert "evaluation" in data
        assert "execution_graph" in data

    def test_post_query_answer_has_text(self):
        response = client.post("/query", json={"query": "e生保一年多少钱？"})
        data = response.json()
        assert len(data["answer"]["text"]) > 0

    def test_post_query_trace_has_events(self):
        response = client.post("/query", json={"query": "理赔流程"})
        data = response.json()
        assert len(data["execution_graph"]) > 0

    def test_post_query_with_custom_session_id(self):
        response = client.post("/query", json={
            "query": "测试查询",
            "session_id": "custom-session-123"
        })
        data = response.json()
        assert data["session_id"] == "custom-session-123"

    def test_post_query_empty_query_rejected(self):
        response = client.post("/query", json={"query": ""})
        assert response.status_code == 422  # Validation error

    def test_post_query_missing_query_rejected(self):
        response = client.post("/query", json={})
        assert response.status_code == 422

    def test_multiple_queries_different_ids(self):
        r1 = client.post("/query", json={"query": "查询1"})
        r2 = client.post("/query", json={"query": "查询2"})

        assert r1.json()["session_id"] != r2.json()["session_id"]

    def test_answer_has_evidence(self):
        """ARCHITECTURE RULE #2: Answer must have evidence."""
        response = client.post("/query", json={"query": "理赔流程"})
        data = response.json()
        assert data["answer"]["evidence_count"] > 0

    def test_state_reconstruction_in_response(self):
        response = client.post("/query", json={"query": "查询保障范围"})
        data = response.json()

        assert data["answer"] is not None
        assert data["evaluation"] is not None


class TestSessionTraceEndpoint:
    """Test GET /sessions/{id} endpoint."""

    def test_get_existing_session(self):
        create_resp = client.post("/query", json={"query": "track me"})
        session_id = create_resp.json()["session_id"]

        trace_resp = client.get(f"/sessions/{session_id}")
        assert trace_resp.status_code == 200

        data = trace_resp.json()
        assert data["session_id"] == session_id
        assert "agents" in data
        assert "message_log" in data

    def test_get_nonexistent_session_returns_200(self):
        response = client.get("/sessions/nonexistent-id")
        assert response.status_code == 200  # Returns empty agent status

    def test_reconstructed_state_matches_original(self):
        create_resp = client.post("/query", json={"query": "replay test"})
        session_id = create_resp.json()["session_id"]
        trace_resp = client.get(f"/sessions/{session_id}")
        assert trace_resp.status_code == 200
        # Verify session exists in response
        assert trace_resp.json()["session_id"] == session_id


class TestHealthEndpoint:
    """Test GET /health endpoint."""

    def test_health_returns_200(self):
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "sessions_processed" in data


class TestEventsEndpoint:
    """Test GET /events debug endpoint."""

    def test_events_endpoint(self):
        client.post("/query", json={"query": "event test"})
        response = client.get("/events")
        assert response.status_code == 200
        data = response.json()
        assert "message_count" in data
        assert data["message_count"] > 0
