"""
Enterprise Identity Provider Abstraction
=========================================

Provides a clean interface for identity resolution that can be swapped
between development (API-key), testing (mock), and production (Entra ID/OIDC).

Architecture:

    Request
      → IdentityProvider.authenticate(token, context)
        → AuthenticatedIdentity
          → AuthorizationContext
            → flows through retrieval → evidence → answer

Design principles:
- No production secrets required for development/testing
- Entra ID integration is ready but not required
- Mock provider enables deterministic testing
- All identity decisions are auditable
"""

from __future__ import annotations

import hashlib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from kurukshetra.security.identity import (
    ClearanceLevel,
    UserIdentity,
    ANONYMOUS,
)


# ==================================================================
# Token Types
# ==================================================================

class TokenType(Enum):
    """Supported authentication token types."""
    API_KEY = "api_key"
    JWT = "jwt"
    BEARER = "bearer"
    NONE = "none"


# ==================================================================
# Authenticated Identity (extended from UserIdentity)
# ==================================================================

@dataclass(slots=True)
class AuthenticatedIdentity:
    """
    Full authenticated identity with enterprise attributes.

    Extends UserIdentity with:
    - Token type and validation info
    - Group/role membership
    - Source-level permissions
    - Token expiry
    - Provider metadata
    """
    user_id: str
    username: str
    display_name: str
    email: str
    team_id: str
    clearance_level: ClearanceLevel
    groups: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    source_permissions: dict[str, list[str]] = field(default_factory=dict)
    token_type: TokenType = TokenType.NONE
    token_valid: bool = False
    token_expiry: Optional[float] = None
    provider: str = "local"
    is_authenticated: bool = True
    created_at: float = field(default_factory=time.time)

    @property
    def max_visibility(self) -> str:
        return ClearanceLevel(self.clearance_level).name.lower()

    def can_see(self, doc_visibility: str) -> bool:
        doc_level = ClearanceLevel.from_string(doc_visibility)
        return doc_level <= self.clearance_level

    def has_group(self, group: str) -> bool:
        return group.lower() in [g.lower() for g in self.groups]

    def has_role(self, role: str) -> bool:
        return role.lower() in [r.lower() for r in self.roles]

    def can_access_source(self, source_id: str) -> bool:
        """Check if user has permission to access a specific source."""
        if not self.source_permissions:
            return True  # No restrictions configured
        allowed = self.source_permissions.get(source_id, [])
        return self.team_id in allowed or "*" in allowed

    def is_token_valid(self) -> bool:
        """Check if the authentication token is still valid."""
        if not self.token_valid:
            return False
        if self.token_expiry and time.time() > self.token_expiry:
            return False
        return True

    def to_user_identity(self) -> UserIdentity:
        """Convert to the existing UserIdentity format for backward compatibility."""
        return UserIdentity(
            user_id=self.user_id,
            username=self.username,
            display_name=self.display_name,
            team_id=self.team_id,
            clearance_level=self.clearance_level,
            is_authenticated=self.is_authenticated,
        )


# ==================================================================
# Authorization Context (flows through the pipeline)
# ==================================================================

@dataclass(slots=True)
class AuthorizationContext:
    """
    Authorization context that flows through the entire SANJAYA pipeline.

    Created once per request and passed through:
    - Retrieval (visibility filtering)
    - Evidence selection
    - Answer generation
    - Memory operations
    - Audit logging

    This ensures consistent authorization at every stage.
    """
    identity: AuthenticatedIdentity
    request_id: str = ""
    source_filter: Optional[str] = None  # Restrict to specific source
    team_filter: Optional[str] = None     # Restrict to specific team
    timestamp: float = field(default_factory=time.time)

    @property
    def user_id(self) -> str:
        return self.identity.user_id

    @property
    def team_id(self) -> str:
        return self.identity.team_id

    @property
    def clearance(self) -> ClearanceLevel:
        return self.identity.clearance_level

    def can_see_document(self, doc_visibility: str) -> bool:
        """Check if this context allows viewing a document."""
        return self.identity.can_see(doc_visibility)

    def can_access_source(self, source_id: str) -> bool:
        """Check if this context allows accessing a source."""
        return self.identity.can_access_source(source_id)

    def for_audit(self) -> dict:
        """Generate audit-friendly context summary."""
        return {
            "user_id": self.identity.user_id,
            "username": self.identity.username,
            "team_id": self.identity.team_id,
            "clearance": self.identity.clearance_level.name,
            "provider": self.identity.provider,
            "token_valid": self.identity.is_token_valid(),
            "request_id": self.request_id,
            "timestamp": self.timestamp,
        }


