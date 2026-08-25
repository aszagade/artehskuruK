"""
Tier-1 Security Controls Tests
================================

Deterministic tests for:
  1. API-key authentication (APIKeyAuth middleware)
  2. Path traversal protection (PathTraversalGuard middleware)
  3. CORS configuration (SecurityConfig)
  4. VisibilityFilter on /api/query
  5. Request audit logging (AuditLog middleware)

All tests are offline and do not require network access.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from kurukshetra.security.config import SecurityConfig
from kurukshetra.security.middleware import APIKeyAuth, AuditLog, PathTraversalGuard


# ==================================================================
# 1. SecurityConfig tests
# ==================================================================

class TestSecurityConfig(unittest.TestCase):
    """Tests for the SecurityConfig dataclass."""

    def test_default_config_open_mode(self):
        """Default config has auth_required=False (development mode)."""
        config = SecurityConfig()
        self.assertFalse(config.auth_required)

    def test_auth_required_from_env(self):
        """auth_required reads from KURUKSHETRA_AUTH_REQUIRED env var."""
        with patch.dict(os.environ, {"KURUKSHETRA_AUTH_REQUIRED": "1"}):
            config = SecurityConfig()
            self.assertTrue(config.auth_required)

    def test_auth_not_required_from_env(self):
        """auth_required=False when env var is '0'."""
        with patch.dict(os.environ, {"KURUKSHETRA_AUTH_REQUIRED": "0"}):
            config = SecurityConfig()
            self.assertFalse(config.auth_required)

    def test_api_keys_from_env(self):
        """API keys parsed from comma-separated env var."""
        with patch.dict(os.environ, {"KURUKSHETRA_API_KEYS": "key1,key2,key3"}):
            config = SecurityConfig()
            self.assertEqual(config.api_keys, ["key1", "key2", "key3"])

    def test_empty_api_keys_default(self):
        """Empty env var produces empty key list."""
        with patch.dict(os.environ, {"KURUKSHETRA_API_KEYS": ""}):
            config = SecurityConfig()
            self.assertEqual(config.api_keys, [])

    def test_cors_origins_from_env(self):
        """CORS origins parsed from comma-separated env var."""
        with patch.dict(os.environ, {"KURUKSHETRA_CORS_ORIGINS": "http://a.com,http://b.com"}):
            config = SecurityConfig()
            self.assertEqual(config.cors_origins, ["http://a.com", "http://b.com"])

    def test_cors_default_open(self):
        """Default CORS is wildcard."""
        config = SecurityConfig()
        self.assertEqual(config.cors_origins, ["*"])

    def test_is_key_valid_open_mode(self):
        """Any key is valid when auth_required=False."""
        config = SecurityConfig()
        config.auth_required = False
        self.assertTrue(config.is_key_valid("anything"))
        self.assertTrue(config.is_key_valid(""))

    def test_is_key_valid_with_keys(self):
        """Valid key passes, invalid key fails when auth is required."""
        config = SecurityConfig(auth_required=True, api_keys=["secret123"])
        self.assertTrue(config.is_key_valid("secret123"))
        self.assertFalse(config.is_key_valid("wrong"))
        self.assertFalse(config.is_key_valid(""))

    def test_is_key_valid_no_keys_configured(self):
        """When auth_required=True but no keys configured, open mode."""
        config = SecurityConfig(auth_required=True, api_keys=[])
        self.assertTrue(config.is_key_valid("anything"))


class TestPathTraversalConfig(unittest.TestCase):
    """Tests for path traversal configuration."""

    def test_default_allowed_dirs(self):
        """Default allowed dirs include knowledge/ and tmp/."""
        config = SecurityConfig()
        self.assertTrue(len(config.allowed_ingest_dirs) >= 2)

    def test_allowed_dirs_from_env(self):
        """Allowed dirs parsed from env."""
        with patch.dict(os.environ, {"KURUKSHETRA_ALLOWED_INGEST_DIRS": "/a,/b"}):
            config = SecurityConfig()
            self.assertEqual(len(config.allowed_ingest_dirs), 2)

    def test_is_path_allowed_within_dir(self):
        """Path within allowed directory is permitted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SecurityConfig(allowed_ingest_dirs=[Path(tmpdir)])
            test_file = Path(tmpdir) / "subdir" / "doc.pdf"
            self.assertTrue(config.is_path_allowed(test_file))

    def test_is_path_allowed_outside_dir(self):
        """Path outside allowed directories is rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SecurityConfig(allowed_ingest_dirs=[Path(tmpdir) / "allowed"])
            outside_file = Path(tmpdir) / "secret.txt"
            self.assertFalse(config.is_path_allowed(outside_file))

    def test_is_path_allowed_symlink(self):
        """Resolved path is checked, preventing symlink traversal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            allowed = Path(tmpdir) / "allowed"
            allowed.mkdir()
            outside = Path(tmpdir) / "outside"
            outside.mkdir()
            (outside / "secret.txt").write_text("secret")

            # Create symlink from inside allowed to outside
            symlink = allowed / "link.txt"
            try:
                symlink.symlink_to(outside / "secret.txt")
            except OSError:
                self.skipTest("Symlinks not supported on this platform")

            config = SecurityConfig(allowed_ingest_dirs=[allowed])
            # The resolved path goes to outside/, so it should be blocked
            self.assertFalse(config.is_path_allowed(symlink))


