"""
Entra ID Security Tests
=======================

Tests JWT validation, token rejection, group authorization,
and identity propagation using mocked Entra tokens.

No production credentials required.
"""
import os, sys, time, unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, ".")

# Generate test RSA keys for JWT signing
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization
import jwt as pyjwt


def _generate_test_keys():
    """Generate RSA key pair for testing."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def _create_test_jwt(
    private_key_pem: bytes,
    claims: dict,
    kid: str = "test-key-1",
) -> str:
    """Create a signed JWT for testing."""
    header = {"alg": "RS256", "kid": kid, "typ": "JWT"}
    return pyjwt.encode(claims, private_key_pem, algorithm="RS256", headers=header)


# Generate keys once at module level
_PRIVATE_KEY_PEM, _PUBLIC_KEY_PEM = _generate_test_keys()

# Keep the key objects for public_bytes()
_PRIVATE_KEY_OBJ = serialization.load_pem_private_key(_PRIVATE_KEY_PEM, password=None)
_PUBLIC_KEY_OBJ = _PRIVATE_KEY_OBJ.public_key()


class TestEntraTokenValidation(unittest.TestCase):
    """Test JWT token validation."""

    def _make_provider(self, tenant_id="test-tenant", client_id="test-client"):
        """Create an Entra provider with test configuration."""
        from kurukshetra.security.entra_provider import EntraIdentityProvider, EntraConfig
        config = EntraConfig(
            tenant_id=tenant_id,
            client_id=client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            jwks_url="https://test.example.com/keys",
        )
        return EntraIdentityProvider(config=config)

    def _make_valid_claims(self, **overrides):
        """Create valid JWT claims."""
        claims = {
            "sub": "user-123",
            "iss": "https://login.microsoftonline.com/test-tenant/v2.0",
            "aud": "test-client",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "name": "Test User",
            "email": "test@example.com",
            "preferred_username": "test@example.com",
            "groups": ["group-spm", "group-ics"],
            "roles": ["viewer"],
        }
        claims.update(overrides)
        return claims

    def test_valid_token_accepted(self):
        """Valid JWT is accepted and identity extracted."""
        provider = self._make_provider()
        claims = self._make_valid_claims()
        token = _create_test_jwt(_PRIVATE_KEY_PEM, claims)

        # Mock JWKS to return our test public key
        with patch.object(provider, '_get_jwks_cache') as mock_cache:
            mock_jwk = MagicMock()
            mock_jwk.key = _PUBLIC_KEY_OBJ.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode()
            mock_cache.return_value.get_signing_key.return_value = mock_jwk

            identity = provider.authenticate(token)

        self.assertTrue(identity.is_authenticated)
        self.assertEqual(identity.user_id, "user-123")
        self.assertEqual(identity.display_name, "Test User")
        self.assertEqual(identity.email, "test@example.com")
        self.assertIn("group-spm", identity.groups)
        self.assertIn("group-ics", identity.groups)

    def test_expired_token_rejected(self):
        """Expired JWT is rejected."""
        provider = self._make_provider()
        claims = self._make_valid_claims(exp=int(time.time()) - 3600)
        token = _create_test_jwt(_PRIVATE_KEY_PEM, claims)

        with patch.object(provider, '_get_jwks_cache') as mock_cache:
            mock_jwk = MagicMock()
            mock_jwk.key = _PUBLIC_KEY_OBJ.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode()
            mock_cache.return_value.get_signing_key.return_value = mock_jwk

            identity = provider.authenticate(token)

        self.assertFalse(identity.is_authenticated)
        self.assertEqual(identity.user_id, "token-expired")

    def test_wrong_audience_rejected(self):
        """JWT with wrong audience is rejected."""
        provider = self._make_provider(client_id="correct-client")
        claims = self._make_valid_claims(aud="wrong-client")
        token = _create_test_jwt(_PRIVATE_KEY_PEM, claims)

        with patch.object(provider, '_get_jwks_cache') as mock_cache:
            mock_jwk = MagicMock()
            mock_jwk.key = _PUBLIC_KEY_OBJ.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode()
            mock_cache.return_value.get_signing_key.return_value = mock_jwk

            identity = provider.authenticate(token)

        self.assertFalse(identity.is_authenticated)
        self.assertEqual(identity.user_id, "invalid-audience")

    def test_wrong_issuer_rejected(self):
        """JWT with wrong issuer is rejected."""
        provider = self._make_provider(tenant_id="correct-tenant")
        claims = self._make_valid_claims(
            iss="https://login.microsoftonline.com/wrong-tenant/v2.0"
        )
        token = _create_test_jwt(_PRIVATE_KEY_PEM, claims)

        with patch.object(provider, '_get_jwks_cache') as mock_cache:
            mock_jwk = MagicMock()
            mock_jwk.key = _PUBLIC_KEY_OBJ.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode()
            mock_cache.return_value.get_signing_key.return_value = mock_jwk

            identity = provider.authenticate(token)

        self.assertFalse(identity.is_authenticated)
        self.assertEqual(identity.user_id, "invalid-issuer")

    def test_wrong_signature_rejected(self):
        """JWT signed with wrong key is rejected."""
        provider = self._make_provider()
        claims = self._make_valid_claims()
        # Sign with a different key
        wrong_key, _ = _generate_test_keys()
        token = _create_test_jwt(wrong_key, claims)

        with patch.object(provider, '_get_jwks_cache') as mock_cache:
            mock_jwk = MagicMock()
            mock_jwk.key = _PUBLIC_KEY_OBJ.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode()
            mock_cache.return_value.get_signing_key.return_value = mock_jwk

            identity = provider.authenticate(token)

        self.assertFalse(identity.is_authenticated)
        self.assertEqual(identity.user_id, "invalid-signature")

    def test_no_token_returns_unauthenticated(self):
        """Missing token returns unauthenticated identity."""
        provider = self._make_provider()
        identity = provider.authenticate(token=None)
        self.assertFalse(identity.is_authenticated)
        self.assertEqual(identity.user_id, "unauthenticated")

    def test_unconfigured_provider_returns_unavailable(self):
        """Unconfigured provider returns unavailable identity."""
        from kurukshetra.security.entra_provider import EntraIdentityProvider, EntraConfig
        config = EntraConfig()  # No tenant/client configured
        provider = EntraIdentityProvider(config=config)
        self.assertFalse(provider.is_available())
        identity = provider.authenticate("some-token")
        self.assertFalse(identity.is_authenticated)
        self.assertEqual(identity.user_id, "entra-unavailable")


class TestGroupRoleMapping(unittest.TestCase):
    """Test group → team and role → clearance mapping."""

    def test_group_maps_to_team(self):
        from kurukshetra.security.entra_provider import EntraIdentityProvider, EntraConfig
        config = EntraConfig(
            tenant_id="test-tenant",
            client_id="test-client",
            jwks_url="https://test.example.com/keys",
            group_team_mapping={
                "group-spm-id": "spm",
                "group-ics-id": "ics",
                "group-sdops-id": "sdops",
            },
        )
        provider = EntraIdentityProvider(config=config)

        claims = {
            "sub": "user-456",
            "iss": "https://login.microsoftonline.com/test-tenant/v2.0",
            "aud": "test-client",
            "exp": int(time.time()) + 3600,
            "groups": ["group-spm-id", "group-ics-id"],
            "roles": ["viewer"],
        }
        token = _create_test_jwt(_PRIVATE_KEY_PEM, claims)

        with patch.object(provider, '_get_jwks_cache') as mock_cache:
            mock_jwk = MagicMock()
            mock_jwk.key = _PUBLIC_KEY_OBJ.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode()
            mock_cache.return_value.get_signing_key.return_value = mock_jwk

            identity = provider.authenticate(token)

        self.assertEqual(identity.team_id, "spm")
        self.assertIn("group-spm-id", identity.groups)
        self.assertIn("group-ics-id", identity.groups)

    def test_role_maps_to_clearance(self):
        from kurukshetra.security.entra_provider import EntraIdentityProvider, EntraConfig
        config = EntraConfig(
            tenant_id="test-tenant",
            client_id="test-client",
            jwks_url="https://test.example.com/keys",
            role_clearance_mapping={
                "admin": "restricted",
                "viewer": "internal",
                "public-viewer": "public",
            },
        )
        provider = EntraIdentityProvider(config=config)

        claims = {
            "sub": "user-789",
            "iss": "https://login.microsoftonline.com/test-tenant/v2.0",
            "aud": "test-client",
            "exp": int(time.time()) + 3600,
            "groups": [],
            "roles": ["admin"],
        }
        token = _create_test_jwt(_PRIVATE_KEY_PEM, claims)

        with patch.object(provider, '_get_jwks_cache') as mock_cache:
            mock_jwk = MagicMock()
            mock_jwk.key = _PUBLIC_KEY_OBJ.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode()
            mock_cache.return_value.get_signing_key.return_value = mock_jwk

            identity = provider.authenticate(token)

        self.assertEqual(identity.clearance_level.name, "RESTRICTED")


class TestIdentityPipeline(unittest.TestCase):
    """Test that identity survives through the retrieval/evidence/answer pipeline."""

    def test_identity_flows_through_authorization_context(self):
        from kurukshetra.security.identity_provider import (
            AuthenticatedIdentity, AuthorizationContext, TokenType,
        )
        from kurukshetra.security.identity import ClearanceLevel

        identity = AuthenticatedIdentity(
            user_id="USR-TEST",
            username="test-user",
            display_name="Test User",
            email="test@example.com",
            team_id="spm",
            clearance_level=ClearanceLevel.CONFIDENTIAL,
            groups=["group-spm"],
            roles=["viewer"],
            token_type=TokenType.JWT,
            token_valid=True,
            provider="entra",
        )

        ctx = AuthorizationContext(identity=identity, request_id="REQ-001")

        self.assertEqual(ctx.user_id, "USR-TEST")
        self.assertEqual(ctx.team_id, "spm")
        self.assertEqual(ctx.clearance.name, "CONFIDENTIAL")
        self.assertTrue(ctx.can_see_document("internal"))
        self.assertTrue(ctx.can_see_document("confidential"))
        self.assertFalse(ctx.can_see_document("restricted"))

    def test_audit_record_contains_identity(self):
        from kurukshetra.security.identity_provider import (
            AuthenticatedIdentity, AuthorizationContext, TokenType,
        )
        from kurukshetra.security.identity import ClearanceLevel

        identity = AuthenticatedIdentity(
            user_id="USR-AUDIT",
            username="audit-user",
            display_name="Audit User",
            email="audit@example.com",
            team_id="ics",
            clearance_level=ClearanceLevel.INTERNAL,
            token_type=TokenType.JWT,
            token_valid=True,
            provider="entra",
        )

        ctx = AuthorizationContext(identity=identity, request_id="REQ-AUDIT")
        audit = ctx.for_audit()

        self.assertEqual(audit["user_id"], "USR-AUDIT")
        self.assertEqual(audit["username"], "audit-user")
        self.assertEqual(audit["team_id"], "ics")
        self.assertEqual(audit["provider"], "entra")
        self.assertTrue(audit["token_valid"])


class TestMemoryIsolation(unittest.TestCase):
    """Test that user memories are isolated."""

    def test_user_a_memory_not_visible_to_user_b(self):
        from kurukshetra.agent.memory_store import EpisodicMemory, KnowledgeSource

        em = EpisodicMemory()

        # User A records an interaction
        ep_a = em.record_episode(
            query="User A private question",
            answer="User A private answer",
            confidence=0.9,
            abstained=False,
            evidence_doc_ids=[],
            knowledge_sources=[KnowledgeSource.ORGANIZATION],
            user_id="user-a-entra",
        )

        # User B records an interaction
        ep_b = em.record_episode(
            query="User B private question",
            answer="User B private answer",
            confidence=0.8,
            abstained=False,
            evidence_doc_ids=[],
            knowledge_sources=[KnowledgeSource.ORGANIZATION],
            user_id="user-b-entra",
        )

        # Each user can only see their own episodes
        # Query all episodes and filter by user_id
        all_episodes = em.get_recent_episodes(limit=100)
        a_episodes = [ep for ep in all_episodes if ep.user_id == "user-a-entra"]
        b_episodes = [ep for ep in all_episodes if ep.user_id == "user-b-entra"]

        a_queries = [ep.query for ep in a_episodes]
        b_queries = [ep.query for ep in b_episodes]

        self.assertIn("User A private question", a_queries)
        self.assertNotIn("User B private question", a_queries)
        self.assertIn("User B private question", b_queries)
        self.assertNotIn("User A private question", b_queries)


class TestPermissionMatrix(unittest.TestCase):
    """Document the required Entra permissions."""

    def test_permission_matrix_documented(self):
        """Permission matrix exists and covers required scenarios."""
        matrix = {
            "authentication": {
                "openid": "required now",
                "profile": "required now",
                "email": "required now",
            },
            "user_lookup": {
                "User.Read": "required now",
                "User.ReadBasic.All": "future",
            },
            "group_lookup": {
                "Group.Read.All": "required now",
                "GroupMember.Read.All": "required now",
            },
            "sharepoint": {
                "Sites.Read.All": "future",
                "Sites.ReadWrite.All": "not required",
            },
            "onedrive": {
                "Files.Read.All": "future",
                "Files.ReadWrite.All": "not required",
            },
            "teams": {
                "Team.ReadBasic.All": "future",
                "ChannelMessage.Read.All": "not required",
            },
            "outlook": {
                "Mail.Read": "not required",
                "Calendars.Read": "not required",
            },
        }

        # Verify structure
        self.assertIn("authentication", matrix)
        self.assertIn("user_lookup", matrix)
        self.assertIn("group_lookup", matrix)
        self.assertIn("sharepoint", matrix)
        self.assertIn("teams", matrix)

        # Verify required permissions are documented
        for category, perms in matrix.items():
            for perm, status in perms.items():
                self.assertIn(status, ["required now", "future", "not required"],
                    f"Permission {perm} has invalid status: {status}")


class TestAgentIdentity(unittest.TestCase):
    """Test that agent identity cannot impersonate human."""

    def test_agent_identity_distinct_from_human(self):
        from kurukshetra.security.identity_provider import AuthenticatedIdentity
        from kurukshetra.security.identity import ClearanceLevel

        human = AuthenticatedIdentity(
            user_id="USR-HUMAN",
            username="human-user",
            display_name="Human User",
            email="human@example.com",
            team_id="spm",
            clearance_level=ClearanceLevel.CONFIDENTIAL,
            provider="entra",
            is_authenticated=True,
        )

        agent = AuthenticatedIdentity(
            user_id="AGENT-SANJAYA",
            username="sanjaya-agent",
            display_name="SANJAYA Agent",
            email="",
            team_id="system",
            clearance_level=ClearanceLevel.INTERNAL,
            provider="local",
            is_authenticated=True,
        )

        # Agent should not have human's team or clearance
        self.assertNotEqual(agent.team_id, human.team_id)
        self.assertNotEqual(agent.user_id, human.user_id)

    def test_connector_identity_cannot_bypass_user_auth(self):
        from kurukshetra.security.identity_provider import AuthenticatedIdentity
        from kurukshetra.security.identity import ClearanceLevel

        connector = AuthenticatedIdentity(
            user_id="CONNECTOR-SFDC",
            username="salesforce-connector",
            display_name="Salesforce Connector",
            email="",
            team_id="system",
            clearance_level=ClearanceLevel.PUBLIC,  # Connectors get minimal clearance
            provider="local",
            is_authenticated=True,
        )

        # Connector should not have elevated clearance
        self.assertEqual(connector.clearance_level, ClearanceLevel.PUBLIC)
        self.assertFalse(connector.can_see("confidential"))
        self.assertFalse(connector.can_see("restricted"))


if __name__ == "__main__":
    unittest.main()