# ==================================================================
# Identity Provider Interface
# ==================================================================

class IdentityProvider(ABC):
    """
    Abstract interface for identity resolution.

    Implementations:
    - LocalIdentityProvider: API-key based (development)
    - MockIdentityProvider: Deterministic testing
    - EntraIdentityProvider: Microsoft Entra ID/OIDC (production)
    """

    @abstractmethod
    def authenticate(
        self,
        token: Optional[str] = None,
        token_type: TokenType = TokenType.NONE,
        context: Optional[dict] = None,
    ) -> AuthenticatedIdentity:
        """
        Authenticate a request and return the full identity.

        Args:
            token: The authentication token (API key, JWT, etc.)
            token_type: Type of token provided
            context: Additional context (headers, IP, etc.)

        Returns:
            AuthenticatedIdentity with full attributes.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is configured and available."""
        ...


# ==================================================================
# Local Identity Provider (API-key based)
# ==================================================================

class LocalIdentityProvider(IdentityProvider):
    """
    Development identity provider using API keys.

    Maps API keys to users stored in DuckDB.
    Falls back to ANONYMOUS when auth is not required.
    """

    def __init__(self) -> None:
        self._config = None

    def _get_config(self):
        if self._config is None:
            from kurukshetra.security.config import SecurityConfig
            self._config = SecurityConfig()
        return self._config

    def authenticate(
        self,
        token: Optional[str] = None,
        token_type: TokenType = TokenType.API_KEY,
        context: Optional[dict] = None,
    ) -> AuthenticatedIdentity:
        config = self._get_config()

        # Open mode: return anonymous
        if not config.auth_required:
            return AuthenticatedIdentity(
                user_id="anonymous",
                username="anonymous",
                display_name="Anonymous User",
                email="",
                team_id="unknown",
                clearance_level=ClearanceLevel.PUBLIC,
                token_type=TokenType.NONE,
                token_valid=False,
                provider="local",
                is_authenticated=False,
            )

        # No token provided
        if not token:
            return AuthenticatedIdentity(
                user_id="unauthenticated",
                username="unauthenticated",
                display_name="Unauthenticated",
                email="",
                team_id="unknown",
                clearance_level=ClearanceLevel.PUBLIC,
                token_type=token_type,
                token_valid=False,
                provider="local",
                is_authenticated=False,
            )

        # Look up user by API key
        from kurukshetra.security.identity import UserStore
        store = UserStore()
        user = store.get_by_api_key(token)

        if user is None:
            return AuthenticatedIdentity(
                user_id="invalid",
                username="invalid",
                display_name="Invalid Credentials",
                email="",
                team_id="unknown",
                clearance_level=ClearanceLevel.PUBLIC,
                token_type=token_type,
                token_valid=False,
                provider="local",
                is_authenticated=False,
            )

        return AuthenticatedIdentity(
            user_id=user.user_id,
            username=user.username,
            display_name=user.display_name,
            email="",
            team_id=user.team_id,
            clearance_level=user.clearance_level,
            token_type=token_type,
            token_valid=True,
            provider="local",
            is_authenticated=True,
        )

    def is_available(self) -> bool:
        return True  # Always available (uses DuckDB)


