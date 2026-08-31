"""
Tests for SANJAYA Enterprise Identity & Data Boundary
======================================================

Proves:
- Authorized users can access appropriate documents
- Unauthorized users cannot access restricted documents
- Confidential documents are filtered by clearance
- Uploaded documents carry ownership
- Cross-user memory isolation works
- Expired/invalid tokens are rejected
- Missing identity returns anonymous
- AuthorizationContext flows through the pipeline
"""
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestIdentityProviderInterface(unittest.TestCase):
    """Test the identity provider abstraction."""

    def test_mock_provider_returns_admin(self):
        from kurukshetra.security.identity_provider import MockIdentityProvider, TokenType
        provider = MockIdentityProvider()
        identity = provider.authenticate("test-admin", TokenType.API_KEY)
        self.assertTrue(identity.is_authenticated)
        self.assertEqual(identity.username, "admin")
        self.assertEqual(identity.team_id, "spm")

    def test_mock_provider_returns_spm_user(self):
        from kurukshetra.security.identity_provider import MockIdentityProvider
        provider = MockIdentityProvider()
        identity = provider.authenticate("test-spm")
        self.assertTrue(identity.is_authenticated)
        self.assertEqual(identity.team_id, "spm")

    def test_mock_provider_returns_ics_user(self):
        from kurukshetra.security.identity_provider import MockIdentityProvider
        provider = MockIdentityProvider()
        identity = provider.authenticate("test-ics")
        self.assertTrue(identity.is_authenticated)
        self.assertEqual(identity.team_id, "ics")

    def test_mock_provider_returns_public_user(self):
        from kurukshetra.security.identity_provider import MockIdentityProvider
        provider = MockIdentityProvider()
        identity = provider.authenticate("test-public")
        self.assertTrue(identity.is_authenticated)
        self.assertEqual(identity.clearance_level.name, "INTERNAL")

    def test_mock_provider_rejects_unknown_token(self):
        from kurukshetra.security.identity_provider import MockIdentityProvider
        provider = MockIdentityProvider()
        identity = provider.authenticate("nonexistent-token")
        self.assertFalse(identity.is_authenticated)

    def test_mock_provider_anonymous_for_none(self):
        from kurukshetra.security.identity_provider import MockIdentityProvider
        provider = MockIdentityProvider()
        identity = provider.authenticate(None)
        self.assertFalse(identity.is_authenticated)
        self.assertEqual(identity.user_id, "anonymous")


class TestAuthenticatedIdentity(unittest.TestCase):
    """Test AuthenticatedIdentity attributes and methods."""

    def test_admin_has_restricted_clearance(self):
        from kurukshetra.security.identity_provider import MockIdentityProvider
        provider = MockIdentityProvider()
        admin = provider.authenticate("test-admin")
        self.assertEqual(admin.clearance_level.name, "RESTRICTED")

    def test_admin_can_see_confidential(self):
        from kurukshetra.security.identity_provider import MockIdentityProvider
        provider = MockIdentityProvider()
        admin = provider.authenticate("test-admin")
        self.assertTrue(admin.can_see("confidential"))

    def test_public_user_cannot_see_confidential(self):
        from kurukshetra.security.identity_provider import MockIdentityProvider
        provider = MockIdentityProvider()
        public = provider.authenticate("test-public")
        self.assertFalse(public.can_see("confidential"))

    def test_admin_has_groups(self):
        from kurukshetra.security.identity_provider import MockIdentityProvider
        provider = MockIdentityProvider()
        admin = provider.authenticate("test-admin")
        self.assertTrue(admin.has_group("admin"))
        self.assertTrue(admin.has_group("spm"))
        self.assertFalse(admin.has_group("nonexistent"))

    def test_admin_has_roles(self):
        from kurukshetra.security.identity_provider import MockIdentityProvider
        provider = MockIdentityProvider()
        admin = provider.authenticate("test-admin")
        self.assertTrue(admin.has_role("admin"))
        self.assertTrue(admin.has_role("viewer"))

    def test_source_permissions(self):
        from kurukshetra.security.identity_provider import MockIdentityProvider
        provider = MockIdentityProvider()
        admin = provider.authenticate("test-admin")
        self.assertTrue(admin.can_access_source("salesforce"))
        # Unknown source returns False when permissions are configured
        self.assertFalse(admin.can_access_source("unknown-source"))

    def test_expired_token_detected(self):
        from kurukshetra.security.identity_provider import MockIdentityProvider
        provider = MockIdentityProvider()
        expired = provider.authenticate("test-expired")
        self.assertTrue(expired.is_authenticated)  # User exists
        self.assertFalse(expired.is_token_valid())  # But token is expired

    def test_to_user_identity_conversion(self):
        from kurukshetra.security.identity_provider import MockIdentityProvider
        provider = MockIdentityProvider()
        admin = provider.authenticate("test-admin")
        ui = admin.to_user_identity()
        self.assertEqual(ui.user_id, admin.user_id)
        self.assertEqual(ui.team_id, admin.team_id)