# ==================================================================
# 2. API Key Auth Middleware tests
# ==================================================================

def _run_async(coro):
    """Run an async coroutine synchronously (Python 3.10+ safe)."""
    import asyncio
    return asyncio.run(coro)


def _make_call_next(response):
    """Create an async call_next mock that returns the given response."""
    async def call_next(request):
        return response
    return call_next


class TestAPIKeyAuth(unittest.TestCase):
    """Tests for the APIKeyAuth middleware."""

    def _make_request(self, path: str = "/api/query", headers: dict | None = None) -> MagicMock:
        """Create a mock request."""
        request = MagicMock()
        request.url.path = path
        request.headers = headers or {}
        return request

    def test_open_mode_allows_all(self):
        """When auth_required=False, all requests pass."""
        config = SecurityConfig()
        config.auth_required = False
        middleware = APIKeyAuth(MagicMock(), config=config)
        request = self._make_request()
        response = MagicMock()
        result = _run_async(middleware.dispatch(request, _make_call_next(response)))
        self.assertEqual(result, response)

    def test_auth_required_blocks_no_key(self):
        """When auth_required=True, missing key returns 401."""
        config = SecurityConfig(auth_required=True, api_keys=["valid_key"])
        middleware = APIKeyAuth(MagicMock(), config=config)
        request = self._make_request(headers={})
        response = _run_async(middleware.dispatch(request, _make_call_next(MagicMock())))
        self.assertEqual(response.status_code, 401)

    def test_auth_required_blocks_invalid_key(self):
        """When auth_required=True, invalid key returns 401."""
        config = SecurityConfig(auth_required=True, api_keys=["valid_key"])
        middleware = APIKeyAuth(MagicMock(), config=config)
        request = self._make_request(headers={"X-API-Key": "wrong_key"})
        response = _run_async(middleware.dispatch(request, _make_call_next(MagicMock())))
        self.assertEqual(response.status_code, 401)

    def test_auth_required_allows_valid_key(self):
        """When auth_required=True, valid key passes through."""
        config = SecurityConfig(auth_required=True, api_keys=["valid_key"])
        middleware = APIKeyAuth(MagicMock(), config=config)
        request = self._make_request(headers={"X-API-Key": "valid_key"})
        next_response = MagicMock()
        response = _run_async(middleware.dispatch(request, _make_call_next(next_response)))
        self.assertEqual(response, next_response)

    def test_health_bypasses_auth(self):
        """Health endpoint bypasses authentication."""
        config = SecurityConfig(auth_required=True, api_keys=["key"])
        middleware = APIKeyAuth(MagicMock(), config=config)
        request = self._make_request(path="/api/health", headers={})
        next_response = MagicMock()
        response = _run_async(middleware.dispatch(request, _make_call_next(next_response)))
        self.assertEqual(response, next_response)


# ==================================================================
# 3. Path Traversal Guard tests
# ==================================================================

