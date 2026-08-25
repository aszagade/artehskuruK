"""
Security Middleware
===================

Tier-1 security controls for the KURUKSHETRA API:

1. APIKeyAuth     — API-key authentication (development boundary)
2. AuditLog       — Request audit logging
3. PathTraversalGuard — Path traversal protection for file ingestion
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .config import SecurityConfig

logger = logging.getLogger("kurukshetra.security")


# ==================================================================
# 1. API-Key Authentication Middleware
# ==================================================================

class APIKeyAuth(BaseHTTPMiddleware):
    """
    Validates API key from the X-API-Key header.

    Bypasses:
    - /api/health (always open)
    - Any path starting with /docs, /openapi, /redoc (FastAPI docs)

    When auth_required=False (development default), all requests pass.
    """

    # Paths that never require authentication.
    PUBLIC_PATHS: set[str] = {
        "/api/health",
        "/docs",
        "/openapi.json",
        "/redoc",
    }

    def __init__(self, app, config: SecurityConfig | None = None) -> None:
        super().__init__(app)
        self.config = config or SecurityConfig()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Check if auth is required
        if not self.config.auth_required:
            return await call_next(request)

        # Skip auth for public paths
        path = request.url.path.rstrip("/")
        if path in self.PUBLIC_PATHS or any(path.startswith(p) for p in ["/docs", "/openapi", "/redoc"]):
            return await call_next(request)

        # Extract API key from header
        api_key = request.headers.get(self.config.api_key_header, "")

        if not self.config.is_key_valid(api_key):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Invalid or missing API key. "
                    f"Provide a valid key in the {self.config.api_key_header} header."
                },
            )

        return await call_next(request)


# ==================================================================
# 2. Audit Logging Middleware
# ==================================================================

class AuditLog(BaseHTTPMiddleware):
    """
    Logs every API request to a structured audit log.

    Each line is a JSON object with:
    - timestamp
    - method
    - path
    - status_code
    - duration_ms
    - client_ip
    - api_key_present (bool, not the actual key)
    """

    def __init__(self, app, config: SecurityConfig | None = None) -> None:
        super().__init__(app)
        self.config = config or SecurityConfig()
        self._log_file = None

    def _ensure_log_file(self):
        """Open audit log file if needed."""
        if self._log_file is None and self.config.audit_enabled:
            try:
                self._log_file = open(self.config.audit_log_path, "a", encoding="utf-8")
            except OSError as e:
                logger.warning("Cannot open audit log file %s: %s", self.config.audit_log_path, e)

    def _write_entry(self, entry: dict) -> None:
        """Write a single audit entry."""
        if not self.config.audit_enabled:
            return

        self._ensure_log_file()
        if self._log_file is None:
            return

        try:
            self._log_file.write(json.dumps(entry) + "\n")
            self._log_file.flush()
        except OSError as e:
            logger.warning("Audit write failed: %s", e)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self.config.audit_enabled:
            return await call_next(request)

        start = time.time()
        api_key_present = bool(request.headers.get(self.config.api_key_header))
        client_ip = request.client.host if request.client else "unknown"

        response = await call_next(request)

        duration_ms = round((time.time() - start) * 1000, 1)

        # Extract user identity if set by auth middleware
        user_id = "anonymous"
        team_id = "unknown"
        if hasattr(request, "state"):
            user = getattr(request.state, "user", None)
            if user is not None and hasattr(user, "user_id"):
                user_id = str(user.user_id)
                team_id = str(user.team_id)

        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "client_ip": client_ip,
            "api_key_present": api_key_present,
            "user_id": user_id,
            "team_id": team_id,
        }

        self._write_entry(entry)

        return response


# ==================================================================
# 3. Path Traversal Guard
# ==================================================================

class PathTraversalGuard(BaseHTTPMiddleware):
    """
    Validates that file paths in ingestion requests are within
    allowed directories.

    Intercepts POST /api/ingest and checks the file_path field.
    Returns 403 if the path is outside allowed directories.
    """

    def __init__(self, app, config: SecurityConfig | None = None) -> None:
        super().__init__(app)
        self.config = config or SecurityConfig()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Only intercept ingestion endpoints
        if request.method == "POST" and request.url.path.rstrip("/") in ("/api/ingest",):
            try:
                # Read the request body to check file_path
                body = await request.body()
                if body:
                    data = json.loads(body)
                    file_path_str = data.get("file_path", "")

                    if file_path_str:
                        file_path = Path(file_path_str)

                        if not self.config.is_path_allowed(file_path):
                            return JSONResponse(
                                status_code=403,
                                content={
                                    "detail": (
                                        f"Path traversal denied: '{file_path_str}' is outside "
                                        "the allowed ingest directories. "
                                        f"Allowed: {[str(d) for d in self.config.allowed_ingest_dirs]}"
                                    )
                                },
                            )

            except (json.JSONDecodeError, ValueError):
                pass  # Let the endpoint handle malformed requests

        return await call_next(request)
