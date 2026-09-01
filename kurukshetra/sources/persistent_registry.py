"""
Persistent Source Registry
==========================

DuckDB-backed persistence layer for the Source Adapter Registry.

Stores source identity, configuration (non-secret), enabled status,
and sync state across server restarts.

Does NOT store secrets — credentials must come from environment variables.

The in-memory SourceAdapterRegistry handles adapter instances and runtime
lifecycle. This module handles durable state that must survive restarts.

Design principle: This module is COMPOSED with SourceAdapterRegistry,
not replacing it. The registry handles adapters; this handles persistence.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from kurukshetra.registry.database import get_connection

logger = logging.getLogger(__name__)


# ==================================================================
# Data Classes
# ==================================================================

@dataclass
class SourceRecord:
    """Durable record of a registered knowledge source."""

    source_id: str
    source_type: str               # SourceType.value (filesystem, salesforce, etc.)
    display_name: str
    description: str = ""
    owner_team: str = ""
    enabled: bool = True
    config_json: str = "{}"        # Non-secret config only
    default_visibility: str = "Internal"
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for API responses."""
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "display_name": self.display_name,
            "description": self.description,
            "owner_team": self.owner_team,
            "enabled": self.enabled,
            "config": json.loads(self.config_json) if self.config_json else {},
            "default_visibility": self.default_visibility,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class SyncStateRecord:
    """Synchronization state for a source."""

    source_id: str
    last_sync_at: Optional[str] = None
    last_sync_status: str = "never"     # never | success | partial | error
    last_error: str = ""
    consecutive_errors: int = 0
    total_syncs: int = 0
    documents_found: int = 0
    documents_new: int = 0
    documents_changed: int = 0
    documents_removed: int = 0
    cursor_value: Optional[str] = None  # Incremental sync cursor
    cursor_type: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "last_sync_at": self.last_sync_at,
            "last_sync_status": self.last_sync_status,
            "last_error": self.last_error,
            "consecutive_errors": self.consecutive_errors,
            "total_syncs": self.total_syncs,
            "documents_found": self.documents_found,
            "documents_new": self.documents_new,
            "documents_changed": self.documents_changed,
            "documents_removed": self.documents_removed,
            "cursor_value": self.cursor_value,
            "cursor_type": self.cursor_type,
        }


# ==================================================================
# Schema
# ==================================================================

_CREATE_SOURCE_REGISTRY = """
CREATE TABLE IF NOT EXISTS source_registry (
    source_id           TEXT PRIMARY KEY,
    source_type         TEXT NOT NULL,
    display_name        TEXT NOT NULL,
    description         TEXT DEFAULT '',
    owner_team          TEXT DEFAULT '',
    enabled             BOOLEAN DEFAULT TRUE,
    config_json         TEXT DEFAULT '{}',
    default_visibility  TEXT DEFAULT 'Internal',
    created_at          TIMESTAMP,
    updated_at          TIMESTAMP
)
"""

_CREATE_SYNC_STATE = """
CREATE TABLE IF NOT EXISTS source_sync_state (
    source_id           TEXT PRIMARY KEY,
    last_sync_at        TIMESTAMP,
    last_sync_status    TEXT DEFAULT 'never',
    last_error          TEXT DEFAULT '',
    consecutive_errors  INTEGER DEFAULT 0,
    total_syncs         INTEGER DEFAULT 0,
    documents_found     INTEGER DEFAULT 0,
    documents_new       INTEGER DEFAULT 0,
    documents_changed   INTEGER DEFAULT 0,
    documents_removed   INTEGER DEFAULT 0,
    cursor_value        TEXT,
    cursor_type         TEXT,
    FOREIGN KEY (source_id) REFERENCES source_registry(source_id)
)
"""


# ==================================================================
# PersistentSourceRegistry
# ==================================================================

