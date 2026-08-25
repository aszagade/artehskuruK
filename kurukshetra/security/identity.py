"""
User Identity & Authorization
==============================

Minimal identity model for KURUKSHETRA:

- Users are stored in DuckDB (no external IAM)
- Each user has a team_id and clearance_level
- Clearance determines maximum document visibility
- Team determines which team-scoped resources are accessible
- API key maps to exactly one user

Design principles:
- No passwords (API-key-only for now)
- No sessions (stateless per-request)
- No external dependencies
- Compatible with existing VisibilityFilter
- Deterministic and auditable
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

from kurukshetra.registry.database import get_connection


# ==================================================================
# Clearance levels (mirrors VisibilityLevel)
# ==================================================================

class ClearanceLevel(IntEnum):
    """User clearance levels, ordered by access scope."""
    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2
    RESTRICTED = 3

    @classmethod
    def from_string(cls, value: str | None) -> ClearanceLevel:
        if value is None:
            return cls.INTERNAL
        mapping = {
            "public": cls.PUBLIC,
            "internal": cls.INTERNAL,
            "confidential": cls.CONFIDENTIAL,
            "restricted": cls.RESTRICTED,
        }
        return mapping.get(value.strip().lower(), cls.INTERNAL)


# ==================================================================
# User Identity dataclass
# ==================================================================

@dataclass(slots=True)
class UserIdentity:
    """
    Authenticated user context carried through the request.

    Populated by APIKeyAuth middleware after successful authentication.
    Used by endpoint dependencies for authorization decisions.
    """
    user_id: str
    username: str
    display_name: str
    team_id: str
    clearance_level: ClearanceLevel
    is_authenticated: bool = True

    @property
    def max_visibility(self) -> str:
        """Return the string form of this user's max visibility."""
        return ClearanceLevel(self.clearance_level).name.lower()

    def can_see(self, doc_visibility: str) -> bool:
        """Check if this user can see a document with the given visibility."""
        doc_level = ClearanceLevel.from_string(doc_visibility)
        return doc_level <= self.clearance_level


# ==================================================================
# Anonymous / unauthenticated user
# ==================================================================

ANONYMOUS = UserIdentity(
    user_id="anonymous",
    username="anonymous",
    display_name="Anonymous",
    team_id="unknown",
    clearance_level=ClearanceLevel.PUBLIC,
    is_authenticated=False,
)


# ==================================================================
# User Store (DuckDB persistence)
# ==================================================================

