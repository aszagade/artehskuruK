"""
Security Configuration
======================

Central configuration for Tier-1 security controls.

API keys are read from environment variables.
If no keys are configured, the system runs in open mode (development default).

Allowed directories control path traversal protection.
CORS origins control cross-origin access.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SecurityConfig:
    """
    Tier-1 security configuration.

    All values are configurable via environment variables.
    Defaults are permissive for local development.
    """

    # --- API Key Authentication ---
    # Comma-separated list of valid API keys.
    # Empty string = open mode (no auth required).
    api_keys: list[str] = field(default_factory=lambda: _env_list("KURUKSHETRA_API_KEYS"))

    # Header name to look for the API key.
    api_key_header: str = "X-API-Key"

    # Whether authentication is enforced.
    # False = open mode (development default).
    # True = keys required (set via KURUKSHETRA_AUTH_REQUIRED=1).
    auth_required: bool = field(default_factory=lambda: _env_bool("KURUKSHETRA_AUTH_REQUIRED"))

    # --- CORS ---
    # Comma-separated list of allowed origins.
    # ["*"] = fully open (development default).
    cors_origins: list[str] = field(default_factory=lambda: _env_list("KURUKSHETRA_CORS_ORIGINS", ["*"]))

    # --- Path Traversal ---
    # Directories from which ingestion is allowed.
    # Paths outside these directories are rejected.
    allowed_ingest_dirs: list[Path] = field(
        default_factory=lambda: _env_path_list(
            "KURUKSHETRA_ALLOWED_INGEST_DIRS",
            # Default: project knowledge/ directory and tmp
            [
                str(Path.cwd() / "knowledge"),
                str(Path.cwd() / "tmp"),
            ],
        )
    )

    # --- Audit Logging ---
    # Whether to log requests to a file.
    audit_enabled: bool = field(default_factory=lambda: _env_bool("KURUKSHETRA_AUDIT_ENABLED", True))

    # Audit log file path.
    audit_log_path: str = field(
        default_factory=lambda: os.environ.get(
            "KURUKSHETRA_AUDIT_LOG_PATH", "kurukshetra_audit.log"
        )
    )

    # Maximum audit log file size in bytes before rotation (10 MB default).
    audit_max_bytes: int = field(
        default_factory=lambda: int(os.environ.get("KURUKSHETRA_AUDIT_MAX_BYTES", "10485760"))
    )

    # --- Knowledge Watcher ---
    # Enable/disable the continuous knowledge watcher.
    watcher_enabled: bool = field(default_factory=lambda: _env_bool("KURUKSHETRA_WATCHER_ENABLED", True))

    # Polling interval in seconds for the watcher.
    watcher_interval: int = field(
        default_factory=lambda: int(os.environ.get("KURUKSHETRA_WATCHER_INTERVAL", "30"))
    )

    # Comma-separated list of source directories to watch.
    watcher_sources: list[str] = field(
        default_factory=lambda: _env_list(
            "KURUKSHETRA_WATCHER_SOURCES",
            ["knowledge/inbox"],
        )
    )

    def is_key_valid(self, key: str) -> bool:
        """Check if an API key is valid."""
        if not self.auth_required:
            return True
        if not self.api_keys:
            return True  # Open mode if no keys configured
        return key in self.api_keys

    def is_path_allowed(self, file_path: Path) -> bool:
        """Check if a file path is within allowed ingest directories."""
        try:
            resolved = file_path.resolve()
        except (OSError, ValueError):
            return False

        for allowed_dir in self.allowed_ingest_dirs:
            try:
                allowed_resolved = allowed_dir.resolve()
                if str(resolved).startswith(str(allowed_resolved)):
                    return True
            except (OSError, ValueError):
                continue

        return False


# ------------------------------------------------------------------
# Environment variable helpers
# ------------------------------------------------------------------

def _env_bool(key: str, default: bool = False) -> bool:
    """Read a boolean from environment."""
    val = os.environ.get(key, "").strip().lower()
    if val in ("1", "true", "yes"):
        return True
    if val in ("0", "false", "no"):
        return False
    return default


def _env_list(key: str, default: list[str] | None = None) -> list[str]:
    """Read a comma-separated list from environment."""
    val = os.environ.get(key, "").strip()
    if val:
        return [v.strip() for v in val.split(",") if v.strip()]
    return default or []


def _env_path_list(key: str, default: list[str] | None = None) -> list[Path]:
    """Read a comma-separated list of paths from environment."""
    val = os.environ.get(key, "").strip()
    if val:
        return [Path(v.strip()) for v in val.split(",") if v.strip()]
    return [Path(v) for v in (default or [])]
