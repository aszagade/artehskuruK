"""
FastAPI Authorization Dependencies
===================================

Provides reusable FastAPI dependencies for:

1. get_current_user()    — extract authenticated user from request
2. require_team()        — restrict endpoint to specific teams
3. require_clearance()   — restrict endpoint to clearance level
4. get_audit_context()   — extract user info for audit logging

Usage in endpoints:

    @router.post("/query")
    async def query(
        request: QueryRequest,
        user: UserIdentity = Depends(get_current_user),
    ):
        # user is authenticated (or ANONYMOUS if open mode)
        ...

    @router.post("/entity/{id}/confirm")
    async def confirm(
        entity_id: str,
        user: UserIdentity = Depends(require_team("spm", "ics")),
    ):
        # only SPM and ICS users can confirm entities
        ...
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException, Request

from .config import SecurityConfig
from .identity import (
    ANONYMOUS,
    ClearanceLevel,
    UserIdentity,
    UserStore,
)


# ==================================================================
# Singleton instances (lazy)
# ==================================================================

_config: SecurityConfig | None = None
_user_store: UserStore | None = None


def _get_config() -> SecurityConfig:
    global _config
    if _config is None:
        _config = SecurityConfig()
    return _config


def _get_user_store() -> UserStore:
    global _user_store
    if _user_store is None:
        _user_store = UserStore()
    return _user_store


# ==================================================================
# Dependency: get_current_user
# ==================================================================

async def get_current_user(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> UserIdentity:
    """
    Extract the authenticated user from the request.

    Behavior:
    - If auth_required=False (open mode): returns ANONYMOUS
    - If auth_required=True and valid API key: returns UserIdentity
    - If auth_required=True and invalid/missing key: raises 401

    The resolved user is also stored on request.state.user
    for downstream use (audit logging, etc.).
    """
    config = _get_config()

    # Open mode: return anonymous user
    if not config.auth_required:
        user = ANONYMOUS
        _set_request_user(request, user)
        return user

    # No API key provided
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Provide X-API-Key header.",
        )

    # Look up user by API key
    store = _get_user_store()
    user = store.get_by_api_key(x_api_key)

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key.",
        )

    _set_request_user(request, user)
    return user


# ==================================================================
# Dependency: require_team
# ==================================================================

def require_team(*allowed_teams: str):
    """
    Create a dependency that restricts access to specific teams.

    Usage:
        @router.post("/confirm")
        async def confirm(user = Depends(require_team("spm", "ics"))):
            ...

    In open mode (auth_required=False), this allows all teams.
    """

    async def _check_team(
        request: Request,
        x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    ) -> UserIdentity:
        user = await get_current_user(request, x_api_key)

        # In open mode, allow all teams
        if not user.is_authenticated:
            return user

        # Check team membership
        if user.team_id not in allowed_teams:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Team '{user.team_id}' is not authorized. "
                    f"Required: one of {list(allowed_teams)}"
                ),
            )

        return user

    return _check_team


# ==================================================================
# Dependency: require_clearance
# ==================================================================

def require_clearance(min_level: ClearanceLevel):
    """
    Create a dependency that restricts access by clearance level.

    Usage:
        @router.get("/confidential-data")
        async def get_confidential(
            user = Depends(require_clearance(ClearanceLevel.CONFIDENTIAL))
        ):
            ...
    """

    async def _check_clearance(
        request: Request,
        x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    ) -> UserIdentity:
        user = await get_current_user(request, x_api_key)

        # In open mode, allow all
        if not user.is_authenticated:
            return user

        if user.clearance_level < min_level:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Insufficient clearance. Required: {min_level.name}, "
                    f"current: {user.clearance_level.name}"
                ),
            )

        return user

    return _check_clearance


# ==================================================================
# Helper: get user from request state
# ==================================================================

def _set_request_user(request: Request, user: UserIdentity) -> None:
    """Store user on request.state for downstream use."""
    if not hasattr(request, "state"):
        request.state = type("State", (), {})()
    request.state.user = user


def get_user_from_request(request: Request) -> UserIdentity:
    """Retrieve the user that was set by get_current_user."""
    if hasattr(request.state, "user"):
        return request.state.user
    return ANONYMOUS