class TestPathTraversalGuard(unittest.TestCase):
    """Tests for the PathTraversalGuard middleware."""

    def test_non_ingest_endpoint_passes(self):
        """Non-ingestion endpoints are not intercepted."""
        config = SecurityConfig(allowed_ingest_dirs=[Path("/allowed")])
        middleware = PathTraversalGuard(MagicMock(), config=config)
        request = MagicMock()
        request.method = "POST"
        request.url.path = "/api/query"
        next_response = MagicMock()
        response = _run_async(middleware.dispatch(request, _make_call_next(next_response)))
        self.assertEqual(response, next_response)

    def test_get_ingest_passes(self):
        """GET requests to /api/ingest are not intercepted."""
        config = SecurityConfig(allowed_ingest_dirs=[Path("/allowed")])
        middleware = PathTraversalGuard(MagicMock(), config=config)
        request = MagicMock()
        request.method = "GET"
        request.url.path = "/api/ingest"
        next_response = MagicMock()
        response = _run_async(middleware.dispatch(request, _make_call_next(next_response)))
        self.assertEqual(response, next_response)

    def test_allowed_path_passes(self):
        """Ingestion with allowed path passes through."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SecurityConfig(allowed_ingest_dirs=[Path(tmpdir)])
            middleware = PathTraversalGuard(MagicMock(), config=config)
            request = MagicMock()
            request.method = "POST"
            request.url.path = "/api/ingest"
            body = json.dumps({"file_path": str(Path(tmpdir) / "doc.pdf")}).encode()
            async def _body(): return body
            request.body = _body
            next_response = MagicMock()
            response = _run_async(middleware.dispatch(request, _make_call_next(next_response)))
            self.assertEqual(response, next_response)

    def test_disallowed_path_returns_403(self):
        """Ingestion with disallowed path returns 403."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SecurityConfig(allowed_ingest_dirs=[Path(tmpdir) / "allowed"])
            middleware = PathTraversalGuard(MagicMock(), config=config)
            request = MagicMock()
            request.method = "POST"
            request.url.path = "/api/ingest"
            body = json.dumps({"file_path": "/etc/passwd"}).encode()
            async def _body(): return body
            request.body = _body
            response = _run_async(middleware.dispatch(request, _make_call_next(MagicMock())))
            self.assertEqual(response.status_code, 403)

    def test_malformed_body_passes(self):
        """Malformed JSON body does not crash the middleware."""
        config = SecurityConfig(allowed_ingest_dirs=[Path("/allowed")])
        middleware = PathTraversalGuard(MagicMock(), config=config)
        request = MagicMock()
        request.method = "POST"
        request.url.path = "/api/ingest"
        async def _body(): return b"not json {{{"
        request.body = _body
        next_response = MagicMock()
        response = _run_async(middleware.dispatch(request, _make_call_next(next_response)))
        self.assertEqual(response, next_response)

    def test_empty_body_passes(self):
        """Empty body does not crash the middleware."""
        config = SecurityConfig(allowed_ingest_dirs=[Path("/allowed")])
        middleware = PathTraversalGuard(MagicMock(), config=config)
        request = MagicMock()
        request.method = "POST"
        request.url.path = "/api/ingest"
        async def _body(): return b""
        request.body = _body
        next_response = MagicMock()
        response = _run_async(middleware.dispatch(request, _make_call_next(next_response)))
        self.assertEqual(response, next_response)


# ==================================================================
# 4. Audit Log tests
# ==================================================================