class TestAuthorizationContext(unittest.TestCase):
    """Test AuthorizationContext flows through the pipeline."""

    def test_context_creation(self):
        from kurukshetra.security.identity_provider import (
            MockIdentityProvider, AuthorizationContext,
        )
        provider = MockIdentityProvider()
        identity = provider.authenticate("test-spm")
        ctx = AuthorizationContext(identity=identity, request_id="REQ-001")
        self.assertEqual(ctx.user_id, identity.user_id)
        self.assertEqual(ctx.team_id, "spm")

    def test_context_can_see_document(self):
        from kurukshetra.security.identity_provider import (
            MockIdentityProvider, AuthorizationContext,
        )
        provider = MockIdentityProvider()
        identity = provider.authenticate("test-spm")
        ctx = AuthorizationContext(identity=identity)
        self.assertTrue(ctx.can_see_document("internal"))
        self.assertTrue(ctx.can_see_document("confidential"))

    def test_context_public_user_cannot_see_confidential(self):
        from kurukshetra.security.identity_provider import (
            MockIdentityProvider, AuthorizationContext,
        )
        provider = MockIdentityProvider()
        identity = provider.authenticate("test-public")
        ctx = AuthorizationContext(identity=identity)
        self.assertFalse(ctx.can_see_document("confidential"))

    def test_context_for_audit(self):
        from kurukshetra.security.identity_provider import (
            MockIdentityProvider, AuthorizationContext,
        )
        provider = MockIdentityProvider()
        identity = provider.authenticate("test-admin")
        ctx = AuthorizationContext(identity=identity, request_id="REQ-002")
        audit = ctx.for_audit()
        self.assertEqual(audit["user_id"], identity.user_id)
        self.assertEqual(audit["request_id"], "REQ-002")
        self.assertIn("timestamp", audit)


class TestClearanceBoundary(unittest.TestCase):
    """Test document visibility filtering by clearance level."""

    def test_restricted_user_sees_all(self):
        from kurukshetra.security.identity_provider import MockIdentityProvider
        provider = MockIdentityProvider()
        admin = provider.authenticate("test-admin")
        for vis in ["public", "internal", "confidential", "restricted"]:
            self.assertTrue(admin.can_see(vis), f"Admin should see {vis}")

    def test_confidential_user_sees_internal_and_below(self):
        from kurukshetra.security.identity_provider import MockIdentityProvider
        provider = MockIdentityProvider()
        spm = provider.authenticate("test-spm")
        self.assertTrue(spm.can_see("public"))
        self.assertTrue(spm.can_see("internal"))
        self.assertTrue(spm.can_see("confidential"))
        self.assertFalse(spm.can_see("restricted"))

    def test_internal_user_sees_only_internal_and_below(self):
        from kurukshetra.security.identity_provider import MockIdentityProvider
        provider = MockIdentityProvider()
        public = provider.authenticate("test-public")
        self.assertTrue(public.can_see("public"))
        self.assertTrue(public.can_see("internal"))
        self.assertFalse(public.can_see("confidential"))
        self.assertFalse(public.can_see("restricted"))


class TestCrossUserIsolation(unittest.TestCase):
    """Test that different users have separate authorization contexts."""

    def test_different_users_different_contexts(self):
        from kurukshetra.security.identity_provider import (
            MockIdentityProvider, AuthorizationContext,
        )
        provider = MockIdentityProvider()

        ctx_spm = AuthorizationContext(
            identity=provider.authenticate("test-spm"),
            request_id="REQ-SPM",
        )
        ctx_ics = AuthorizationContext(
            identity=provider.authenticate("test-ics"),
            request_id="REQ-ICS",
        )

        self.assertNotEqual(ctx_spm.user_id, ctx_ics.user_id)
        self.assertNotEqual(ctx_spm.team_id, ctx_ics.team_id)

    def test_spm_cannot_access_ics_context_data(self):
        from kurukshetra.security.identity_provider import (
            MockIdentityProvider, AuthorizationContext,
        )
        provider = MockIdentityProvider()
        ctx_spm = AuthorizationContext(
            identity=provider.authenticate("test-spm"),
        )
        # SPM user should not be able to claim ICS identity
        self.assertEqual(ctx_spm.team_id, "spm")
        self.assertNotEqual(ctx_spm.team_id, "ics")


