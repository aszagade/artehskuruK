"""Tests for SANJAYA frontend serving — Mission: Serve and Verify UI."""

import pytest
from fastapi.testclient import TestClient

from command_center.backend.main import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app, raise_server_exceptions=False)


class TestFrontendServing:
    """Verify that the SANJAYA frontend is served and APIs remain intact."""

    def test_root_returns_200(self, client):
        """GET / returns HTTP 200."""
        resp = client.get("/")
        assert resp.status_code == 200

    def test_root_contains_sanjaya_frontend(self, client):
        """GET / contains recognizable SANJAYA frontend content."""
        resp = client.get("/")
        body = resp.text
        # The frontend should contain the SANJAYA title or a key UI element
        assert "SANJAYA" in body or "sanjaya" in body.lower(), (
            "Root response does not appear to contain the SANJAYA frontend"
        )

    def test_root_is_html(self, client):
        """GET / returns HTML content."""
        resp = client.get("/")
        ct = resp.headers.get("content-type", "")
        assert "text/html" in ct or "application/octet-stream" in ct, (
            f"Expected HTML content-type, got: {ct}"
        )

    def test_docs_still_works(self, client):
        """GET /docs still works."""
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_api_config_still_works(self, client):
        """GET /api/config still works."""
        resp = client.get("/api/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data

    def test_api_ask_registered(self, client):
        """POST /api/ask route is registered (may return 422 for missing body)."""
        resp = client.post("/api/ask", json={})
        # Should be 422 (validation error) or similar — NOT 404
        assert resp.status_code != 404, "/api/ask route not found"

    def test_api_health_registered(self, client):
        """GET /api/health still works."""
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_knowledge_upload_registered(self, client):
        """POST /api/knowledge/upload route is registered."""
        resp = client.post("/api/knowledge/upload")
        # Should be 422 (missing file) or similar — NOT 404
        assert resp.status_code != 404, "/api/knowledge/upload route not found"

    def test_auth_login_registered(self, client):
        """GET /auth/login route is registered."""
        resp = client.get("/auth/login", follow_redirects=False)
        # Should redirect (307) to Entra or return error — NOT 404
        assert resp.status_code != 404, "/auth/login route not found"

    def test_api_feedback_registered(self, client):
        """POST /api/feedback route is registered."""
        resp = client.post("/api/feedback", json={})
        # Should be 422 or similar — NOT 404
        assert resp.status_code != 404, "/api/feedback route not found"

    def test_graph_endpoint_registered(self, client):
        """GET /api/graph/stats endpoint is registered."""
        resp = client.get("/api/graph/stats")
        # Should return data or error — NOT 404
        assert resp.status_code != 404, "/api/graph/stats route not found"

    def test_openapi_spec_available(self, client):
        """GET /openapi.json is available (Swagger UI)."""
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        data = resp.json()
        assert "paths" in data
