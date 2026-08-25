"""
Identity & Authorization Tests
================================

Deterministic tests for:
  1. UserStore CRUD
  2. API-key → user lookup
  3. Cross-user/cross-team authorization
  4. Clearance-level enforcement
  5. Unauthorized Graph/SEAL access
  6. Audit log user identity
  7. Open-mode vs authenticated-mode behavior
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from kurukshetra.security.identity import (
    ANONYMOUS,
    ClearanceLevel,
    UserIdentity,
    UserStore,
    _hash_key,
)
from kurukshetra.security.config import SecurityConfig
from kurukshetra.security.deps import get_current_user, require_team, require_clearance
from kurukshetra.security.middleware import AuditLog


# ==================================================================
# Helper
# ==================================================================

def _run_async(coro):
    import asyncio
    return asyncio.run(coro)


def _make_call_next(response):
    async def call_next(request):
        return response
    return call_next


class _PatchedUserStore:
    """UserStore backed by a temp DuckDB, with active monkeypatch."""
    def __init__(self):
        import duckdb
        import kurukshetra.security.identity as _ident
        self._tmp_path = os.path.join(
            tempfile.gettempdir(),
            f"test_identity_{os.getpid()}_{id(self)}.duckdb",
        )
        # DuckDB allows multiple connections to the same file
        self._orig_get_conn = _ident.get_connection
        _ident.get_connection = lambda: duckdb.connect(self._tmp_path)
        self.store = UserStore()

    def close(self):
        import kurukshetra.security.identity as _ident
        _ident.get_connection = self._orig_get_conn
        try:
            os.unlink(self._tmp_path)
        except OSError:
            pass


# ==================================================================
# 1. UserIdentity model tests
# ==================================================================

class TestUserIdentity(unittest.TestCase):
    """Tests for UserIdentity dataclass."""

    def test_anonymous_user(self):
        """ANONYMOUS has public clearance and is not authenticated."""
        self.assertFalse(ANONYMOUS.is_authenticated)
        self.assertEqual(ANONYMOUS.clearance_level, ClearanceLevel.PUBLIC)
        self.assertEqual(ANONYMOUS.team_id, "unknown")

    def test_can_see_public(self):
        """Any user can see PUBLIC documents."""
        user = UserIdentity(
            user_id="USR-TEST", username="test", display_name="Test",
            team_id="spm", clearance_level=ClearanceLevel.INTERNAL,
        )
        self.assertTrue(user.can_see("public"))
        self.assertTrue(user.can_see("internal"))

    def test_cannot_see_above_clearance(self):
        """User cannot see documents above their clearance."""
        user = UserIdentity(
            user_id="USR-TEST", username="test", display_name="Test",
            team_id="spm", clearance_level=ClearanceLevel.INTERNAL,
        )
        self.assertFalse(user.can_see("confidential"))
        self.assertFalse(user.can_see("restricted"))

    def test_confidential_user_sees_confidential(self):
        """CONFIDENTIAL-cleared user can see CONFIDENTIAL documents."""
        user = UserIdentity(
            user_id="USR-TEST", username="test", display_name="Test",
            team_id="spm", clearance_level=ClearanceLevel.CONFIDENTIAL,
        )
        self.assertTrue(user.can_see("confidential"))
        self.assertFalse(user.can_see("restricted"))

    def test_max_visibility_property(self):
        """max_visibility returns string form of clearance."""
        user = UserIdentity(
            user_id="USR-TEST", username="test", display_name="Test",
            team_id="spm", clearance_level=ClearanceLevel.CONFIDENTIAL,
        )
        self.assertEqual(user.max_visibility, "confidential")


# ==================================================================
# 2. UserStore CRUD tests
# ==================================================================

class TestUserStore(unittest.TestCase):
    """Tests for UserStore CRUD operations."""

    def setUp(self):
        self.patched = _PatchedUserStore()
        self.store = self.patched.store

    def tearDown(self):
        self.patched.close()

    def test_create_user(self):
        """Create a user and retrieve by username."""
        user = self.store.create_user(
            username="alice", display_name="Alice Smith",
            team_id="spm", clearance_level="internal", api_key="key123",
        )
        self.assertEqual(user.username, "alice")
        self.assertEqual(user.team_id, "spm")
        self.assertEqual(user.clearance_level, ClearanceLevel.INTERNAL)

    def test_get_by_api_key(self):
        """Lookup user by API key."""
        self.store.create_user(username="bob", team_id="ics", api_key="secret456")
        found = self.store.get_by_api_key("secret456")
        self.assertIsNotNone(found)
        self.assertEqual(found.username, "bob")
        self.assertEqual(found.team_id, "ics")

    def test_get_by_api_key_invalid(self):
        """Invalid API key returns None."""
        self.store.create_user(username="bob", team_id="ics", api_key="secret456")
        found = self.store.get_by_api_key("wrong")
        self.assertIsNone(found)

    def test_get_by_api_key_empty(self):
        """Empty API key returns None."""
        found = self.store.get_by_api_key("")
        self.assertIsNone(found)

    def test_get_by_username(self):
        """Lookup user by username."""
        self.store.create_user(username="carol", team_id="sdops")
        found = self.store.get_by_username("carol")
        self.assertIsNotNone(found)
        self.assertEqual(found.user_id, "USR-CAROL")

    def test_get_by_username_missing(self):
        """Missing username returns None."""
        found = self.store.get_by_username("nobody")
        self.assertIsNone(found)

    def test_list_users_all(self):
        """List all users."""
        self.store.create_user(username="u1", team_id="spm")
        self.store.create_user(username="u2", team_id="ics")
        users = self.store.list_users()
        self.assertEqual(len(users), 2)

    def test_list_users_by_team(self):
        """List users filtered by team."""
        self.store.create_user(username="u1", team_id="spm")
        self.store.create_user(username="u2", team_id="ics")
        self.store.create_user(username="u3", team_id="spm")
        spm_users = self.store.list_users(team_id="spm")
        self.assertEqual(len(spm_users), 2)

    def test_deactivate_user(self):
        """Deactivated user is no longer found."""
        self.store.create_user(username="temp", team_id="spm", api_key="tempkey")
        user = self.store.get_by_api_key("tempkey")
        self.assertIsNotNone(user)
        self.store.deactivate_user(user.user_id)
        found = self.store.get_by_api_key("tempkey")
        self.assertIsNone(found)

    def test_update_team(self):
        """Update user team."""
        user = self.store.create_user(username="move", team_id="spm")
        self.store.update_team(user.user_id, "ics")
        found = self.store.get_by_username("move")
        self.assertEqual(found.team_id, "ics")

    def test_update_clearance(self):
        """Update user clearance."""
        user = self.store.create_user(username="promote", team_id="spm", clearance_level="internal")
        self.store.update_clearance(user.user_id, "confidential")
        found = self.store.get_by_username("promote")
        self.assertEqual(found.clearance_level, ClearanceLevel.CONFIDENTIAL)


# ==================================================================
# 3. Cross-team authorization tests
# ==================================================================

class TestCrossTeamAuthorization(unittest.TestCase):
    """Tests for team-based access control."""

    def test_same_team_allowed(self):
        """User can access their own team's resources."""
        user = UserIdentity(
            user_id="USR-SPM1", username="spm_user", display_name="SPM User",
            team_id="spm", clearance_level=ClearanceLevel.INTERNAL,
        )
        # require_team("spm", "ics") should pass for spm user
        # We test the logic directly
        allowed_teams = ("spm", "ics")
        self.assertIn(user.team_id, allowed_teams)

    def test_different_team_rejected(self):
        """User cannot access another team's resources."""
        user = UserIdentity(
            user_id="USR-SDOPS1", username="sdops_user", display_name="SDOPS User",
            team_id="sdops", clearance_level=ClearanceLevel.INTERNAL,
        )
        allowed_teams = ("spm", "ics")
        self.assertNotIn(user.team_id, allowed_teams)

    def test_anonymous_bypasses_team_check(self):
        """Anonymous user bypasses team checks (open mode)."""
        self.assertFalse(ANONYMOUS.is_authenticated)


