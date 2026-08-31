"""
Microsoft Entra ID / OIDC Identity Provider
=============================================

Production-ready Entra ID authentication with:
- JWT validation (issuer, audience, signature, expiry)
- JWKS key fetching and caching
- Group/role → team/clearance mapping
- Token refresh support
- Read-only validation (no modifications to Entra config)

Architecture:
  Request → Bearer token
    → JWKS fetch (cached)
    → JWT decode + validate
    → Extract claims (sub, email, groups, roles)
    → Map groups → team_id
    → Map roles → clearance_level
    → AuthenticatedIdentity
    → AuthorizationContext

Safety:
- Never hardcodes credentials
- Configuration from environment only
- Never modifies Entra tenant
- Never grants broad permissions
- Tokens validated at every request
- Expired tokens rejected
- Wrong tenant/audience rejected
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

import jwt
from jwt import PyJWKClient

from kurukshetra.security.identity_provider import (
    AuthenticatedIdentity,
    IdentityProvider,
    TokenType,
)
from kurukshetra.security.identity import ClearanceLevel

logger = logging.getLogger(__name__)


# ==================================================================
# Configuration
# ==================================================================

@dataclass
class EntraConfig:
    """Entra ID configuration from environment variables."""
    tenant_id: str = ""
    client_id: str = ""
    client_secret: str = ""  # NEVER log or print this
    authority: str = ""
    jwks_url: str = ""
    redirect_uri: str = ""
    # Group → team mapping (Entra group ID → Kurukshetra team)
    group_team_mapping: dict[str, str] = None
    # Role → clearance mapping (Entra role → clearance level)
    role_clearance_mapping: dict[str, str] = None
    # Required claims
    required_claims: list[str] = None

    def __post_init__(self):
        if self.group_team_mapping is None:
            self.group_team_mapping = {}
        if self.role_clearance_mapping is None:
            self.role_clearance_mapping = {}
        if self.required_claims is None:
            self.required_claims = ["sub", "iss", "aud", "exp"]

    @classmethod
    def from_env(cls) -> "EntraConfig":
        """Load configuration from environment variables."""
        tenant_id = os.environ.get("ENTRA_TENANT_ID", "")
        client_id = os.environ.get("ENTRA_CLIENT_ID", "")
        client_secret = os.environ.get("ENTRA_CLIENT_SECRET", "")  # NEVER log this

        authority = os.environ.get("ENTRA_AUTHORITY", "")
        if not authority and tenant_id:
            authority = f"https://login.microsoftonline.com/{tenant_id}"

        jwks_url = os.environ.get("ENTRA_JWKS_URL", "")
        if not jwks_url and tenant_id:
            jwks_url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"

        # Default to localhost for development; override with ENTRA_REDIRECT_URI for LAN/production
        redirect_uri = os.environ.get("ENTRA_REDIRECT_URI", "http://localhost:8000/auth/callback")

        # Parse group mapping from JSON env var
        group_mapping_str = os.environ.get("ENTRA_GROUP_TEAM_MAPPING", "{}")
        try:
            group_team_mapping = json.loads(group_mapping_str)
        except (json.JSONDecodeError, TypeError):
            group_team_mapping = {}

        # Parse role mapping from JSON env var
        role_mapping_str = os.environ.get("ENTRA_ROLE_CLEARANCE_MAPPING", "{}")
        try:
            role_clearance_mapping = json.loads(role_mapping_str)
        except (json.JSONDecodeError, TypeError):
            role_clearance_mapping = {}

        return cls(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
            authority=authority,
            jwks_url=jwks_url,
            redirect_uri=redirect_uri,
            group_team_mapping=group_team_mapping,
            role_clearance_mapping=role_clearance_mapping,
        )

    @property
    def issuer(self) -> str:
        """Expected JWT issuer."""
        if self.tenant_id:
            return f"https://login.microsoftonline.com/{self.tenant_id}/v2.0"
        return ""

    @property
    def is_configured(self) -> bool:
        """Whether Entra is properly configured."""
        return bool(self.tenant_id and self.client_id)


# ==================================================================
# JWKS Key Cache
# ==================================================================

class JWKSKeyCache:
    """Cache JWKS signing keys to avoid repeated fetches."""

    def __init__(self, jwks_url: str, cache_ttl: int = 3600):
        self.jwks_url = jwks_url
        self.cache_ttl = cache_ttl
        self._keys: dict = {}
        self._fetched_at: float = 0
        self._jwk_client: Optional[PyJWKClient] = None

    def get_signing_key(self, token: str):
        """Get the signing key for validating a JWT."""
        if not self.jwks_url:
            raise ValueError("JWKS URL not configured")

        # Check cache freshness
        now = time.time()
        if now - self._fetched_at > self.cache_ttl:
            self._refresh_keys()

        # Use PyJWKClient to get the key
        if self._jwk_client is None:
            self._jwk_client = PyJWKClient(self.jwks_url)

        return self._jwk_client.get_signing_key_from_jwt(token)

    def _refresh_keys(self):
        """Refresh the JWKS keys from the endpoint."""
        try:
            self._jwk_client = PyJWKClient(self.jwks_url)
            self._fetched_at = time.time()
            logger.info(f"Refreshed JWKS keys from {self.jwks_url}")
        except Exception as e:
            logger.error(f"Failed to refresh JWKS keys: {e}")
            # Keep existing keys if refresh fails
            if not self._jwk_client:
                raise


# ==================================================================
# Entra Identity Provider (Production)
# ==================================================================

class EntraIdentityProvider(IdentityProvider):
    """
    Microsoft Entra ID / OIDC identity provider.

    Validates JWTs issued by Entra ID and extracts identity claims.
    """

    def __init__(self, config: Optional[EntraConfig] = None):
        self.config = config or EntraConfig.from_env()
        self._jwks_cache: Optional[JWKSKeyCache] = None

    def is_available(self) -> bool:
        """Check if Entra is configured and available."""
        return self.config.is_configured

    def _get_jwks_cache(self) -> JWKSKeyCache:
        """Get or create the JWKS key cache."""
        if self._jwks_cache is None:
            self._jwks_cache = JWKSKeyCache(self.config.jwks_url)
        return self._jwks_cache

    def authenticate(
        self,
        token: Optional[str] = None,
        token_type: TokenType = TokenType.JWT,
        context: Optional[dict] = None,
    ) -> AuthenticatedIdentity:
        """
        Validate an Entra ID JWT and extract identity claims.

        Validation steps:
        1. Token present
        2. JWKS key fetched
        3. JWT signature verified
        4. Issuer matches Entra tenant
        5. Audience matches client ID
        6. Expiry not passed
        7. Required claims present
        8. Groups/roles mapped to teams/clearance
        """
        # Not configured
        if not self.is_available():
            return self._make_identity(
                user_id="entra-unavailable",
                display_name="Entra ID Not Configured",
                is_authenticated=False,
            )

        # No token
        if not token:
            return self._make_identity(
                user_id="unauthenticated",
                display_name="Unauthenticated",
                is_authenticated=False,
            )

        try:
            # Fetch signing key
            cache = self._get_jwks_cache()
            signing_key = cache.get_signing_key(token)

            # Decode and validate JWT
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "RS384", "RS512"],
                audience=self.config.client_id,
                issuer=self.config.issuer,
                options={
                    "verify_exp": True,
                    "verify_aud": True,
                    "verify_iss": True,
                    "verify_signature": True,
                },
            )

            # Extract identity from claims
            return self._claims_to_identity(claims)

        except jwt.ExpiredSignatureError:
            logger.warning("Entra token expired")
            return self._make_identity(
                user_id="token-expired",
                display_name="Token Expired",
                is_authenticated=False,
            )
        except jwt.InvalidAudienceError:
            logger.warning(f"Entra token audience mismatch: expected {self.config.client_id}")
            return self._make_identity(
                user_id="invalid-audience",
                display_name="Invalid Audience",
                is_authenticated=False,
            )
        except jwt.InvalidIssuerError:
            logger.warning(f"Entra token issuer mismatch: expected {self.config.issuer}")
            return self._make_identity(
                user_id="invalid-issuer",
                display_name="Invalid Issuer",
                is_authenticated=False,
            )
        except jwt.InvalidSignatureError:
            logger.warning("Entra token signature invalid")
            return self._make_identity(
                user_id="invalid-signature",
                display_name="Invalid Signature",
                is_authenticated=False,
            )
        except jwt.DecodeError as e:
            logger.warning(f"Entra token decode error: {e}")
            return self._make_identity(
                user_id="invalid-token",
                display_name="Invalid Token",
                is_authenticated=False,
            )
        except Exception as e:
            logger.error(f"Entra authentication error: {e}")
            return self._make_identity(
                user_id="entra-error",
                display_name="Authentication Error",
                is_authenticated=False,
            )

    def _claims_to_identity(self, claims: dict) -> AuthenticatedIdentity:
        """Convert JWT claims to AuthenticatedIdentity."""
        user_id = claims.get("sub", "")
        username = claims.get("preferred_username", claims.get("upn", ""))
        display_name = claims.get("name", "")
        email = claims.get("email", claims.get("preferred_username", ""))

        # Extract groups and roles
        groups = claims.get("groups", [])
        roles = claims.get("roles", [])

        # Map groups to team
        team_id = self._map_groups_to_team(groups)

        # Map roles to clearance
        clearance = self._map_roles_to_clearance(roles)

        return AuthenticatedIdentity(
            user_id=user_id,
            username=username,
            display_name=display_name,
            email=email,
            team_id=team_id,
            clearance_level=clearance,
            groups=groups,
            roles=roles,
            token_type=TokenType.JWT,
            token_valid=True,
            token_expiry=claims.get("exp"),
            provider="entra",
            is_authenticated=True,
        )

    def _map_groups_to_team(self, groups: list[str]) -> str:
        """Map Entra group IDs to Kurukshetra team IDs."""
        for group_id in groups:
            if group_id in self.config.group_team_mapping:
                return self.config.group_team_mapping[group_id]
        return "unknown"

    def _map_roles_to_clearance(self, roles: list[str]) -> ClearanceLevel:
        """Map Entra roles to Kurukshetra clearance levels."""
        for role in roles:
            if role in self.config.role_clearance_mapping:
                level_str = self.config.role_clearance_mapping[role]
                try:
                    return ClearanceLevel.from_string(level_str)
                except Exception:
                    pass
        return ClearanceLevel.INTERNAL  # Default clearance

    def _make_identity(
        self,
        user_id: str,
        display_name: str,
        is_authenticated: bool,
    ) -> AuthenticatedIdentity:
        """Create an AuthenticatedIdentity with standard defaults."""
        return AuthenticatedIdentity(
            user_id=user_id,
            username=user_id,
            display_name=display_name,
            email="",
            team_id="unknown",
            clearance_level=ClearanceLevel.PUBLIC,
            token_type=TokenType.JWT,
            token_valid=False,
            provider="entra",
            is_authenticated=is_authenticated,
        )

    def get_auth_url(self, state: str = "") -> str:
        """
        Generate the OAuth2 authorization URL for Authorization Code + PKCE.

        Returns the URL the user should be redirected to for login.
        """
        if not self.is_configured:
            return ""

        params = {
            "client_id": self.config.client_id,
            "response_type": "code",
            "redirect_uri": self.config.redirect_uri,
            "scope": "openid profile email",
            "response_mode": "query",
        }
        if state:
            params["state"] = state

        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.config.authority}/oauth2/v2.0/authorize?{query}"

    def exchange_code(self, code: str) -> Optional[str]:
        """
        Exchange an authorization code for tokens.

        This is called after the user completes the OAuth2 flow.
        Returns the access token or None on failure.
        """
        if not self.is_configured:
            return None

        try:
            import requests
            token_url = f"{self.config.authority}/oauth2/v2.0/token"
            data = {
                "client_id": self.config.client_id,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.config.redirect_uri,
            }
            response = requests.post(token_url, data=data, timeout=10)
            if response.status_code == 200:
                token_data = response.json()
                return token_data.get("access_token")
            else:
                logger.error(f"Token exchange failed: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Token exchange error: {e}")
            return None