class PersistentSourceRegistry:
    """DuckDB-backed source registry with CRUD and sync state management.

    Usage:
        store = PersistentSourceRegistry()

        # Register a source
        store.register_source(
            source_id="ics-network-share",
            source_type="network_share",
            display_name="ICS Network Share",
            owner_team="ICS",
        )

        # List sources
        sources = store.list_sources()

        # Update sync state
        store.record_sync_result(
            source_id="ics-network-share",
            status="success",
            documents_found=120,
            documents_new=15,
        )

        # Get cursor
        cursor = store.get_cursor("ics-network-share")
    """

    def __init__(self) -> None:
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Create tables if they don't exist."""
        conn = get_connection()
        try:
            conn.execute(_CREATE_SOURCE_REGISTRY)
            conn.execute(_CREATE_SYNC_STATE)
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Source CRUD
    # ------------------------------------------------------------------

    def register_source(
        self,
        source_id: str,
        source_type: str,
        display_name: str,
        description: str = "",
        owner_team: str = "",
        enabled: bool = True,
        config: Optional[dict] = None,
        default_visibility: str = "Internal",
    ) -> SourceRecord:
        """Register or update a source in the persistent registry.

        Secrets must NOT be passed in config. Use environment variables
        for credentials.

        Returns the SourceRecord.
        """
        now = datetime.utcnow().isoformat()
        config_json = json.dumps(config or {})

        # Validate config does not contain common secret patterns
        if config:
            self._validate_no_secrets(config, source_id)

        conn = get_connection()
        try:
            conn.execute(
                """INSERT INTO source_registry
                (source_id, source_type, display_name, description,
                 owner_team, enabled, config_json, default_visibility,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    source_type = excluded.source_type,
                    display_name = excluded.display_name,
                    description = excluded.description,
                    owner_team = excluded.owner_team,
                    enabled = excluded.enabled,
                    config_json = excluded.config_json,
                    default_visibility = excluded.default_visibility,
                    updated_at = excluded.updated_at""",
                (
                    source_id, source_type, display_name, description,
                    owner_team, enabled, config_json, default_visibility,
                    now, now,
                ),
            )
        finally:
            conn.close()

        logger.info(f"Registered source: {source_id} ({source_type})")
        return self.get_source(source_id)

    def get_source(self, source_id: str) -> Optional[SourceRecord]:
        """Get a single source record by ID."""
        conn = get_connection()
        try:
            row = conn.execute(
                """SELECT source_id, source_type, display_name, description,
                    owner_team, enabled, config_json, default_visibility,
                    created_at, updated_at
                FROM source_registry WHERE source_id = ?""",
                (source_id,),
            ).fetchone()
        finally:
            conn.close()

        if not row:
            return None

        return SourceRecord(
            source_id=row[0],
            source_type=row[1],
            display_name=row[2],
            description=row[3] or "",
            owner_team=row[4] or "",
            enabled=bool(row[5]),
            config_json=row[6] or "{}",
            default_visibility=row[7] or "Internal",
            created_at=str(row[8]) if row[8] else "",
            updated_at=str(row[9]) if row[9] else "",
        )

    def list_sources(self, enabled_only: bool = False) -> list[SourceRecord]:
        """List all registered sources."""
        conn = get_connection()
        try:
            if enabled_only:
                rows = conn.execute(
                    """SELECT source_id, source_type, display_name, description,
                        owner_team, enabled, config_json, default_visibility,
                        created_at, updated_at
                    FROM source_registry WHERE enabled = TRUE
                    ORDER BY display_name"""
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT source_id, source_type, display_name, description,
                        owner_team, enabled, config_json, default_visibility,
                        created_at, updated_at
                    FROM source_registry ORDER BY display_name"""
                ).fetchall()
        finally:
            conn.close()

        return [
            SourceRecord(
                source_id=r[0], source_type=r[1], display_name=r[2],
                description=r[3] or "", owner_team=r[4] or "",
                enabled=bool(r[5]), config_json=r[6] or "{}",
                default_visibility=r[7] or "Internal",
                created_at=str(r[8]) if r[8] else "",
                updated_at=str(r[9]) if r[9] else "",
            )
            for r in rows
        ]

    def update_source(
        self,
        source_id: str,
        **kwargs,
    ) -> Optional[SourceRecord]:
        """Update specific fields of a source record.

        Supported kwargs: display_name, description, owner_team,
        enabled, config, default_visibility.
        """
        allowed = {
            "display_name", "description", "owner_team",
            "enabled", "config", "default_visibility",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return self.get_source(source_id)

        # Validate secrets
        if "config" in updates and updates["config"]:
            self._validate_no_secrets(updates["config"], source_id)

        set_parts = []
        values = []
        for key, val in updates.items():
            if key == "config":
                set_parts.append("config_json = ?")
                values.append(json.dumps(val))
            elif key == "enabled":
                set_parts.append("enabled = ?")
                values.append(val)
            else:
                set_parts.append(f"{key} = ?")
                values.append(val)

        set_parts.append("updated_at = ?")
        values.append(datetime.utcnow().isoformat())
        values.append(source_id)

        conn = get_connection()
        try:
            conn.execute(
                f"UPDATE source_registry SET {', '.join(set_parts)} WHERE source_id = ?",
                values,
            )
        finally:
            conn.close()

        return self.get_source(source_id)

    def enable_source(self, source_id: str) -> Optional[SourceRecord]:
        """Enable a source."""
        return self.update_source(source_id, enabled=True)

    def disable_source(self, source_id: str) -> Optional[SourceRecord]:
        """Disable a source."""
        return self.update_source(source_id, enabled=False)

    def delete_source(self, source_id: str) -> bool:
        """Remove a source from the registry.

        Also removes its sync state. Does NOT remove ingested documents.
        """
        conn = get_connection()
        try:
            conn.execute("DELETE FROM source_sync_state WHERE source_id = ?", (source_id,))
            conn.execute("DELETE FROM source_registry WHERE source_id = ?", (source_id,))
        finally:
            conn.close()

        logger.info(f"Deleted source: {source_id}")
        return True

    def source_exists(self, source_id: str) -> bool:
        """Check if a source is registered."""
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT 1 FROM source_registry WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        finally:
            conn.close()
        return row is not None

    def count(self, enabled_only: bool = False) -> int:
        """Count registered sources."""
        conn = get_connection()
        try:
            if enabled_only:
                row = conn.execute(
                    "SELECT COUNT(*) FROM source_registry WHERE enabled = TRUE"
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM source_registry"
                ).fetchone()
        finally:
            conn.close()
        return row[0] if row else 0

    # ------------------------------------------------------------------
    # Sync State Management
    # ------------------------------------------------------------------

    def get_sync_state(self, source_id: str) -> Optional[SyncStateRecord]:
        """Get sync state for a source."""
        conn = get_connection()
        try:
            row = conn.execute(
                """SELECT source_id, last_sync_at, last_sync_status,
                    last_error, consecutive_errors, total_syncs,
                    documents_found, documents_new, documents_changed,
                    documents_removed, cursor_value, cursor_type
                FROM source_sync_state WHERE source_id = ?""",
                (source_id,),
            ).fetchone()
        finally:
            conn.close()

        if not row:
            return None

        return SyncStateRecord(
            source_id=row[0],
            last_sync_at=str(row[1]) if row[1] else None,
            last_sync_status=row[2] or "never",
            last_error=row[3] or "",
            consecutive_errors=row[4] or 0,
            total_syncs=row[5] or 0,
            documents_found=row[6] or 0,
            documents_new=row[7] or 0,
            documents_changed=row[8] or 0,
            documents_removed=row[9] or 0,
            cursor_value=row[10],
            cursor_type=row[11],
        )

    def record_sync_result(
        self,
        source_id: str,
        status: str,
        documents_found: int = 0,
        documents_new: int = 0,
        documents_changed: int = 0,
        documents_removed: int = 0,
        error: str = "",
    ) -> SyncStateRecord:
        """Record the result of a sync operation.

        Args:
            source_id: The source that was synced
            status: "success", "partial", or "error"
            documents_found: Total documents discovered
            documents_new: New documents ingested
            documents_changed: Documents updated
            documents_removed: Documents deleted
            error: Error message if status is "error"
        """
        now = datetime.utcnow().isoformat()

        conn = get_connection()
        try:
            # Get existing state
            existing = conn.execute(
                "SELECT consecutive_errors, total_syncs FROM source_sync_state WHERE source_id = ?",
                (source_id,),
            ).fetchone()

            prev_errors = existing[0] if existing else 0
            prev_total = existing[1] if existing else 0

            new_errors = 0 if status == "success" else prev_errors + 1
            new_total = prev_total + 1

            conn.execute(
                """INSERT INTO source_sync_state
                (source_id, last_sync_at, last_sync_status, last_error,
                 consecutive_errors, total_syncs,
                 documents_found, documents_new, documents_changed,
                 documents_removed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    last_sync_at = excluded.last_sync_at,
                    last_sync_status = excluded.last_sync_status,
                    last_error = excluded.last_error,
                    consecutive_errors = excluded.consecutive_errors,
                    total_syncs = excluded.total_syncs,
                    documents_found = excluded.documents_found,
                    documents_new = excluded.documents_new,
                    documents_changed = excluded.documents_changed,
                    documents_removed = excluded.documents_removed""",
                (
                    source_id, now, status, error,
                    new_errors, new_total,
                    documents_found, documents_new,
                    documents_changed, documents_removed,
                ),
            )
        finally:
            conn.close()

        return self.get_sync_state(source_id)

    def save_cursor(
        self,
        source_id: str,
        cursor_value: str,
        cursor_type: str = "adapter",
    ) -> None:
        """Save an incremental sync cursor for a source.

        This is compatible with the existing KnowledgeFabric source_cursors
        table — both tables store cursors. The source_sync_state table
        is the authoritative source; source_cursors remains for backward
        compatibility.
        """
        conn = get_connection()
        try:
            conn.execute(
                """INSERT INTO source_sync_state (source_id, cursor_value, cursor_type)
                VALUES (?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    cursor_value = excluded.cursor_value,
                    cursor_type = excluded.cursor_type""",
                (source_id, cursor_value, cursor_type),
            )
        finally:
            conn.close()

        # Also update legacy source_cursors table for backward compatibility
        try:
            from kurukshetra.knowledge.fabric import KnowledgeFabric
            fabric = KnowledgeFabric()
            fabric.save_source_cursor(source_id, cursor_value)
        except Exception:
            pass  # Best-effort legacy compat

    def get_cursor(self, source_id: str) -> Optional[str]:
        """Load the incremental sync cursor for a source."""
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT cursor_value FROM source_sync_state WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        finally:
            conn.close()

        if row and row[0]:
            return row[0]

        # Fallback to legacy source_cursors table
        try:
            from kurukshetra.knowledge.fabric import KnowledgeFabric
            fabric = KnowledgeFabric()
            return fabric.load_source_cursor(source_id)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Bulk Queries
    # ------------------------------------------------------------------

    def get_all_sync_states(self) -> list[SyncStateRecord]:
        """Get sync states for all registered sources."""
        conn = get_connection()
        try:
            rows = conn.execute(
                """SELECT sr.source_id,
                    ss.last_sync_at, ss.last_sync_status, ss.last_error,
                    ss.consecutive_errors, ss.total_syncs,
                    ss.documents_found, ss.documents_new, ss.documents_changed,
                    ss.documents_removed, ss.cursor_value, ss.cursor_type
                FROM source_registry sr
                LEFT JOIN source_sync_state ss ON sr.source_id = ss.source_id
                ORDER BY sr.display_name"""
            ).fetchall()
        finally:
            conn.close()

        return [
            SyncStateRecord(
                source_id=r[0],
                last_sync_at=str(r[1]) if r[1] else None,
                last_sync_status=r[2] or "never",
                last_error=r[3] or "",
                consecutive_errors=r[4] or 0,
                total_syncs=r[5] or 0,
                documents_found=r[6] or 0,
                documents_new=r[7] or 0,
                documents_changed=r[8] or 0,
                documents_removed=r[9] or 0,
                cursor_value=r[10],
                cursor_type=r[11],
            )
            for r in rows
        ]

    def get_sources_needing_sync(
        self, max_consecutive_errors: int = 5
    ) -> list[SourceRecord]:
        """Get enabled sources that should be synced.

        Returns sources that are:
        - enabled
        - have not exceeded max consecutive errors
        - have never been synced OR their last sync was more than 1 hour ago
        """
        conn = get_connection()
        try:
            rows = conn.execute(
                """SELECT sr.source_id, sr.source_type, sr.display_name,
                    sr.description, sr.owner_team, sr.enabled,
                    sr.config_json, sr.default_visibility,
                    sr.created_at, sr.updated_at
                FROM source_registry sr
                LEFT JOIN source_sync_state ss ON sr.source_id = ss.source_id
                WHERE sr.enabled = TRUE
                  AND (ss.consecutive_errors IS NULL
                       OR ss.consecutive_errors < ?)
                  AND (ss.last_sync_at IS NULL
                       OR ss.last_sync_at < CAST(CURRENT_TIMESTAMP AS TIMESTAMP) - INTERVAL '1 HOUR')
                ORDER BY sr.display_name""",
                (max_consecutive_errors,),
            ).fetchall()
        finally:
            conn.close()

        return [
            SourceRecord(
                source_id=r[0], source_type=r[1], display_name=r[2],
                description=r[3] or "", owner_team=r[4] or "",
                enabled=bool(r[5]), config_json=r[6] or "{}",
                default_visibility=r[7] or "Internal",
                created_at=str(r[8]) if r[8] else "",
                updated_at=str(r[9]) if r[9] else "",
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Security: Secret Validation
    # ------------------------------------------------------------------

    _SECRET_PATTERNS = (
        "password", "secret", "token", "api_key", "apikey",
        "access_key", "private_key", "credential", "auth_token",
        "client_secret", "bearer",
    )

    def _validate_no_secrets(self, config: dict, source_id: str) -> None:
        """Validate that config does not contain secret values.

        Logs a warning if potential secrets are found. Does not raise
        to avoid breaking registration, but makes the violation visible.
        """
        for key, value in config.items():
            key_lower = key.lower()
            for pattern in self._SECRET_PATTERNS:
                if pattern in key_lower:
                    # Check if value looks like a real secret (not a placeholder)
                    val_str = str(value).strip()
                    if val_str and val_str not in (
                        "", "env:", "ENV:", "${}", "os.environ", "REPLACE_ME",
                        "TODO", "none", "null",
                    ):
                        logger.warning(
                            f"SECURITY: Source '{source_id}' config key '{key}' "
                            f"may contain a secret. Secrets should come from "
                            f"environment variables, not config."
                        )
                    break

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def clear(self) -> int:
        """Remove all source records and sync states.

        USE WITH CAUTION — does not affect ingested documents.
        """
        conn = get_connection()
        try:
            conn.execute("DELETE FROM source_sync_state")
            conn.execute("DELETE FROM source_registry")
        finally:
            conn.close()
        logger.warning("Source registry cleared")
        return 0