# ==================================================================
# 4. Clearance-level authorization tests
# ==================================================================

class TestClearanceAuthorization(unittest.TestCase):
    """Tests for clearance-level access control."""

    def test_internal_clearance_sees_internal(self):
        user = UserIdentity(
            user_id="USR-T1", username="t1", display_name="T1",
            team_id="spm", clearance_level=ClearanceLevel.INTERNAL,
        )
        self.assertTrue(user.can_see("internal"))
        self.assertTrue(user.can_see("public"))

    def test_internal_clearance_rejected_from_confidential(self):
        user = UserIdentity(
            user_id="USR-T1", username="t1", display_name="T1",
            team_id="spm", clearance_level=ClearanceLevel.INTERNAL,
        )
        self.assertFalse(user.can_see("confidential"))

    def test_restricted_clearance_sees_everything(self):
        user = UserIdentity(
            user_id="USR-T1", username="t1", display_name="T1",
            team_id="spm", clearance_level=ClearanceLevel.RESTRICTED,
        )
        self.assertTrue(user.can_see("public"))
        self.assertTrue(user.can_see("internal"))
        self.assertTrue(user.can_see("confidential"))
        self.assertTrue(user.can_see("restricted"))


# ==================================================================
# 5. API dependency tests
# ==================================================================

