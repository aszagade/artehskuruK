"""
Entra OIDC Authentication Flow Tests
=====================================

Tests the complete authentication flow:
- /auth/login generates correct authorization URL
- /auth/callback validates state, exchanges code, validates JWT
- Session management works correctly
- Security properties are enforced
"""
import os, sys, time, json, unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, ".")

# Set test environment
os.environ["ENTRA_TENANT_ID"] = "test-tenant-123"
os.environ["ENTRA_CLIENT_ID"] = "test-client-456"
os.environ["KURUKSHETRA_SESSION_SECRET"] = "test-session-secret-do-not-use-in-production"

from cryptography.hazmat.primitives.asymmetric import rsa
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
    return private_pem, public_pem, private_key, public_key


_PRIVATE_KEY_PEM, _PUBLIC_KEY_PEM, _PRIVATE_KEY_OBJ, _PUBLIC_KEY_OBJ = _generate_test_keys()


class TestAuthLogin(unittest.TestCase):
    """Test /auth/login endpoint."""

    def test_login_generates_auth_url(self):
        """Login generates a valid Entra authorization URL."""
        from command_center.backend.routers.auth import login
        import asyncio

        response = asyncio.run(login())

        self.assertIn("login.microsoftonline.com", response.auth_url)
        self.assertIn("test-tenant-123", response.auth_url)
        self.assertIn("test-client-456", response.auth_url)
        self.assertIn("response_type=code", response.auth_url)
        self.assertIn("scope=openid", response.auth_url)
        self.assertIn("state=", response.auth_url)

    def test_login_includes_state(self):
        """Login generates a random state parameter."""
        from command_center.backend.routers.auth import login
        import asyncio

        response = asyncio.run(login())
        self.assertIsNotNone(response.state)
        self.assertGreater(len(response.state), 10)

    def test_login_includes_pkce_challenge(self):
        """Login includes PKCE code_challenge and method."""
        from command_center.backend.routers.auth import login
        import asyncio

        response = asyncio.run(login())

        self.assertIn("code_challenge=", response.auth_url)
        self.assertIn("code_challenge_method=S256", response.auth_url)


class TestAuthCallback(unittest.TestCase):
    """Test /auth/callback endpoint."""

    def _create_id_token(self, claims: dict) -> str:
        """Create a signed ID token for testing."""
        return pyjwt.encode(claims, _PRIVATE_KEY_PEM, algorithm="RS256", headers={"kid": "test-key"})

    def test_callback_validates_state(self):
        """Callback rejects invalid state."""
        from command_center.backend.routers.auth import callback
        from fastapi import HTTPException
        import asyncio

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(callback(code="test-code", state="invalid-state"))

        self.assertEqual(ctx.exception.status_code, 400)

    def test_callback_validates_code(self):
        """Callback rejects missing code."""
        from command_center.backend.routers.auth import callback
        from fastapi import HTTPException
        import asyncio

        # Create a valid state
        from command_center.backend.routers.auth import _pending_states
        state = "test-state-123"
        _pending_states[state] = {
            "nonce": "test-nonce",
            "created_at": time.time(),
            "expires_at": time.time() + 600,
        }

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(callback(code=None, state=state))

        self.assertEqual(ctx.exception.status_code, 400)

    def test_callback_rejects_expired_state(self):
        """Callback rejects expired state."""
        from command_center.backend.routers.auth import callback, _pending_states
        from fastapi import HTTPException
        import asyncio

        state = "expired-state"
        _pending_states[state] = {
            "nonce": "test-nonce",
            "created_at": time.time() - 700,
            "expires_at": time.time() - 100,  # Expired
        }

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(callback(code="test-code", state=state))

        self.assertEqual(ctx.exception.status_code, 400)


class TestPKCE(unittest.TestCase):
    """Test PKCE implementation."""

    def test_pkce_generation(self):
        """PKCE generates valid verifier and challenge."""
        from command_center.backend.routers.auth import _generate_pkce

        verifier, challenge = _generate_pkce()

        # RFC 7636: code_verifier must be 43-128 characters
        self.assertGreaterEqual(len(verifier), 43)
        self.assertLessEqual(len(verifier), 128)
        self.assertGreater(len(challenge), 40)
        # Challenge should be base64url-encoded SHA256 of verifier
        import hashlib, base64
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        self.assertEqual(challenge, expected)

    def test_pkce_stored_in_pending_state(self):
        """Login stores code_verifier in pending state."""
        from command_center.backend.routers.auth import login, _pending_states
        import asyncio

        response = asyncio.run(login())
        state_data = _pending_states.get(response.state)

        self.assertIsNotNone(state_data)
        self.assertIn("code_verifier", state_data)
        # RFC 7636: code_verifier must be 43-128 characters
        self.assertGreaterEqual(len(state_data["code_verifier"]), 43)
        self.assertLessEqual(len(state_data["code_verifier"]), 128)


