"""
Microsoft Entra OIDC Authentication
====================================

Provides /auth/login and /auth/callback endpoints for
Authorization Code + PKCE flow with Microsoft Entra ID.

Flow:
1. GET /auth/login → redirect to Entra authorization endpoint
2. User authenticates with Entra
3. Entra redirects to /auth/callback with authorization code
4. Backend exchanges code for tokens
5. Backend validates JWT and creates session
6. Backend returns session token to frontend

Security:
- State parameter prevents CSRF
- Nonce prevents replay attacks
- JWT validated (issuer, audience, expiry, signature)
- Session tokens are short-lived
- All tokens are validated at every request
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional

import jwt
import requests
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from kurukshetra.security.entra_provider import EntraConfig
from kurukshetra.security.identity_provider import (
    AuthenticatedIdentity,
    AuthorizationContext,
    TokenType,
)
from kurukshetra.security.identity import ClearanceLevel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


# ==================================================================
# Session Management
# ==================================================================

@dataclass
class Session:
    """A user session after successful authentication."""
    session_id: str
    identity: AuthenticatedIdentity
    created_at: float
    expires_at: float
    refresh_token: Optional[str] = None

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    def to_token(self) -> str:
        """Convert session to a JWT token for the frontend."""
        payload = {
            "sub": self.identity.user_id,
            "username": self.identity.username,
            "display_name": self.identity.display_name,
            "email": self.identity.email,
            "team_id": self.identity.team_id,
            "clearance": self.identity.clearance_level.name,
            "groups": self.identity.groups,
            "roles": self.identity.roles,
            "provider": self.identity.provider,
            "iat": int(self.created_at),
            "exp": int(self.expires_at),
            "session_id": self.session_id,
        }
        # Sign with a server-side secret
        secret = os.environ.get("KURUKSHETRA_SESSION_SECRET", "dev-session-secret-do-not-use-in-production")
        return jwt.encode(payload, secret, algorithm="HS256")

    @classmethod
    def from_token(cls, token: str) -> Optional["Session"]:
        """Decode a session token."""
        secret = os.environ.get("KURUKSHETRA_SESSION_SECRET", "dev-session-secret-do-not-use-in-production")
        try:
            payload = jwt.decode(token, secret, algorithms=["HS256"])
            identity = AuthenticatedIdentity(
                user_id=payload["sub"],
                username=payload.get("username", ""),
                display_name=payload.get("display_name", ""),
                email=payload.get("email", ""),
                team_id=payload.get("team_id", "unknown"),
                clearance_level=ClearanceLevel.from_string(payload.get("clearance", "internal")),
                groups=payload.get("groups", []),
                roles=payload.get("roles", []),
                provider=payload.get("provider", "entra"),
                token_type=TokenType.JWT,
                token_valid=True,
                is_authenticated=True,
            )
            return cls(
                session_id=payload.get("session_id", ""),
                identity=identity,
                created_at=payload.get("iat", time.time()),
                expires_at=payload.get("exp", time.time() + 3600),
            )
        except Exception as e:
            logger.warning(f"Failed to decode session token: {e}")
            return None


# In-memory session store (replace with Redis/DB in production)
_sessions: dict[str, Session] = {}
_pending_states: dict[str, dict] = {}  # state → {nonce, created_at}


# ==================================================================
# Request/Response Models
# ==================================================================

class LoginResponse(BaseModel):
    """Response from /auth/login."""
    auth_url: str
    state: str


class CallbackResponse(BaseModel):
    """Response from /auth/callback."""
    session_token: str
    user_id: str
    username: str
    display_name: str
    team_id: str
    clearance: str
    expires_at: float


class UserInfoResponse(BaseModel):
    """Response from /auth/me."""
    authenticated: bool
    user_id: str = ""
    username: str = ""
    display_name: str = ""
    email: str = ""
    team_id: str = ""
    clearance: str = ""
    groups: list[str] = []
    roles: list[str] = []
    provider: str = ""


# ==================================================================
# PKCE Helpers
# ==================================================================

def _generate_pkce() -> tuple[str, str]:
    """
    Generate PKCE code_verifier and code_challenge.

    code_verifier: 43-128 character random string (URL-safe)
    code_challenge: SHA256 hash of code_verifier, base64url-encoded
    """
    # Generate 96 random bytes, base64url-encode to get ~128 chars
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(96)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


# ==================================================================
# Endpoints
# ==================================================================

@router.get("/login", response_model=LoginResponse)
async def login():
    """
    Initiate Entra OIDC login flow.

    Generates a random state, nonce, and PKCE challenge.
    Stores them and returns the Entra authorization URL.
    """
    config = EntraConfig.from_env()

    if not config.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Entra ID not configured. Set ENTRA_TENANT_ID and ENTRA_CLIENT_ID."
        )

    # Generate state, nonce, and PKCE
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    code_verifier, code_challenge = _generate_pkce()

    # Store state with nonce and code_verifier (expires in 10 minutes)
    _pending_states[state] = {
        "nonce": nonce,
        "code_verifier": code_verifier,
        "created_at": time.time(),
        "expires_at": time.time() + 600,
    }

    # Build authorization URL
    redirect_uri = config.redirect_uri or "http://localhost:8000/auth/callback"

    params = {
        "client_id": config.client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": "openid profile email",
        "response_mode": "query",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    query = "&".join(f"{k}={requests.utils.quote(v)}" for k, v in params.items())
    auth_url = f"{config.authority}/oauth2/v2.0/authorize?{query}"

    logger.info(f"Login initiated: state={state[:8]}...")

    return LoginResponse(auth_url=auth_url, state=state)


@router.get("/callback")
async def callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
):
    """
    Handle Entra OIDC callback.

    Validates state, exchanges code for tokens, validates JWT,
    and creates a session.
    """
    # Handle errors from Entra
    if error:
        logger.error(f"Entra callback error: {error} - {error_description}")
        raise HTTPException(status_code=400, detail=f"Authentication failed: {error}")

    # Validate state
    if not state or state not in _pending_states:
        raise HTTPException(status_code=400, detail="Invalid or missing state parameter")

    state_data = _pending_states.pop(state)

    # Check state expiry
    if time.time() > state_data["expires_at"]:
        raise HTTPException(status_code=400, detail="State expired. Please try again.")

    # Validate code
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    # Exchange code for tokens
    config = EntraConfig.from_env()
    redirect_uri = config.redirect_uri or "http://localhost:8000/auth/callback"

    # Validate client_secret is configured (required for Web platform)
    if not config.client_secret:
        logger.error("ENTRA_CLIENT_SECRET not configured")
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: ENTRA_CLIENT_SECRET not set."
        )

    try:
        token_response = requests.post(
            f"{config.authority}/oauth2/v2.0/token",
            data={
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "nonce": state_data["nonce"],
                "code_verifier": state_data["code_verifier"],
            },
            timeout=10,
        )

        if token_response.status_code != 200:
            logger.error(f"Token exchange failed: {token_response.status_code} {token_response.text}")
            raise HTTPException(status_code=400, detail="Token exchange failed")

        token_data = token_response.json()
        id_token = token_data.get("id_token")
        access_token = token_data.get("access_token")

        if not id_token:
            raise HTTPException(status_code=400, detail="No ID token in response")

    except requests.RequestException as e:
        logger.error(f"Token exchange request failed: {e}")
        raise HTTPException(status_code=500, detail="Token exchange failed")

    # Validate ID token
    try:
        # Fetch JWKS to validate signature
        jwks_url = config.jwks_url or f"https://login.microsoftonline.com/{config.tenant_id}/discovery/v2.0/keys"
        jwks_response = requests.get(jwks_url, timeout=10)
        jwks = jwks_response.json()

        # Get the header to find the key ID
        unverified_header = jwt.get_unverified_header(id_token)
        kid = unverified_header.get("kid")

        # Find the matching key
        signing_key = None
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                from jwt.algorithms import RSAAlgorithm
                signing_key = RSAAlgorithm.from_jwk(key)
                break

        if not signing_key:
            raise HTTPException(status_code=400, detail="Unable to find signing key")

        # Validate JWT
        claims = jwt.decode(
            id_token,
            signing_key,
            algorithms=["RS256"],
            audience=config.client_id,
            issuer=config.issuer,
            options={
                "verify_exp": True,
                "verify_aud": True,
                "verify_iss": True,
                "verify_signature": True,
            },
        )

        # Validate nonce
        if claims.get("nonce") != state_data["nonce"]:
            raise HTTPException(status_code=400, detail="Nonce mismatch")

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="ID token expired")
    except jwt.InvalidAudienceError:
        raise HTTPException(status_code=400, detail="Invalid audience")
    except jwt.InvalidIssuerError:
        raise HTTPException(status_code=400, detail="Invalid issuer")
    except jwt.InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ID token validation failed: {e}")
        raise HTTPException(status_code=400, detail="ID token validation failed")

    # Extract identity from claims
    user_id = claims.get("sub", "")
    username = claims.get("preferred_username", claims.get("upn", ""))
    display_name = claims.get("name", "")
    email = claims.get("email", claims.get("preferred_username", ""))
    groups = claims.get("groups", [])
    roles = claims.get("roles", [])

    # Map groups to team (using config mapping)
    group_mapping = json.loads(os.environ.get("ENTRA_GROUP_TEAM_MAPPING", "{}"))
    team_id = "unknown"
    for group_id in groups:
        if group_id in group_mapping:
            team_id = group_mapping[group_id]
            break

    # Map roles to clearance
    role_mapping = json.loads(os.environ.get("ENTRA_ROLE_CLEARANCE_MAPPING", "{}"))
    clearance = ClearanceLevel.INTERNAL
    for role in roles:
        if role in role_mapping:
            try:
                clearance = ClearanceLevel.from_string(role_mapping[role])
            except Exception:
                pass
            break

    # Create identity
    identity = AuthenticatedIdentity(
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

    # Create session
    session_id = secrets.token_urlsafe(32)
    session = Session(
        session_id=session_id,
        identity=identity,
        created_at=time.time(),
        expires_at=time.time() + 3600,  # 1 hour
        refresh_token=token_data.get("refresh_token"),
    )

    _sessions[session_id] = session

    logger.info(f"Login successful: user={username} team={team_id}")

    # Return session token
    session_token = session.to_token()

    return CallbackResponse(
        session_token=session_token,
        user_id=user_id,
        username=username,
        display_name=display_name,
        team_id=team_id,
        clearance=clearance.name,
        expires_at=session.expires_at,
    )


@router.get("/me", response_model=UserInfoResponse)
async def get_current_user(request: Request):
    """Get current authenticated user from session token."""
    # Extract token from Authorization header
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return UserInfoResponse(authenticated=False)

    token = auth_header[7:]
    session = Session.from_token(token)

    if not session or session.is_expired:
        return UserInfoResponse(authenticated=False)

    return UserInfoResponse(
        authenticated=True,
        user_id=session.identity.user_id,
        username=session.identity.username,
        display_name=session.identity.display_name,
        email=session.identity.email,
        team_id=session.identity.team_id,
        clearance=session.identity.clearance_level.name,
        groups=session.identity.groups,
        roles=session.identity.roles,
        provider=session.identity.provider,
    )


@router.post("/logout")
async def logout(request: Request):
    """Logout and invalidate session."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        session = Session.from_token(token)
        if session:
            _sessions.pop(session.session_id, None)

    return {"status": "logged out"}


# ==================================================================
# Helper: Get identity from request (for other routers)
# ==================================================================

def get_identity_from_request(request: Request) -> AuthenticatedIdentity:
    """
    Extract AuthenticatedIdentity from request.

    Checks for:
    1. Bearer token in Authorization header (Entra/session)
    2. X-API-Key header (development)

    Returns ANONYMOUS if not authenticated.
    """
    # Check for Bearer token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        session = Session.from_token(token)
        if session and not session.is_expired:
            return session.identity

    # Fall back to API key (development)
    api_key = request.headers.get("X-API-Key", "")
    if api_key:
        from kurukshetra.security.identity_provider import LocalIdentityProvider
        provider = LocalIdentityProvider()
        return provider.authenticate(api_key, TokenType.API_KEY)

    # Anonymous
    return AuthenticatedIdentity(
        user_id="anonymous",
        username="anonymous",
        display_name="Anonymous",
        email="",
        team_id="unknown",
        clearance_level=ClearanceLevel.PUBLIC,
        token_type=TokenType.NONE,
        token_valid=False,
        provider="local",
        is_authenticated=False,
    )