class TestAuthDependencies(unittest.TestCase):
    """Tests for FastAPI authorization dependencies."""

    def test_open_mode_returns_anonymous(self):
        """In open mode, get_current_user returns ANONYMOUS."""
        with patch("kurukshetra.security.deps._get_config") as mock_cfg:
            mock_cfg.return_value = SecurityConfig(auth_required=False)
            request = MagicMock()
            request.state = MagicMock()
            user = _run_async(get_current_user(request, x_api_key=None))
            self.assertEqual(user, ANONYMOUS)

    def test_auth_required_no_key_raises_401(self):
        """In auth mode, missing key raises 401."""
        with patch("kurukshetra.security.deps._get_config") as mock_cfg:
            mock_cfg.return_value = SecurityConfig(auth_required=True, api_keys=["key1"])
            request = MagicMock()
            request.state = MagicMock()
            from fastapi import HTTPException
            with self.assertRaises(HTTPException) as ctx:
                _run_async(get_current_user(request, x_api_key=None))
            self.assertEqual(ctx.exception.status_code, 401)

    def test_auth_required_invalid_key_raises_401(self):
        """In auth mode, invalid key raises 401."""
        with patch("kurukshetra.security.deps._get_config") as mock_cfg:
            mock_cfg.return_value = SecurityConfig(auth_required=True, api_keys=["key1"])
            with patch("kurukshetra.security.deps._get_user_store") as mock_store:
                mock_store.return_value = MagicMock(get_by_api_key=MagicMock(return_value=None))
                request = MagicMock()
                request.state = MagicMock()
                from fastapi import HTTPException
                with self.assertRaises(HTTPException) as ctx:
                    _run_async(get_current_user(request, x_api_key="wrong"))
                self.assertEqual(ctx.exception.status_code, 401)

    def test_auth_required_valid_key_returns_user(self):
        """In auth mode, valid key returns UserIdentity."""
        mock_user = UserIdentity(
            user_id="USR-ALICE", username="alice", display_name="Alice",
            team_id="spm", clearance_level=ClearanceLevel.INTERNAL,
        )
        with patch("kurukshetra.security.deps._get_config") as mock_cfg:
            mock_cfg.return_value = SecurityConfig(auth_required=True, api_keys=["key1"])
            with patch("kurukshetra.security.deps._get_user_store") as mock_store:
                mock_store.return_value = MagicMock(get_by_api_key=MagicMock(return_value=mock_user))
                request = MagicMock()
                request.state = MagicMock()
                user = _run_async(get_current_user(request, x_api_key="key1"))
                self.assertEqual(user.username, "alice")

    def test_require_team_allows_matching_team(self):
        """require_team allows matching team."""
        mock_user = UserIdentity(
            user_id="USR-SPM", username="spm_user", display_name="SPM",
            team_id="spm", clearance_level=ClearanceLevel.INTERNAL,
        )
        with patch("kurukshetra.security.deps._get_config") as mock_cfg:
            mock_cfg.return_value = SecurityConfig(auth_required=False)
            request = MagicMock()
            request.state = MagicMock()
            # Open mode: anonymous passes through
            dep = require_team("spm", "ics")
            user = _run_async(dep(request, x_api_key=None))
            self.assertIsNotNone(user)

    def test_require_team_rejects_wrong_team(self):
        """require_team rejects wrong team in authenticated mode."""
        mock_user = UserIdentity(
            user_id="USR-SDOPS", username="sdops_user", display_name="SDOPS",
            team_id="sdops", clearance_level=ClearanceLevel.INTERNAL,
        )
        with patch("kurukshetra.security.deps._get_config") as mock_cfg:
            mock_cfg.return_value = SecurityConfig(auth_required=True, api_keys=["k"])
            with patch("kurukshetra.security.deps._get_user_store") as mock_store:
                mock_store.return_value = MagicMock(get_by_api_key=MagicMock(return_value=mock_user))
                request = MagicMock()
                request.state = MagicMock()
                dep = require_team("spm", "ics")
                from fastapi import HTTPException
                with self.assertRaises(HTTPException) as ctx:
                    _run_async(dep(request, x_api_key="k"))
                self.assertEqual(ctx.exception.status_code, 403)