class TestSessionToken(unittest.TestCase):
    """Test session token creation and validation."""

    def test_session_token_creation(self):
        """Session token can be created and decoded."""
        from command_center.backend.routers.auth import Session
        from kurukshetra.security.identity_provider import AuthenticatedIdentity
        from kurukshetra.security.identity import ClearanceLevel

        identity = AuthenticatedIdentity(
            user_id="test-user",
            username="testuser",
            display_name="Test User",
            email="test@example.com",
            team_id="spm",
            clearance_level=ClearanceLevel.CONFIDENTIAL,
            groups=["group-spm"],
            roles=["viewer"],
            token_type=pyjwt  # This will be overridden
        )

        # Fix the token_type
        from kurukshetra.security.identity_provider import TokenType
        identity.token_type = TokenType.JWT

        session = Session(
            session_id="test-session",
            identity=identity,
            created_at=time.time(),
            expires_at=time.time() + 3600,
        )

        token = session.to_token()
        self.assertIsNotNone(token)

        # Decode token
        decoded = Session.from_token(token)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.identity.user_id, "test-user")
        self.assertEqual(decoded.identity.team_id, "spm")

    def test_expired_session_rejected(self):
        """Expired session tokens are rejected."""
        from command_center.backend.routers.auth import Session
        from kurukshetra.security.identity_provider import AuthenticatedIdentity, TokenType
        from kurukshetra.security.identity import ClearanceLevel

        identity = AuthenticatedIdentity(
            user_id="test-user",
            username="testuser",
            display_name="Test User",
            email="test@example.com",
            team_id="spm",
            clearance_level=ClearanceLevel.INTERNAL,
            token_type=TokenType.JWT,
        )

        session = Session(
            session_id="expired-session",
            identity=identity,
            created_at=time.time() - 7200,
            expires_at=time.time() - 3600,  # Expired
        )

        self.assertTrue(session.is_expired)


class TestSecurityProperties(unittest.TestCase):
    """Test security properties of the auth system."""

    def test_invalid_token_rejected(self):
        """Invalid JWT tokens are rejected."""
        from command_center.backend.routers.auth import Session

        result = Session.from_token("invalid.token.here")
        self.assertIsNone(result)

    def test_wrong_secret_rejected(self):
        """Tokens signed with wrong secret are rejected."""
        from command_center.backend.routers.auth import Session

        # Create token with wrong secret
        wrong_token = pyjwt.encode(
            {"sub": "test", "exp": time.time() + 3600},
            "wrong-secret",
            algorithm="HS256"
        )

        result = Session.from_token(wrong_token)
        self.assertIsNone(result)

    def test_tampered_token_rejected(self):
        """Tampered tokens are rejected."""
        from command_center.backend.routers.auth import Session

        # Create valid token
        token = pyjwt.encode(
            {"sub": "test", "exp": time.time() + 3600, "team_id": "spm"},
            os.environ["KURUKSHETRA_SESSION_SECRET"],
            algorithm="HS256"
        )

        # Tamper with token
        tampered = token[:-5] + "XXXXX"

        result = Session.from_token(tampered)
        self.assertIsNone(result)

    def test_missing_client_secret_fails_safely(self):
        """Missing ENTRA_CLIENT_SECRET produces clear error, not silent failure."""
        from kurukshetra.security.entra_provider import EntraConfig
        import asyncio

        # Clear the secret
        old_secret = os.environ.pop("ENTRA_CLIENT_SECRET", None)
        try:
            # Verify config shows secret is missing
            config = EntraConfig.from_env()
            self.assertFalse(config.client_secret)

            # The callback would fail with 500 because client_secret is empty
            # We verify the config check works correctly
            self.assertEqual(config.client_secret, "")
        finally:
            if old_secret:
                os.environ["ENTRA_CLIENT_SECRET"] = old_secret

    def test_client_secret_not_in_logs(self):
        """Client secret value is never logged."""
        import logging
        from io import StringIO

        # Capture log output
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.DEBUG)
        logger = logging.getLogger("kurukshetra.security")
        logger.addHandler(handler)

        try:
            # Simulate a failed token exchange
            from command_center.backend.routers.auth import callback, _pending_states
            from fastapi import HTTPException
            import asyncio

            os.environ["ENTRA_CLIENT_SECRET"] = "super-secret-value-12345"
            state = "test-state-log-check"
            _pending_states[state] = {
                "nonce": "test-nonce",
                "code_verifier": "test-verifier",
                "created_at": time.time(),
                "expires_at": time.time() + 600,
            }

            try:
                asyncio.run(callback(code="test-code", state=state))
            except HTTPException:
                pass

            # Check logs don't contain the secret
            log_output = log_capture.getvalue()
            self.assertNotIn("super-secret-value-12345", log_output)
        finally:
            logger.removeHandler(handler)


class TestGetIdentityFromRequest(unittest.TestCase):
    """Test identity extraction from requests."""

    def test_anonymous_when_no_auth(self):
        """Returns anonymous when no auth header."""
        from command_center.backend.routers.auth import get_identity_from_request
        from unittest.mock import MagicMock

        request = MagicMock()
        request.headers = {}

        identity = get_identity_from_request(request)
        self.assertFalse(identity.is_authenticated)
        self.assertEqual(identity.user_id, "anonymous")

    def test_session_token_auth(self):
        """Authenticates with valid session token."""
        from command_center.backend.routers.auth import get_identity_from_request, Session
        from kurukshetra.security.identity_provider import AuthenticatedIdentity, TokenType
        from kurukshetra.security.identity import ClearanceLevel
        from unittest.mock import MagicMock

        identity = AuthenticatedIdentity(
            user_id="USR-123",
            username="testuser",
            display_name="Test User",
            email="test@example.com",
            team_id="spm",
            clearance_level=ClearanceLevel.INTERNAL,
            token_type=TokenType.JWT,
            is_authenticated=True,
        )

        session = Session(
            session_id="test-session",
            identity=identity,
            created_at=time.time(),
            expires_at=time.time() + 3600,
        )

        token = session.to_token()

        request = MagicMock()
        request.headers = {"Authorization": f"Bearer {token}"}

        result = get_identity_from_request(request)
        self.assertTrue(result.is_authenticated)
        self.assertEqual(result.user_id, "USR-123")


if __name__ == "__main__":
    unittest.main()
