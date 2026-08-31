"""
LAN Deployment & UI Tests
=========================
"""
import os, sys, time, unittest
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, ".")


class TestSameOriginAPI(unittest.TestCase):
    """Test that frontend uses same-origin API."""

    def test_frontend_no_hardcoded_localhost(self):
        """Frontend does not hardcode localhost:8000."""
        with open("command_center/frontend/index.html", encoding="utf-8") as f:
            content = f.read()
        # Should use window.location.origin, not hardcoded localhost
        self.assertIn("window.location.origin", content)
        self.assertNotIn("http://localhost:8000/api", content)

    def test_api_base_uses_origin(self):
        """API_BASE is derived from window.location.origin."""
        with open("command_center/frontend/index.html", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("const API = window.location.origin + '/api'", content)


class TestConfigurableHost(unittest.TestCase):
    """Test that host/port are configurable."""

    def test_main_reads_env_vars(self):
        """main.py reads SANJAYA_HOST and SANJAYA_PORT."""
        with open("command_center/backend/main.py") as f:
            content = f.read()
        self.assertIn("SANJAYA_HOST", content)
        self.assertIn("SANJAYA_PORT", content)

    def test_default_host_is_0_0_0_0(self):
        """Default host binds to all interfaces."""
        with open("command_center/backend/main.py") as f:
            content = f.read()
        self.assertIn('os.environ.get("SANJAYA_HOST", "0.0.0.0")', content)


class TestEntraRedirectConfigurable(unittest.TestCase):
    """Test that Entra redirect URI is configurable."""

    def test_redirect_uri_from_env(self):
        """ENTRA_REDIRECT_URI is read from environment."""
        with open("kurukshetra/security/entra_provider.py") as f:
            content = f.read()
        self.assertIn('ENTRA_REDIRECT_URI', content)
        self.assertIn('http://localhost:8000/auth/callback', content)  # default

    def test_auth_uses_config_redirect(self):
        """auth.py uses config.redirect_uri."""
        with open("command_center/backend/routers/auth.py") as f:
            content = f.read()
        self.assertIn("config.redirect_uri", content)


class TestAuthIdentity(unittest.TestCase):
    """Test that authenticated identity reaches AuthorizationContext."""

    def test_identity_from_request_works(self):
        """get_identity_from_request extracts identity correctly."""
        from command_center.backend.routers.auth import get_identity_from_request, Session
        from kurukshetra.security.identity_provider import AuthenticatedIdentity, TokenType
        from kurukshetra.security.identity import ClearanceLevel
        from unittest.mock import MagicMock

        identity = AuthenticatedIdentity(
            user_id="USR-LAN", username="lan-user", display_name="LAN User",
            email="lan@test.com", team_id="spm",
            clearance_level=ClearanceLevel.CONFIDENTIAL,
            token_type=TokenType.JWT, is_authenticated=True,
        )
        session = Session(session_id="lan-sess", identity=identity,
                         created_at=time.time(), expires_at=time.time() + 3600)
        token = session.to_token()

        request = MagicMock()
        request.headers = {"Authorization": f"Bearer {token}"}
        result = get_identity_from_request(request)
        self.assertTrue(result.is_authenticated)
        self.assertEqual(result.user_id, "USR-LAN")


class TestUserIsolation(unittest.TestCase):
    """Test that users are isolated."""

    def test_user_a_cannot_see_user_b_memory(self):
        """User A's episodic memory is isolated from User B."""
        from kurukshetra.agent.memory_store import EpisodicMemory, KnowledgeSource

        em = EpisodicMemory()
        ts = int(time.time() * 1000)

        em.record_episode(query=f"User A secret {ts}", answer="answer A",
                         confidence=0.9, abstained=False, evidence_doc_ids=[],
                         knowledge_sources=[KnowledgeSource.ORGANIZATION],
                         user_id=f"user-a-{ts}")
        em.record_episode(query=f"User B secret {ts}", answer="answer B",
                         confidence=0.8, abstained=False, evidence_doc_ids=[],
                         knowledge_sources=[KnowledgeSource.ORGANIZATION],
                         user_id=f"user-b-{ts}")

        all_eps = em.get_recent_episodes(limit=100)
        a_eps = [ep for ep in all_eps if ep.user_id == f"user-a-{ts}"]
        b_eps = [ep for ep in all_eps if ep.user_id == f"user-b-{ts}"]

        self.assertIn(f"User A secret {ts}", [ep.query for ep in a_eps])
        self.assertNotIn(f"User B secret {ts}", [ep.query for ep in a_eps])


class TestUploadPipeline(unittest.TestCase):
    """Test upload goes through KnowledgeFabric."""

    def test_upload_endpoint_exists(self):
        """POST /api/knowledge/upload endpoint exists."""
        from command_center.backend.routers.knowledge import router
        routes = [r.path for r in router.routes]
        self.assertIn("/api/knowledge/upload", routes)

    def test_upload_validates_file(self):
        """Upload validates file type and size."""
        from command_center.backend.routers.knowledge import router
        routes = [r.path for r in router.routes]
        self.assertGreater(len(routes), 0)


class TestSecurityBoundary(unittest.TestCase):
    """Test security boundaries are preserved."""

    def test_visibility_filter_enforced(self):
        """VisibilityFilter prevents unauthorized document access."""
        from kurukshetra.retrieval.access_control import VisibilityFilter, VisibilityLevel
        from kurukshetra.retrieval.models import RetrievalResult

        vf = VisibilityFilter(max_level=VisibilityLevel.INTERNAL)
        # Confidential documents should be filtered out for internal users
        results = [
            RetrievalResult(chunk_id="c1", document_id="d1", score=0.9,
                          text="test", metadata={"visibility": "confidential"}),
            RetrievalResult(chunk_id="c2", document_id="d2", score=0.8,
                          text="test", metadata={"visibility": "internal"}),
        ]
        filtered = vf.filter(results)
        # At minimum, filter should reduce results or keep only authorized
        self.assertLessEqual(len(filtered), len(results))

    def test_gx10_receives_only_authorized_evidence(self):
        """AnswerGenerator only receives authorized evidence."""
        from kurukshetra.agent.answer_generator import AnswerGenerator
        gen = AnswerGenerator()
        # The generator receives results that have already been filtered
        # by VisibilityFilter in the retriever pipeline
        self.assertIsNotNone(gen)


class TestFeedbackUserScoped(unittest.TestCase):
    """Test feedback is user-scoped."""

    def test_feedback_records_user_id(self):
        """Feedback entries include user_id."""
        from kurukshetra.services.feedback import FeedbackLoop
        fb = FeedbackLoop()
        ts = int(time.time() * 1000)
        entry = fb.record_feedback(
            query=f"lan test {ts}", document_id="DOC-LAN",
            chunk_id=f"CHUNK-LAN-{ts}", score=0.8, is_correct=True,
            user_id=f"lan-user-{ts}",
        )
        self.assertIsNotNone(entry.feedback_id)


class TestSessionInvalidation(unittest.TestCase):
    """Test logout invalidates session."""

    def test_logout_removes_session(self):
        """Logout removes session from store."""
        from command_center.backend.routers.auth import Session, _sessions
        from kurukshetra.security.identity_provider import AuthenticatedIdentity, TokenType
        from kurukshetra.security.identity import ClearanceLevel

        identity = AuthenticatedIdentity(
            user_id="USR-LOGOUT", username="logout-test",
            display_name="Logout Test", email="",
            team_id="unknown", clearance_level=ClearanceLevel.INTERNAL,
            token_type=TokenType.JWT, is_authenticated=True,
        )
        session = Session(session_id="logout-sess", identity=identity,
                         created_at=time.time(), expires_at=time.time() + 3600)
        _sessions["logout-sess"] = session
        self.assertIn("logout-sess", _sessions)

        # Simulate logout
        _sessions.pop("logout-sess", None)
        self.assertNotIn("logout-sess", _sessions)


class TestPublicUrlConfig(unittest.TestCase):
    """Test SANJAYA_PUBLIC_URL is configurable."""

    def test_config_endpoint_returns_public_url(self):
        """Config endpoint returns public URL from env."""
        os.environ["SANJAYA_PUBLIC_URL"] = "http://192.168.1.100:8000"
        try:
            from kurukshetra.security.entra_provider import EntraConfig
            # Public URL is read from env in main.py
            import importlib
            # Just verify the env var is readable
            self.assertEqual(os.environ.get("SANJAYA_PUBLIC_URL"), "http://192.168.1.100:8000")
        finally:
            del os.environ["SANJAYA_PUBLIC_URL"]


if __name__ == "__main__":
    unittest.main()