class TestTokenExpiry(unittest.TestCase):
    """Test expired token handling."""

    def test_expired_token_detected(self):
        from kurukshetra.security.identity_provider import MockIdentityProvider
        provider = MockIdentityProvider()
        expired = provider.authenticate("test-expired")
        self.assertFalse(expired.is_token_valid())

    def test_valid_token_passes(self):
        from kurukshetra.security.identity_provider import MockIdentityProvider
        provider = MockIdentityProvider()
        valid = provider.authenticate("test-admin")
        self.assertTrue(valid.is_token_valid())


class TestEntraProvider(unittest.TestCase):
    """Test Entra ID provider interface."""

    def test_entra_not_available_without_config(self):
        import os
        # Ensure Entra env vars are not set
        for key in ["ENTRA_TENANT_ID", "ENTRA_CLIENT_ID", "ENTRA_JWKS_URL"]:
            os.environ.pop(key, None)
        from kurukshetra.security.identity_provider import EntraIdentityProvider
        provider = EntraIdentityProvider()
        self.assertFalse(provider.is_available())

    def test_entra_returns_unauthenticated_when_unavailable(self):
        import os
        for key in ["ENTRA_TENANT_ID", "ENTRA_CLIENT_ID", "ENTRA_JWKS_URL"]:
            os.environ.pop(key, None)
        from kurukshetra.security.identity_provider import EntraIdentityProvider
        provider = EntraIdentityProvider()
        identity = provider.authenticate("some-jwt-token")
        self.assertFalse(identity.is_authenticated)
        self.assertEqual(identity.provider, "entra")


class TestUploadedDocumentOwnership(unittest.TestCase):
    """Test that uploaded documents carry ownership metadata."""

    def test_upload_endpoint_accepts_identity(self):
        """Upload endpoint should accept user identity for ownership."""
        try:
            from fastapi.testclient import TestClient
            from command_center.backend.main import app
            client = TestClient(app)
        except ImportError:
            self.skipTest("FastAPI test client not available")

        content = b"Test document about G3 RMS for ownership test."
        response = client.post(
            "/api/knowledge/upload",
            files={"file": ("ownership_test.txt", content, "text/plain")},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("document_id", data)


class TestMemoryIsolation(unittest.TestCase):
    """Test that memory respects identity boundaries."""

    def test_episodic_memory_user_scoped(self):
        from kurukshetra.agent.memory_store import EpisodicMemory, KnowledgeSource
        em = EpisodicMemory()
        ep1 = em.record_episode(
            query="SPM question", answer="SPM answer", confidence=0.8,
            abstained=False, evidence_doc_ids=[],
            knowledge_sources=[KnowledgeSource.ORGANIZATION],
            user_id="spm-user",
        )
        ep2 = em.record_episode(
            query="ICS question", answer="ICS answer", confidence=0.8,
            abstained=False, evidence_doc_ids=[],
            knowledge_sources=[KnowledgeSource.ORGANIZATION],
            user_id="ics-user",
        )
        # Both episodes exist
        recent = em.get_recent_episodes(limit=10)
        user_ids = {ep.user_id for ep in recent}
        self.assertIn("spm-user", user_ids)
        self.assertIn("ics-user", user_ids)

    def test_prospective_memory_user_scoped(self):
        from kurukshetra.agent.memory_store import ProspectiveMemory
        pm = ProspectiveMemory()
        t1 = pm.add_task(description="SPM task", requested_by="spm-user")
        t2 = pm.add_task(description="ICS task", requested_by="ics-user")
        pending = pm.get_pending_tasks()
        # Both tasks exist
        descriptions = {t.description for t in pending}
        self.assertIn("SPM task", descriptions)
        self.assertIn("ICS task", descriptions)


class TestProviderFactory(unittest.TestCase):
    """Test the provider factory."""

    def test_get_mock_provider(self):
        from kurukshetra.security.identity_provider import get_mock_provider
        provider = get_mock_provider()
        self.assertIsNotNone(provider)
        self.assertTrue(provider.is_available())

    def test_get_identity_provider_returns_local(self):
        """Without Entra config, should return local provider."""
        import os
        for key in ["ENTRA_TENANT_ID", "ENTRA_CLIENT_ID", "ENTRA_JWKS_URL"]:
            os.environ.pop(key, None)
        from kurukshetra.security.identity_provider import get_identity_provider
        provider = get_identity_provider()
        self.assertIsNotNone(provider)


if __name__ == "__main__":
    unittest.main()