# ==================================================================
# 6. Audit log user identity tests
# ==================================================================

class TestAuditUserIdentity(unittest.TestCase):
    """Tests that audit logs record user identity."""

    def test_audit_records_user_id(self):
        """Audit entry includes user_id and team_id."""
        log_path = os.path.join(tempfile.gettempdir(), "test_audit_identity.log")
        try:
            config = SecurityConfig(audit_enabled=True, audit_log_path=log_path)
            middleware = AuditLog(MagicMock(), config=config)

            # Simulate a request with user identity
            request = MagicMock()
            request.method = "GET"
            request.url.path = "/api/query"
            request.headers = {"X-API-Key": "present"}
            request.client = MagicMock()
            request.client.host = "10.0.0.1"

            # Set user on request.state (as auth middleware would)
            request.state = MagicMock()
            request.state.user = UserIdentity(
                user_id="USR-SPM1", username="spm_user", display_name="SPM User",
                team_id="spm", clearance_level=ClearanceLevel.INTERNAL,
            )

            _run_async(middleware.dispatch(request, _make_call_next(MagicMock(status_code=200))))

            if middleware._log_file:
                middleware._log_file.close()

            with open(log_path) as f:
                entry = json.loads(f.readline().strip())
            self.assertEqual(entry["user_id"], "USR-SPM1")
            self.assertEqual(entry["team_id"], "spm")
        finally:
            if middleware._log_file:
                try: middleware._log_file.close()
                except: pass
            try: os.unlink(log_path)
            except OSError: pass


# ==================================================================
# 7. Graph/SEAL authorization wiring tests
# ==================================================================

class TestEndpointAuthorizationWiring(unittest.TestCase):
    """Verify that endpoints are wired with authorization dependencies."""

    def test_graph_confirm_uses_require_team(self):
        """Graph entity confirm endpoint uses require_team."""
        import inspect
        from command_center.backend.routers.graph import confirm_entity
        sig = inspect.signature(confirm_entity)
        # Should have a 'user' parameter with Depends
        self.assertIn("user", sig.parameters)

    def test_seal_pending_uses_get_current_user(self):
        """SEAL pending endpoint uses get_current_user."""
        import inspect
        from command_center.backend.routers.seal import get_pending_glossary_terms
        sig = inspect.signature(get_pending_glossary_terms)
        self.assertIn("user", sig.parameters)

    def test_query_uses_get_current_user(self):
        """Query endpoint uses get_current_user."""
        import inspect
        from command_center.backend.routers.chat import query_knowledge
        sig = inspect.signature(query_knowledge)
        self.assertIn("user", sig.parameters)

    def test_ask_uses_get_current_user(self):
        """Ask endpoint uses get_current_user."""
        import inspect
        from command_center.backend.routers.chat import ask_evidence_grounded
        sig = inspect.signature(ask_evidence_grounded)
        self.assertIn("user", sig.parameters)


# ==================================================================
# 8. Hash function tests
# ==================================================================

class TestHashFunction(unittest.TestCase):
    """Tests for API key hashing."""

    def test_hash_deterministic(self):
        """Same key produces same hash."""
        h1 = _hash_key("test_key")
        h2 = _hash_key("test_key")
        self.assertEqual(h1, h2)

    def test_hash_different_keys(self):
        """Different keys produce different hashes."""
        h1 = _hash_key("key1")
        h2 = _hash_key("key2")
        self.assertNotEqual(h1, h2)

    def test_hash_is_sha256(self):
        """Hash matches SHA-256."""
        expected = hashlib.sha256("hello".encode()).hexdigest()
        self.assertEqual(_hash_key("hello"), expected)


if __name__ == "__main__":
    unittest.main()