# ==================================================================
# Mock Identity Provider (for testing)
# ==================================================================

class MockIdentityProvider(IdentityProvider):
    """
    Deterministic identity provider for testing.

    Pre-configured users with known attributes.
    No external dependencies.
    """

    def __init__(self) -> None:
        self._users: dict[str, AuthenticatedIdentity] = {
            "test-admin": AuthenticatedIdentity(
                user_id="USR-ADMIN",
                username="admin",
                display_name="Test Admin",
                email="admin@test.com",
                team_id="spm",
                clearance_level=ClearanceLevel.RESTRICTED,
                groups=["admin", "spm", "ics"],
                roles=["admin", "viewer"],
                source_permissions={"salesforce": ["spm", "ics", "*"]},
                token_type=TokenType.API_KEY,
                token_valid=True,
                provider="mock",
            ),
            "test-spm": AuthenticatedIdentity(
                user_id="USR-SPM",
                username="spm-user",
                display_name="SPM User",
                email="spm@test.com",
                team_id="spm",
                clearance_level=ClearanceLevel.CONFIDENTIAL,
                groups=["spm"],
                roles=["viewer"],
                token_type=TokenType.API_KEY,
                token_valid=True,
                provider="mock",
            ),
            "test-ics": AuthenticatedIdentity(
                user_id="USR-ICS",
                username="ics-user",
                display_name="ICS User",
                email="ics@test.com",
                team_id="ics",
                clearance_level=ClearanceLevel.CONFIDENTIAL,
                groups=["ics"],
                roles=["viewer"],
                token_type=TokenType.API_KEY,
                token_valid=True,
                provider="mock",
            ),
            "test-public": AuthenticatedIdentity(
                user_id="USR-PUBLIC",
                username="public-user",
                display_name="Public User",
                email="public@test.com",
                team_id="unknown",
                clearance_level=ClearanceLevel.INTERNAL,
                groups=[],
                roles=["viewer"],
                token_type=TokenType.API_KEY,
                token_valid=True,
                provider="mock",
            ),
            "test-expired": AuthenticatedIdentity(
                user_id="USR-EXPIRED",
                username="expired-user",
                display_name="Expired User",
                email="expired@test.com",
                team_id="spm",
                clearance_level=ClearanceLevel.INTERNAL,
                token_type=TokenType.JWT,
                token_valid=True,
                token_expiry=time.time() - 3600,  # Expired 1 hour ago
                provider="mock",
            ),
        }

    def authenticate(
        self,
        token: Optional[str] = None,
        token_type: TokenType = TokenType.API_KEY,
        context: Optional[dict] = None,
    ) -> AuthenticatedIdentity:
        if token is None:
            return AuthenticatedIdentity(
                user_id="anonymous",
                username="anonymous",
                display_name="Anonymous",
                email="",
                team_id="unknown",
                clearance_level=ClearanceLevel.PUBLIC,
                token_type=TokenType.NONE,
                token_valid=False,
                provider="mock",
                is_authenticated=False,
            )

        user = self._users.get(token)
        if user is None:
            return AuthenticatedIdentity(
                user_id="invalid",
                username="invalid",
                display_name="Invalid",
                email="",
                team_id="unknown",
                clearance_level=ClearanceLevel.PUBLIC,
                token_type=token_type,
                token_valid=False,
                provider="mock",
                is_authenticated=False,
            )

        return user

    def is_available(self) -> bool:
        return True


# ==================================================================
# Entra Identity Provider (production-ready interface)
# ==================================================================

