"""Confluence OAuth Router.

Handles the Atlassian OAuth 2.0 authorization-code flow.
Token persistence and Confluence content ingestion will be added separately.
"""

from __future__ import annotations

import os
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv


load_dotenv(dotenv_path=".env")

router = APIRouter(prefix="/api/confluence", tags=["Confluence"])


# Temporary localhost OAuth state store.
# Production will replace this with persistent, user-bound state.
_pending_states: set[str] = set()


@router.get("/auth/login")
async def confluence_login():
    """Start the Atlassian OAuth 2.0 authorization flow."""

    client_id = os.getenv("CONFLUENCE_OAUTH_CLIENT_ID")
    redirect_uri = os.getenv("CONFLUENCE_OAUTH_REDIRECT_URI")

    if not client_id:
        raise HTTPException(
            status_code=500,
            detail="CONFLUENCE_OAUTH_CLIENT_ID is not configured",
        )

    if not redirect_uri:
        raise HTTPException(
            status_code=500,
            detail="CONFLUENCE_OAUTH_REDIRECT_URI is not configured",
        )

    state = secrets.token_urlsafe(32)
    _pending_states.add(state)

    params = {
        "audience": "api.atlassian.com",
        "client_id": client_id,
        "scope": (
            "read:content:confluence "
            "read:content-details:confluence "
            "read:space-details:confluence "
            "read:space:confluence "
            "read:attachment:confluence "
            "read:page:confluence "
            "read:hierarchical-content:confluence"
        ),
        "redirect_uri": redirect_uri,
        "state": state,
        "response_type": "code",
        "prompt": "consent",
    }

    authorize_url = (
        "https://auth.atlassian.com/authorize?"
        + urlencode(params)
    )

    return RedirectResponse(url=authorize_url, status_code=302)


@router.get("/auth/callback")
async def confluence_callback(code: str, state: str):
    """Receive the Atlassian OAuth authorization callback and exchange the code."""

    if not state or state not in _pending_states:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired OAuth state",
        )

    _pending_states.remove(state)

    if not code:
        raise HTTPException(
            status_code=400,
            detail="Missing OAuth authorization code",
        )

    try:
        from kurukshetra.sources.confluence_oauth import (
            ConfluenceOAuthClient,
            store_token,
        )

        client = ConfluenceOAuthClient()
        token_data = await client.exchange_code(code)
        store_token(token_data)

        return {
            "status": "authenticated",
            "message": "Confluence OAuth authentication succeeded.",
            "token_type": token_data.get("token_type", "Bearer"),
            "expires_in": token_data.get("expires_in"),
            "refresh_token_present": bool(token_data.get("refresh_token")),
        }

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Confluence OAuth token exchange failed: {exc}",
        ) from exc


@router.get("/auth/resources")
async def confluence_accessible_resources():
    """Return Atlassian resources accessible to the authenticated OAuth grant."""

    from kurukshetra.sources.confluence_oauth import (
        ConfluenceOAuthClient,
        get_token,
    )

    token = get_token()

    if not token or not token.get("access_token"):
        raise HTTPException(
            status_code=401,
            detail="Confluence is not authenticated",
        )

    try:
        client = ConfluenceOAuthClient()
        resources = await client.accessible_resources(
            token["access_token"]
        )

        safe_resources = []

        for resource in resources:
            safe_resources.append(
                {
                    "id": resource.get("id"),
                    "name": resource.get("name"),
                    "url": resource.get("url"),
                    "scopes": resource.get("scopes", []),
                }
            )

        return {
            "authenticated": True,
            "resource_count": len(safe_resources),
            "resources": safe_resources,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to query Atlassian accessible resources: {exc}",
        ) from exc


@router.get("/spaces")
async def confluence_spaces():
    """Read a small page of Confluence spaces without ingesting content."""

    from kurukshetra.sources.confluence_oauth import get_token

    token = get_token()

    if not token or not token.get("access_token"):
        raise HTTPException(
            status_code=401,
            detail="Confluence is not authenticated",
        )

    # Cloud ID is obtained from the accessible-resources response.
    # For this first diagnostic, require it explicitly in the environment
    # rather than silently guessing or selecting a resource.
    cloud_id = os.getenv("CONFLUENCE_CLOUD_ID")

    if not cloud_id:
        raise HTTPException(
            status_code=500,
            detail="CONFLUENCE_CLOUD_ID is not configured",
        )

    url = (
        f"https://api.atlassian.com/ex/confluence/"
        f"{cloud_id}/wiki/api/v2/spaces"
    )

    headers = {
        "Authorization": f"Bearer {token['access_token']}",
        "Accept": "application/json",
    }

    import httpx

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                headers=headers,
                params={"limit": 10},
            )

        if response.status_code != 200:
            try:
                detail = response.json()
            except Exception:
                detail = response.text

            raise HTTPException(
                status_code=502,
                detail=(
                    f"Confluence spaces request failed "
                    f"(HTTP {response.status_code}): {detail}"
                ),
            )

        data = response.json()

        results = data.get("results", [])

        return {
            "batch_size": len(results),
            "limit": 10,
            "has_more": bool(
                data.get("_links", {}).get("next")
            ),
            "spaces": [
                {
                    "id": space.get("id"),
                    "key": space.get("key"),
                    "name": space.get("name"),
                    "type": space.get("type"),
                    "status": space.get("status"),
                }
                for space in results
            ],
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to query Confluence spaces: {exc}",
        ) from exc


