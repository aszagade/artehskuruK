"""Atlassian Confluence OAuth 2.0 client.

Handles authorization-code exchange and accessible-resource discovery.
Secrets and tokens stay server-side and are never returned by API routes.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx
from dotenv import load_dotenv


load_dotenv(dotenv_path=".env")


class ConfluenceOAuthClient:
    """Small server-side client for Atlassian OAuth 2.0."""

    TOKEN_URL = "https://auth.atlassian.com/oauth/token"
    RESOURCES_URL = "https://api.atlassian.com/oauth/token/accessible-resources"

    def __init__(self) -> None:
        self.client_id = os.getenv("CONFLUENCE_OAUTH_CLIENT_ID", "")
        self.client_secret = os.getenv("CONFLUENCE_OAUTH_CLIENT_SECRET", "")
        self.redirect_uri = os.getenv("CONFLUENCE_OAUTH_REDIRECT_URI", "")

        if not self.client_id:
            raise ValueError("CONFLUENCE_OAUTH_CLIENT_ID is not configured")
        if not self.client_secret:
            raise ValueError("CONFLUENCE_OAUTH_CLIENT_SECRET is not configured")
        if not self.redirect_uri:
            raise ValueError("CONFLUENCE_OAUTH_REDIRECT_URI is not configured")

    async def exchange_code(self, code: str) -> dict[str, Any]:
        """Exchange an authorization code for Atlassian OAuth tokens."""

        if not code:
            raise ValueError("authorization code is required")

        payload = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": self.redirect_uri,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(self.TOKEN_URL, json=payload)

        if response.status_code != 200:
            try:
                detail: Any = response.json()
            except Exception:
                detail = response.text

            raise RuntimeError(
                f"Atlassian token exchange failed "
                f"(HTTP {response.status_code}): {detail}"
            )

        data = response.json()

        access_token = data.get("access_token")
        if not access_token:
            raise RuntimeError(
                "Atlassian token response did not contain an access_token"
            )

        return data

    async def accessible_resources(
        self,
        access_token: str,
    ) -> list[dict[str, Any]]:
        """Return Atlassian resources accessible with the OAuth token."""

        if not access_token:
            raise ValueError("access_token is required")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                self.RESOURCES_URL,
                headers=headers,
            )

        if response.status_code != 200:
            try:
                detail: Any = response.json()
            except Exception:
                detail = response.text

            raise RuntimeError(
                f"Atlassian accessible-resources request failed "
                f"(HTTP {response.status_code}): {detail}"
            )

        data = response.json()

        if not isinstance(data, list):
            raise RuntimeError(
                "Atlassian accessible-resources response was not a list"
            )

        return data


# Temporary localhost-only token holder.
# Production will replace this with encrypted persistent storage.
_token: Optional[dict[str, Any]] = None


def store_token(token_data: dict[str, Any]) -> None:
    """Store OAuth token data server-side for the current process."""

    global _token
    _token = dict(token_data)


def get_token() -> Optional[dict[str, Any]]:
    """Return the current server-side token, if authenticated."""

    return dict(_token) if _token else None


def clear_token() -> None:
    """Clear the current server-side OAuth token."""

    global _token
    _token = None