class TestAuditLog(unittest.TestCase):
    """Tests for the AuditLog middleware."""

    def test_audit_disabled_no_log(self):
        """When audit_enabled=False, no log entries are written."""
        config = SecurityConfig(audit_enabled=False)
        middleware = AuditLog(MagicMock(), config=config)
        request = MagicMock()
        request.method = "GET"
        request.url.path = "/api/health"
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        _run_async(middleware.dispatch(request, _make_call_next(MagicMock(status_code=200))))
        self.assertIsNone(middleware._log_file)

    def test_audit_writes_entries(self):
        """When audit_enabled=True, entries are written to log file."""
        log_path = os.path.join(tempfile.gettempdir(), "test_audit_1.log")
        try:
            config = SecurityConfig(audit_enabled=True, audit_log_path=log_path)
            middleware = AuditLog(MagicMock(), config=config)
            request = MagicMock()
            request.method = "POST"
            request.url.path = "/api/query"
            request.headers = {"X-API-Key": "present"}
            request.client = MagicMock()
            request.client.host = "10.0.0.1"
            _run_async(middleware.dispatch(request, _make_call_next(MagicMock(status_code=200))))
            # Close the log file before reading
            if middleware._log_file:
                middleware._log_file.close()
            with open(log_path) as f:
                line = f.readline().strip()
            entry = json.loads(line)
            self.assertEqual(entry["method"], "POST")
            self.assertEqual(entry["path"], "/api/query")
            self.assertEqual(entry["status_code"], 200)
            self.assertEqual(entry["client_ip"], "10.0.0.1")
            self.assertTrue(entry["api_key_present"])
            self.assertIn("timestamp", entry)
            self.assertIn("duration_ms", entry)
        finally:
            try: os.unlink(log_path)
            except OSError: pass

    def test_audit_logs_client_ip(self):
        """Audit entry includes client IP address."""
        log_path = os.path.join(tempfile.gettempdir(), "test_audit_2.log")
        try:
            config = SecurityConfig(audit_enabled=True, audit_log_path=log_path)
            middleware = AuditLog(MagicMock(), config=config)
            request = MagicMock()
            request.method = "GET"
            request.url.path = "/api/health"
            request.headers = {}
            request.client = MagicMock()
            request.client.host = "192.168.1.100"
            _run_async(middleware.dispatch(request, _make_call_next(MagicMock(status_code=200))))
            if middleware._log_file:
                middleware._log_file.close()
            with open(log_path) as f:
                entry = json.loads(f.readline().strip())
            self.assertEqual(entry["client_ip"], "192.168.1.100")
        finally:
            try: os.unlink(log_path)
            except OSError: pass

    def test_audit_records_api_key_presence(self):
        """Audit entry records whether API key was present (not the key itself)."""
        log_path = os.path.join(tempfile.gettempdir(), "test_audit_3.log")
        try:
            config = SecurityConfig(audit_enabled=True, audit_log_path=log_path)
            middleware = AuditLog(MagicMock(), config=config)
            request = MagicMock()
            request.method = "GET"
            request.url.path = "/api/test"
            request.headers = {"X-API-Key": "secret123"}
            request.client = MagicMock()
            request.client.host = "127.0.0.1"
            _run_async(middleware.dispatch(request, _make_call_next(MagicMock(status_code=200))))
            if middleware._log_file:
                middleware._log_file.close()
            with open(log_path) as f:
                entry = json.loads(f.readline().strip())
            self.assertTrue(entry["api_key_present"])
            # Key itself should NOT be in the log
            self.assertNotIn("secret123", json.dumps(entry))
        finally:
            try: os.unlink(log_path)
            except OSError: pass


# ==================================================================
# 5. VisibilityFilter on /api/query integration test
# ==================================================================

class TestQueryEndpointVisibility(unittest.TestCase):
    """
    Verify that the /api/query endpoint enforces visibility filtering.

    This tests the chat.py router code directly.
    """

    def test_query_router_uses_visibility_filter(self):
        """The query_knowledge function imports and uses VisibilityFilter."""
        # Read the source code and verify the filter is present
        import inspect
        from command_center.backend.routers.chat import query_knowledge
        source = inspect.getsource(query_knowledge)
        self.assertIn("VisibilityFilter", source)
        self.assertIn("VisibilityLevel", source)
        self.assertIn("vf.wrap", source)

    def test_ask_router_uses_visibility_filter(self):
        """The ask_evidence_grounded function uses VisibilityFilter."""
        import inspect
        from command_center.backend.routers.chat import ask_evidence_grounded
        source = inspect.getsource(ask_evidence_grounded)
        self.assertIn("VisibilityFilter", source)
        self.assertIn("VisibilityLevel", source)


# ==================================================================
# 6. Main app wiring test
# ==================================================================

class TestAppSecurityWiring(unittest.TestCase):
    """Verify that main.py wires in all security middleware."""

    def test_main_imports_security(self):
        """main.py imports SecurityConfig and middleware."""
        import inspect
        from command_center.backend.main import app
        source_file = Path(__file__).parent.parent / "command_center" / "backend" / "main.py"
        source = source_file.read_text()
        self.assertIn("SecurityConfig", source)
        self.assertIn("APIKeyAuth", source)
        self.assertIn("AuditLog", source)
        self.assertIn("PathTraversalGuard", source)

    def test_cors_not_wildcard_by_default(self):
        """CORS uses SecurityConfig.cors_origins, not hardcoded *."""
        source_file = Path(__file__).parent.parent / "command_center" / "backend" / "main.py"
        source = source_file.read_text()
        # Should reference _security.cors_origins, not hardcoded ["*"]
        self.assertIn("_security.cors_origins", source)

    def test_documents_router_has_path_guard(self):
        """documents.py validates paths before ingestion."""
        import inspect
        from command_center.backend.routers.documents import ingest_document
        source = inspect.getsource(ingest_document)
        self.assertIn("SecurityConfig", source)
        self.assertIn("is_path_allowed", source)
        self.assertIn("403", source)


if __name__ == "__main__":
    unittest.main()
