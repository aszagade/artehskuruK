"""
Source-Aware Authority and Provenance
======================================

Maps knowledge sources to authority levels and tracks per-document
authority metadata. Authority is ONE SIGNAL among many — it does NOT
automatically make higher-authority evidence "true."

Authority must be combined with:
- recency (document version, last_modified)
- evidence quality (retrieval score, direct textual support)
- contradictions (conflicting evidence from different sources)
- authorization (visibility/permissions)
- provenance (source identity, content hash, timestamps)

Design principles:
- Authority NEVER overrides evidence quality
- Higher authority = more trustworthy source, not automatically correct
- User-provided knowledge never becomes authoritative
- LLM inference never becomes authoritative
- Conflicts between authority levels are surfaced, not silently resolved
- Authority is stored as metadata, not used as a ranking multiplier
  UNLESS A/B experiments prove it improves results
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

from kurukshetra.registry.database import get_connection

logger = logging.getLogger(__name__)


# ==================================================================
# Authority Levels (ordered by trust)
# ==================================================================

class AuthorityLevel(IntEnum):
    """Authority levels for knowledge sources, ordered by trust.

    Higher value = more authoritative. This ordering is used for
    comparison, NOT for automatic promotion.
    """
    UNKNOWN = 0
    INFERRED = 1        # derived from other knowledge, not directly stated
    USER_PROVIDED = 2   # from user uploads, less vetted
    OBSERVATIONAL = 3   # from monitoring/observational data
    OPERATIONAL = 4     # from operational records (cases, emails)
    OFFICIAL = 5        # from official documentation (SOPs, Knowledge articles)
    AUTHORITATIVE = 6   # highest trust (approved, verified official docs)

    @classmethod
    def from_string(cls, value: str) -> AuthorityLevel:
        """Parse a authority level string, defaulting to UNKNOWN."""
        mapping = {
            "unknown": cls.UNKNOWN,
            "user_provided": cls.USER_PROVIDED,
            "inferred": cls.INFERRED,
            "observational": cls.OBSERVATIONAL,
            "operational": cls.OPERATIONAL,
            "official": cls.OFFICIAL,
            "authoritative": cls.AUTHORITATIVE,
        }
        return mapping.get(value.strip().lower(), cls.UNKNOWN)


# ==================================================================
# Data Classes
# ==================================================================

@dataclass
class DocumentAuthority:
    """Authority metadata for a single document."""
    document_id: str
    source_id: str
    authority_level: AuthorityLevel
    authority_evidence: str = ""     # Why this authority level
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    superseded: bool = False
    conflict_status: str = "none"    # none | pending | confirmed | resolved

    def to_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "source_id": self.source_id,
            "authority_level": self.authority_level.name,
            "authority_level_value": int(self.authority_level),
            "authority_evidence": self.authority_evidence,
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
            "superseded": self.superseded,
            "conflict_status": self.conflict_status,
        }


@dataclass
class AuthorityConflict:
    """A detected conflict between documents with different authority levels."""
    conflict_id: str
    entity_or_claim: str
    doc_a_id: str
    doc_a_authority: AuthorityLevel
    doc_a_evidence: str
    doc_b_id: str
    doc_b_authority: AuthorityLevel
    doc_b_evidence: str
    description: str
    severity: str = "medium"  # low | medium | high | critical

    def to_dict(self) -> dict:
        return {
            "conflict_id": self.conflict_id,
            "entity_or_claim": self.entity_or_claim,
            "doc_a_id": self.doc_a_id,
            "doc_a_authority": self.doc_a_authority.name,
            "doc_b_id": self.doc_b_id,
            "doc_b_authority": self.doc_b_authority.name,
            "description": self.description,
            "severity": self.severity,
        }


# ==================================================================
# Schema
# ==================================================================

_CREATE_SOURCE_AUTHORITY_DEFAULTS = """
CREATE TABLE IF NOT EXISTS source_authority_defaults (
    source_id       TEXT PRIMARY KEY,
    authority_level TEXT NOT NULL DEFAULT 'operational',
    description     TEXT DEFAULT '',
    created_at      TIMESTAMP,
    updated_at      TIMESTAMP
)
"""

_CREATE_DOCUMENT_AUTHORITY = """
CREATE TABLE IF NOT EXISTS document_authority (
    document_id         TEXT PRIMARY KEY,
    source_id           TEXT NOT NULL,
    authority_level     TEXT NOT NULL DEFAULT 'operational',
    authority_evidence  TEXT DEFAULT '',
    effective_from      TIMESTAMP,
    effective_to        TIMESTAMP,
    superseded          BOOLEAN DEFAULT FALSE,
    conflict_status     TEXT DEFAULT 'none',
    created_at          TIMESTAMP,
    updated_at          TIMESTAMP
)
"""

_CREATE_AUTHORITY_CONFLICTS = """
CREATE TABLE IF NOT EXISTS authority_conflicts (
    conflict_id         TEXT PRIMARY KEY,
    entity_or_claim     TEXT NOT NULL,
    doc_a_id            TEXT NOT NULL,
    doc_a_authority     TEXT NOT NULL,
    doc_a_evidence      TEXT DEFAULT '',
    doc_b_id            TEXT NOT NULL,
    doc_b_authority     TEXT NOT NULL,
    doc_b_evidence      TEXT DEFAULT '',
    description         TEXT NOT NULL,
    severity            TEXT DEFAULT 'medium',
    detected_at         TIMESTAMP,
    resolved            BOOLEAN DEFAULT FALSE,
    resolution          TEXT DEFAULT ''
)
"""


# ==================================================================
# AuthorityStore
# ==================================================================

class AuthorityStore:
    """Manages source-level and document-level authority.

    Usage:
        store = AuthorityStore()

        # Set source defaults
        store.set_source_authority("sforce-prod", "official", "Salesforce Knowledge articles")
        store.set_source_authority("ics-upload", "operational", "User-uploaded ICS documents")

        # Record document authority during ingestion
        store.record_document_authority(
            document_id="DOC-000123",
            source_id="sforce-prod",
            authority_level="official",
            authority_evidence="Published Salesforce Knowledge article",
        )

        # Look up authority for evidence
        auth = store.get_document_authority("DOC-000123")
    """

    def __init__(self) -> None:
        self._ensure_tables()
        self._seed_defaults()

    def _ensure_tables(self) -> None:
        """Create tables if they don't exist."""
        conn = get_connection()
        try:
            conn.execute(_CREATE_SOURCE_AUTHORITY_DEFAULTS)
            conn.execute(_CREATE_DOCUMENT_AUTHORITY)
            conn.execute(_CREATE_AUTHORITY_CONFLICTS)
        finally:
            conn.close()

    def _seed_defaults(self) -> None:
        """Seed default authority levels for known source types.

        Only seeds if the table is empty (first run).
        """
        conn = get_connection()
        try:
            row = conn.execute("SELECT COUNT(*) FROM source_authority_defaults").fetchone()
            if row[0] > 0:
                return  # Already seeded

            defaults = [
                ("filesystem", "operational", "Local filesystem documents"),
                ("network_share", "operational", "Network share documents"),
                ("salesforce", "official", "Salesforce Knowledge articles and cases"),
                ("confluence", "official", "Confluence wiki documentation"),
                ("datadog", "observational", "Datadog monitoring observations"),
                ("github", "official", "GitHub repository code and documentation"),
                ("outlook", "operational", "Email communications"),
                ("teams", "operational", "Teams messages and files"),
                ("user_upload", "user_provided", "User-uploaded documents"),
                ("custom", "operational", "Custom source adapter"),
            ]

            for source_id, authority, desc in defaults:
                conn.execute(
                    """INSERT INTO source_authority_defaults
                    (source_id, authority_level, description, created_at, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
                    (source_id, authority, desc),
                )
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Source Authority Defaults
    # ------------------------------------------------------------------

    def set_source_authority(
        self,
        source_id: str,
        authority_level: str,
        description: str = "",
    ) -> None:
        """Set the default authority level for a source type."""
        from datetime import datetime
        now = datetime.utcnow().isoformat()
        conn = get_connection()
        try:
            conn.execute(
                """INSERT INTO source_authority_defaults
                (source_id, authority_level, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    authority_level = excluded.authority_level,
                    description = excluded.description,
                    updated_at = excluded.updated_at""",
                (source_id, authority_level, description, now, now),
            )
        finally:
            conn.close()

    def get_source_authority(self, source_id: str) -> AuthorityLevel:
        """Get the default authority level for a source."""
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT authority_level FROM source_authority_defaults WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        finally:
            conn.close()

        if row:
            return AuthorityLevel.from_string(row[0])
        return AuthorityLevel.UNKNOWN

    def list_source_authorities(self) -> list[dict]:
        """List all source authority defaults."""
        conn = get_connection()
        try:
            rows = conn.execute(
                """SELECT source_id, authority_level, description
                FROM source_authority_defaults ORDER BY authority_level DESC"""
            ).fetchall()
        finally:
            conn.close()

        return [
            {
                "source_id": r[0],
                "authority_level": r[1],
                "authority_level_value": int(AuthorityLevel.from_string(r[1])),
                "description": r[2] or "",
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Document Authority
    # ------------------------------------------------------------------

    def record_document_authority(
        self,
        document_id: str,
        source_id: str,
        authority_level: str,
        authority_evidence: str = "",
        effective_from: Optional[str] = None,
        effective_to: Optional[str] = None,
    ) -> DocumentAuthority:
        """Record authority metadata for a document.

        Called during ingestion when a SourceDocument flows through
        KnowledgeFabric. The authority level is determined by:
        1. Source-level default (from source_authority_defaults)
        2. Document-specific override (if provided by adapter)
        """
        from datetime import datetime
        now = datetime.utcnow().isoformat()

        conn = get_connection()
        try:
            conn.execute(
                """INSERT INTO document_authority
                (document_id, source_id, authority_level, authority_evidence,
                 effective_from, effective_to, superseded, conflict_status,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, FALSE, 'none', ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    source_id = excluded.source_id,
                    authority_level = excluded.authority_level,
                    authority_evidence = excluded.authority_evidence,
                    effective_from = excluded.effective_from,
                    effective_to = excluded.effective_to,
                    updated_at = excluded.updated_at""",
                (
                    document_id, source_id, authority_level,
                    authority_evidence, effective_from, effective_to,
                    now, now,
                ),
            )
        finally:
            conn.close()

        return DocumentAuthority(
            document_id=document_id,
            source_id=source_id,
            authority_level=AuthorityLevel.from_string(authority_level),
            authority_evidence=authority_evidence,
            effective_from=effective_from,
            effective_to=effective_to,
        )

    def get_document_authority(self, document_id: str) -> Optional[DocumentAuthority]:
        """Get authority metadata for a document."""
        conn = get_connection()
        try:
            row = conn.execute(
                """SELECT document_id, source_id, authority_level,
                    authority_evidence, effective_from, effective_to,
                    superseded, conflict_status
                FROM document_authority WHERE document_id = ?""",
                (document_id,),
            ).fetchone()
        finally:
            conn.close()

        if not row:
            return None

        return DocumentAuthority(
            document_id=row[0],
            source_id=row[1],
            authority_level=AuthorityLevel.from_string(row[2]),
            authority_evidence=row[3] or "",
            effective_from=row[4],
            effective_to=row[5],
            superseded=bool(row[6]),
            conflict_status=row[7] or "none",
        )

    def get_authority_for_documents(self, document_ids: list[str]) -> dict[str, DocumentAuthority]:
        """Batch lookup authority for multiple documents."""
        if not document_ids:
            return {}

        conn = get_connection()
        try:
            placeholders = ",".join("?" * len(document_ids))
            rows = conn.execute(
                f"""SELECT document_id, source_id, authority_level,
                    authority_evidence, effective_from, effective_to,
                    superseded, conflict_status
                FROM document_authority WHERE document_id IN ({placeholders})""",
                document_ids,
            ).fetchall()
        finally:
            conn.close()

        return {
            r[0]: DocumentAuthority(
                document_id=r[0],
                source_id=r[1],
                authority_level=AuthorityLevel.from_string(r[2]),
                authority_evidence=r[3] or "",
                effective_from=r[4],
                effective_to=r[5],
                superseded=bool(r[6]),
                conflict_status=r[7] or "none",
            )
            for r in rows
        }

    def get_documents_by_authority(
        self, authority_level: str
    ) -> list[DocumentAuthority]:
        """Get all documents with a specific authority level."""
        conn = get_connection()
        try:
            rows = conn.execute(
                """SELECT document_id, source_id, authority_level,
                    authority_evidence, effective_from, effective_to,
                    superseded, conflict_status
                FROM document_authority WHERE authority_level = ?
                ORDER BY document_id""",
                (authority_level,),
            ).fetchall()
        finally:
            conn.close()

        return [
            DocumentAuthority(
                document_id=r[0], source_id=r[1],
                authority_level=AuthorityLevel.from_string(r[2]),
                authority_evidence=r[3] or "",
                effective_from=r[4], effective_to=r[5],
                superseded=bool(r[6]), conflict_status=r[7] or "none",
            )
            for r in rows
        ]

    def count_by_authority(self) -> dict[str, int]:
        """Count documents by authority level."""
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT authority_level, COUNT(*) FROM document_authority GROUP BY authority_level"
            ).fetchall()
        finally:
            conn.close()

        return {r[0]: r[1] for r in rows}

    # ------------------------------------------------------------------
    # Conflict Detection
    # ------------------------------------------------------------------

    def detect_authority_conflicts(
        self, entity_name: str, evidence_docs: list[str]
    ) -> list[AuthorityConflict]:
        """Detect conflicts between documents with different authority levels.

        When evidence from multiple documents references the same entity
        but the documents have different authority levels, this surfaces
        the conflict rather than silently choosing one.

        Returns conflicts sorted by severity (highest first).
        """
        if len(evidence_docs) < 2:
            return []

        # Get authority for all evidence documents
        authorities = self.get_authority_for_documents(evidence_docs)
        if len(authorities) < 2:
            return []

        conflicts = []
        doc_ids = list(authorities.keys())

        for i in range(len(doc_ids)):
            for j in range(i + 1, len(doc_ids)):
                a = authorities[doc_ids[i]]
                b = authorities[doc_ids[j]]

                # Only flag conflict if authority levels differ significantly
                if abs(a.authority_level - b.authority_level) < 2:
                    continue

                # Determine severity
                diff = abs(a.authority_level - b.authority_level)
                if diff >= 4:
                    severity = "critical"
                elif diff >= 3:
                    severity = "high"
                elif diff >= 2:
                    severity = "medium"
                else:
                    severity = "low"

                # Higher-authority doc provides evidence
                if a.authority_level > b.authority_level:
                    higher, lower = a, b
                else:
                    higher, lower = b, a

                conflict_id = f"AUTH-CONFLICT-{entity_name[:20]}-{doc_ids[i]}-{doc_ids[j]}"

                description = (
                    f"Different authority levels for entity '{entity_name}': "
                    f"{higher.source_id} ({higher.authority_level.name}) "
                    f"vs {lower.source_id} ({lower.authority_level.name})"
                )

                conflict = AuthorityConflict(
                    conflict_id=conflict_id,
                    entity_or_claim=entity_name,
                    doc_a_id=doc_ids[i],
                    doc_a_authority=a.authority_level,
                    doc_a_evidence=a.authority_evidence,
                    doc_b_id=doc_ids[j],
                    doc_b_authority=b.authority_level,
                    doc_b_evidence=b.authority_evidence,
                    description=description,
                    severity=severity,
                )
                conflicts.append(conflict)

        # Sort by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        conflicts.sort(key=lambda c: severity_order.get(c.severity, 99))

        return conflicts

    def format_conflict_for_answer(
        self, conflict: AuthorityConflict
    ) -> str:
        """Format an authority conflict as a human-readable string for answers.

        This is used by the answer layer to surface conflicts rather than
        silently choosing one source.
        """
        higher_auth = max(conflict.doc_a_authority, conflict.doc_b_authority)
        lower_auth = min(conflict.doc_a_authority, conflict.doc_b_authority)

        if conflict.doc_a_authority == higher_auth:
            higher_id = conflict.doc_a_id
            lower_id = conflict.doc_b_id
        else:
            higher_id = conflict.doc_b_id
            lower_id = conflict.doc_a_id

        return (
            f"⚠️ Conflicting evidence detected for '{conflict.entity_or_claim}': "
            f"Higher-authority source ({higher_id}, {higher_auth.name}) "
            f"vs lower-authority source ({lower_id}, {lower_auth.name}). "
            f"The documented process may differ from observed practice."
        )

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Remove all authority data. USE WITH CAUTION."""
        conn = get_connection()
        try:
            conn.execute("DELETE FROM authority_conflicts")
            conn.execute("DELETE FROM document_authority")
            conn.execute("DELETE FROM source_authority_defaults")
        finally:
            conn.close()