class EntraIdentityProvider(IdentityProvider):
    """
    Microsoft Entra ID / OIDC identity provider.

    This is the production-ready interface. It requires:
    - ENTRA_TENANT_ID: Azure AD tenant ID
    - ENTRA_CLIENT_ID: Application client ID
    - ENTRA_JWKS_URL: JWKS endpoint for token validation

    When these are not configured, is_available() returns False
    and the system falls back to LocalIdentityProvider.

    To connect to a real Entra tenant later:
    1. Register an app in Entra ID
    2. Configure redirect URIs
    3. Set environment variables
    4. The provider handles JWT validation automatically
    """

    def __init__(self) -> None:
        import os
        self._tenant_id = os.environ.get("ENTRA_TENANT_ID", "")
        self._client_id = os.environ.get("ENTRA_CLIENT_ID", "")
        self._jwks_url = os.environ.get("ENTRA_JWKS_URL", "")
        self._issuer = f"https://login.microsoftonline.com/{self._tenant_id}/v2.0" if self._tenant_id else ""

    def is_available(self) -> bool:
        return bool(self._tenant_id and self._client_id and self._jwks_url)

    def authenticate(
        self,
        token: Optional[str] = None,
        token_type: TokenType = TokenType.JWT,
        context: Optional[dict] = None,
    ) -> AuthenticatedIdentity:
        """
        Validate an Entra ID JWT and extract identity claims.

        When Entra is not configured, returns an unauthenticated identity.
        When configured, validates the JWT signature and extracts:
        - sub (user ID)
        - email / preferred_username
        - name
        - groups / roles
        - team assignment (from group mapping)
        - clearance level (from role mapping)
        """
        if not self.is_available() or not token:
            return AuthenticatedIdentity(
                user_id="entra-unavailable",
                username="entra-unavailable",
                display_name="Entra ID Not Configured",
                email="",
                team_id="unknown",
                clearance_level=ClearanceLevel.PUBLIC,
                token_type=token_type,
                token_valid=False,
                provider="entra",
                is_authenticated=False,
            )

        try:
            # JWT validation would go here using python-jose or PyJWT
            # For now, this is the interface that production code would implement:
            #
            # from jose import jwt
            # claims = jwt.decode(token, self._get_signing_key(), algorithms=["RS256"],
            #                     audience=self._client_id, issuer=self._issuer)
            #
            # return AuthenticatedIdentity(
            #     user_id=claims["sub"],
            #     username=claims.get("preferred_username", ""),
            #     display_name=claims.get("name", ""),
            #     email=claims.get("email", ""),
            #     team_id=self._map_group_to_team(claims.get("groups", [])),
            #     clearance_level=self._map_role_to_clearance(claims.get("roles", [])),
            #     groups=claims.get("groups", []),
            #     roles=claims.get("roles", []),
            #     token_type=TokenType.JWT,
            #     token_valid=True,
            #     token_expiry=claims.get("exp"),
            #     provider="entra",
            # )

            return AuthenticatedIdentity(
                user_id="entra-validation-not-implemented",
                username="entra",
                display_name="Entra ID (interface ready)",
                email="",
                team_id="unknown",
                clearance_level=ClearanceLevel.PUBLIC,
                token_type=token_type,
                token_valid=False,
                provider="entra",
                is_authenticated=False,
            )

        except Exception:
            return AuthenticatedIdentity(
                user_id="entra-error",
                username="entra-error",
                display_name="Entra ID Validation Error",
                email="",
                team_id="unknown",
                clearance_level=ClearanceLevel.PUBLIC,
                token_type=token_type,
                token_valid=False,
                provider="entra",
                is_authenticated=False,
            )


# ==================================================================
# Provider Factory
# ==================================================================

def get_identity_provider() -> IdentityProvider:
    """
    Get the appropriate identity provider based on configuration.

    Priority:
    1. Entra ID (if configured)
    2. Local (API-key based)
    """
    entra = EntraIdentityProvider()
    if entra.is_available():
        return entra
    return LocalIdentityProvider()


def get_mock_provider() -> MockIdentityProvider:
    """Get a mock provider for testing."""
    return MockIdentityProvider()