@router.get("/spaces/{space_id}/pages")
async def confluence_space_pages(space_id: str):
    """Read at most five pages from one Confluence space.

    This endpoint is diagnostic only. It does not ingest content.
    """

    from kurukshetra.sources.confluence_oauth import get_token
    import httpx

    token = get_token()

    if not token or not token.get("access_token"):
        raise HTTPException(
            status_code=401,
            detail="Confluence is not authenticated",
        )

    cloud_id = os.getenv("CONFLUENCE_CLOUD_ID")

    if not cloud_id:
        raise HTTPException(
            status_code=500,
            detail="CONFLUENCE_CLOUD_ID is not configured",
        )

    url = (
        f"https://api.atlassian.com/ex/confluence/"
        f"{cloud_id}/wiki/api/v2/pages"
    )

    headers = {
        "Authorization": f"Bearer {token['access_token']}",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                headers=headers,
                params={
                    "space-id": space_id,
                    "limit": 5,
                },
            )

        if response.status_code != 200:
            try:
                detail = response.json()
            except Exception:
                detail = response.text

            raise HTTPException(
                status_code=502,
                detail=(
                    f"Confluence pages request failed "
                    f"(HTTP {response.status_code}): {detail}"
                ),
            )

        data = response.json()
        results = data.get("results", [])

        pages = []

        for page in results:
            pages.append(
                {
                    "id": page.get("id"),
                    "title": page.get("title"),
                    "status": page.get("status"),
                    "space_id": page.get("spaceId"),
                    "parent_id": page.get("parentId"),
                    "created_at": page.get("createdAt"),
                    "version": page.get("version"),
                    "web_link": page.get("_links", {}).get("webui"),
                }
            )

        return {
            "space_id": space_id,
            "batch_size": len(pages),
            "limit": 5,
            "has_more": bool(
                data.get("_links", {}).get("next")
            ),
            "pages": pages,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to query Confluence pages: {exc}",
        ) from exc


@router.get("/pages/{page_id}")
async def confluence_page(page_id: str):
    """Read one Confluence page with its body, without ingesting it."""

    from kurukshetra.sources.confluence_oauth import get_token
    import httpx

    token = get_token()

    if not token or not token.get("access_token"):
        raise HTTPException(
            status_code=401,
            detail="Confluence is not authenticated",
        )

    cloud_id = os.getenv("CONFLUENCE_CLOUD_ID")

    if not cloud_id:
        raise HTTPException(
            status_code=500,
            detail="CONFLUENCE_CLOUD_ID is not configured",
        )

    url = (
        f"https://api.atlassian.com/ex/confluence/"
        f"{cloud_id}/wiki/api/v2/pages/{page_id}"
    )

    headers = {
        "Authorization": f"Bearer {token['access_token']}",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                headers=headers,
                params={
                    "body-format": "storage",
                },
            )

        if response.status_code != 200:
            try:
                detail = response.json()
            except Exception:
                detail = response.text

            raise HTTPException(
                status_code=502,
                detail=(
                    f"Confluence page request failed "
                    f"(HTTP {response.status_code}): {detail}"
                ),
            )

        page = response.json()

        body = page.get("body", {})
        storage = body.get("storage", {})

        return {
            "id": page.get("id"),
            "title": page.get("title"),
            "status": page.get("status"),
            "space_id": page.get("spaceId"),
            "parent_id": page.get("parentId"),
            "created_at": page.get("createdAt"),
            "version": page.get("version"),
            "body_format": storage.get("representation"),
            "body_length": len(storage.get("value", "")),
            "body": storage.get("value", ""),
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to query Confluence page: {exc}",
        ) from exc


@router.get("/auth/status")
async def confluence_auth_status():
    """Return the current localhost OAuth state."""

    from kurukshetra.sources.confluence_oauth import get_token

    configured = bool(
        os.getenv("CONFLUENCE_OAUTH_CLIENT_ID")
        and os.getenv("CONFLUENCE_OAUTH_CLIENT_SECRET")
        and os.getenv("CONFLUENCE_OAUTH_REDIRECT_URI")
    )

    token = get_token()

    return {
        "configured": configured,
        "authenticated": bool(token and token.get("access_token")),
        "pending_states": len(_pending_states),
    }