class UserStore:
    """
    Manages user identity in DuckDB.

    Provides:
    - User CRUD
    - API-key lookup
    - Team-based user queries
    """

    def __init__(self) -> None:
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Create users table if it doesn't exist."""
        conn = get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                display_name TEXT,
                team_id TEXT NOT NULL DEFAULT 'unknown',
                clearance_level TEXT NOT NULL DEFAULT 'internal',
                api_key_hash TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Note: connection is NOT closed here — it will be reused by subsequent calls.

    def create_user(
        self,
        username: str,
        display_name: str = "",
        team_id: str = "unknown",
        clearance_level: str = "internal",
        api_key: str = "",
    ) -> UserIdentity:
        """Create a new user and return their identity."""
        user_id = f"USR-{username.upper()}"
        api_key_hash = _hash_key(api_key) if api_key else ""

        conn = get_connection()
        # Check if user already exists
        existing = conn.execute(
            "SELECT user_id FROM users WHERE username = ?", (username,)
        ).fetchone()

        if existing:
            # Update existing user
            conn.execute(
                """UPDATE users SET display_name = ?, team_id = ?,
                clearance_level = ?, api_key_hash = ?, status = 'active'
                WHERE username = ?""",
                (display_name or username, team_id, clearance_level,
                 api_key_hash, username),
            )
        else:
            # Insert new user
            conn.execute(
                """INSERT INTO users
                (user_id, username, display_name, team_id, clearance_level,
                 api_key_hash, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP)""",
                (user_id, username, display_name or username, team_id,
                 clearance_level, api_key_hash),
            )
        conn.close()

        return UserIdentity(
            user_id=user_id,
            username=username,
            display_name=display_name or username,
            team_id=team_id,
            clearance_level=ClearanceLevel.from_string(clearance_level),
        )

    def get_by_api_key(self, api_key: str) -> Optional[UserIdentity]:
        """Look up a user by their API key."""
        if not api_key:
            return None

        key_hash = _hash_key(api_key)
        conn = get_connection()
        row = conn.execute(
            """SELECT user_id, username, display_name, team_id, clearance_level, status
            FROM users WHERE api_key_hash = ? AND status = 'active'""",
            (key_hash,),
        ).fetchone()
        conn.close()

        if row is None:
            return None

        return UserIdentity(
            user_id=row[0],
            username=row[1],
            display_name=row[2],
            team_id=row[3],
            clearance_level=ClearanceLevel.from_string(row[4]),
        )

    def get_by_username(self, username: str) -> Optional[UserIdentity]:
        """Look up a user by username."""
        conn = get_connection()
        row = conn.execute(
            """SELECT user_id, username, display_name, team_id, clearance_level, status
            FROM users WHERE username = ? AND status = 'active'""",
            (username,),
        ).fetchone()
        conn.close()

        if row is None:
            return None

        return UserIdentity(
            user_id=row[0],
            username=row[1],
            display_name=row[2],
            team_id=row[3],
            clearance_level=ClearanceLevel.from_string(row[4]),
        )

    def get_by_id(self, user_id: str) -> Optional[UserIdentity]:
        """Look up a user by user_id."""
        conn = get_connection()
        row = conn.execute(
            """SELECT user_id, username, display_name, team_id, clearance_level, status
            FROM users WHERE user_id = ? AND status = 'active'""",
            (user_id,),
        ).fetchone()
        conn.close()

        if row is None:
            return None

        return UserIdentity(
            user_id=row[0],
            username=row[1],
            display_name=row[2],
            team_id=row[3],
            clearance_level=ClearanceLevel.from_string(row[4]),
        )

    def list_users(self, team_id: str | None = None) -> list[UserIdentity]:
        """List all active users, optionally filtered by team."""
        conn = get_connection()
        if team_id:
            rows = conn.execute(
                """SELECT user_id, username, display_name, team_id, clearance_level
                FROM users WHERE status = 'active' AND team_id = ?""",
                (team_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT user_id, username, display_name, team_id, clearance_level
                FROM users WHERE status = 'active'"""
            ).fetchall()
        conn.close()

        return [
            UserIdentity(
                user_id=r[0], username=r[1], display_name=r[2],
                team_id=r[3], clearance_level=ClearanceLevel.from_string(r[4]),
            )
            for r in rows
        ]

    def deactivate_user(self, user_id: str) -> bool:
        """Deactivate a user."""
        conn = get_connection()
        before = conn.execute(
            "SELECT COUNT(*) FROM users WHERE user_id = ? AND status = 'active'",
            (user_id,),
        ).fetchone()[0]
        conn.execute(
            "UPDATE users SET status = 'inactive' WHERE user_id = ?",
            (user_id,),
        )
        conn.close()
        return before > 0

    def update_team(self, user_id: str, team_id: str) -> bool:
        """Update a user's team assignment."""
        conn = get_connection()
        before = conn.execute(
            "SELECT COUNT(*) FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        conn.execute(
            "UPDATE users SET team_id = ? WHERE user_id = ?",
            (team_id, user_id),
        )
        conn.close()
        return before > 0

    def update_clearance(self, user_id: str, clearance_level: str) -> bool:
        """Update a user's clearance level."""
        conn = get_connection()
        before = conn.execute(
            "SELECT COUNT(*) FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        conn.execute(
            "UPDATE users SET clearance_level = ? WHERE user_id = ?",
            (clearance_level, user_id),
        )
        conn.close()
        return before > 0


# ==================================================================
# Helpers
# ==================================================================

def _hash_key(key: str) -> str:
    """Hash an API key using SHA-256."""
    return hashlib.sha256(key.encode()).hexdigest()
