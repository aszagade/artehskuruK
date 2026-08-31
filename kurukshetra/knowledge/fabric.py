"""
Knowledge Fabric — Continuous Knowledge Maintenance
====================================================

Automatically detects new/changed/removed documents, ingests them
incrementally, tracks multi-team concepts, detects conflicts, and
maintains a machine-readable knowledge state for SANJAYA.

Design principles:
- Reuses existing IngestionPipeline (no duplication)
- SHA-256 fingerprinting for change detection
- Document state tracking in DuckDB
- Multi-team concept association
- Version history with conflict detection
- Provenance preserved at every stage
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from kurukshetra.identity import generate_sha256
from kurukshetra.registry.database import get_connection


# ==================================================================
# Enums
# ==================================================================

class DocumentState(Enum):
    """Document lifecycle states in the knowledge fabric."""
    NEW = "new"
    REGISTERED = "registered"
    INDEXED = "indexed"
    CHANGED = "changed"
    REMOVED = "removed"
    CONFLICT = "conflict"
    STALE = "stale"


class ChangeType(Enum):
    """Types of document changes detected."""
    NONE = "none"
    NEW_FILE = "new_file"
    CONTENT_CHANGED = "content_changed"
    METADATA_CHANGED = "metadata_changed"
    RENAMED = "renamed"
    REMOVED = "removed"


class ConflictType(Enum):
    """Types of knowledge conflicts."""
    TEAM_MISMATCH = "team_mismatch"
    VERSION_CONFLICT = "version_conflict"
    CONTENT_CONTRADICTION = "content_contradiction"
    ENTITY_CONTRADICTION = "entity_contradiction"


# ==================================================================
# Data classes
# ==================================================================

@dataclass(slots=True)
class DocumentFingerprint:
    """Fingerprint of a document for change detection."""
    document_id: str
    source_path: str
    sha256: str
    file_size: int
    last_modified: Optional[datetime]
    last_ingested: Optional[datetime]
    state: DocumentState
    version: str
    team_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ChangeDetection:
    """Result of change detection for a document."""
    change_type: ChangeType
    document_id: str
    source_path: str
    old_sha256: Optional[str] = None
    new_sha256: Optional[str] = None
    details: str = ""


@dataclass(slots=True)
class ConceptTeamAssociation:
    """Multi-team association for a concept/entity."""
    concept_name: str
    concept_type: str  # "entity", "system", "process", etc.
    team_id: str
    association_type: str  # "owner", "user", "supporting", "affected"
    confidence: float
    source_document_id: str
    first_seen: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class VersionRecord:
    """A version record for a document."""
    document_id: str
    version: str
    sha256: str
    ingested_at: datetime
    source_path: str
    chunks_count: int = 0
    is_current: bool = True


@dataclass(slots=True)
class ConflictRecord:
    """A detected knowledge conflict."""
    conflict_id: str
    conflict_type: ConflictType
    entity_name: str
    source_a: str  # document_id
    source_b: str  # document_id
    description: str
    detected_at: datetime = field(default_factory=datetime.utcnow)
    resolved: bool = False
    resolution: str = ""


@dataclass(slots=True)
class FabricScanResult:
    """Result of scanning a source directory."""
    source_path: str
    scan_time: float
    files_found: int
    new_files: int
    changed_files: int
    unchanged_files: int
    removed_files: int
    errors: list[str] = field(default_factory=list)
    changes: list[ChangeDetection] = field(default_factory=list)


@dataclass(slots=True)
class FabricIngestResult:
    """Result of incremental ingestion."""
    document_id: str
    source_path: str
    change_type: ChangeType
    title: str = ""
    chunks_stored: int = 0
    entities_extracted: int = 0
    relationships_extracted: int = 0
    unknown_terms: int = 0
    teams_detected: list[str] = field(default_factory=list)
    concepts_added: int = 0
    conflicts_detected: int = 0
    version: str = "1.0.0"
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    stages: dict = field(default_factory=dict)


@dataclass(slots=True)
class KnowledgeState:
    """Machine-readable knowledge state for SANJAYA Brain."""
    total_documents: int
    total_chunks: int
    total_entities: int
    total_relationships: int
    total_evidence: int
    total_glossary_terms: int
    total_unknown_terms: int
    total_concepts: int
    total_conflicts: int
    total_versions: int
    teams_represented: list[str]
    documents_by_state: dict[str, int]
    documents_by_team: dict[str, int]
    recent_changes: list[dict]
    active_conflicts: list[dict]
    last_scan_time: Optional[str]
    freshness_summary: dict[str, int]


# ==================================================================
# Knowledge Fabric Service
# ==================================================================

class KnowledgeFabric:
    """
    Continuous knowledge maintenance layer.

    Detects new/changed documents, manages incremental ingestion,
    tracks multi-team concepts, and maintains knowledge state.
    """

    def __init__(self) -> None:
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Create knowledge fabric tables if they don't exist."""
        conn = get_connection()

        # Drop and recreate fabric-specific tables if they have wrong schema
        # (these tables are internal to the fabric, not production data)
        for table in ['document_state', 'document_versions', 'concept_teams',
                       'knowledge_conflicts', 'fabric_scans']:
            try:
                cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
                # Check if table has 'id INTEGER PRIMARY KEY' (old schema)
                has_id_pk = any(
                    c[1] == 'id' and c[5] == True  # pk flag
                    for c in cols
                )
                if has_id_pk and table in ('concept_teams', 'document_versions', 'fabric_scans'):
                    conn.execute(f"DROP TABLE IF EXISTS {table}")
            except Exception:
                pass

        # Document state tracking
        conn.execute("""
            CREATE TABLE IF NOT EXISTS document_state (
                document_id TEXT PRIMARY KEY,
                source_path TEXT,
                sha256 TEXT,
                file_size INTEGER,
                last_modified TIMESTAMP,
                last_ingested TIMESTAMP,
                state TEXT DEFAULT 'new',
                version TEXT DEFAULT '1.0.0',
                team_ids TEXT DEFAULT '[]'
            )
        """)

        # Document version history
        conn.execute("""
            CREATE TABLE IF NOT EXISTS document_versions (
                document_id TEXT,
                version TEXT,
                sha256 TEXT,
                ingested_at TIMESTAMP,
                source_path TEXT,
                chunks_count INTEGER DEFAULT 0,
                is_current BOOLEAN DEFAULT TRUE
            )
        """)

        # Multi-team concept associations
        conn.execute("""
            CREATE TABLE IF NOT EXISTS concept_teams (
                concept_name TEXT,
                concept_type TEXT,
                team_id TEXT,
                association_type TEXT,
                confidence REAL,
                source_document_id TEXT,
                first_seen TIMESTAMP,
                last_seen TIMESTAMP,
                PRIMARY KEY (concept_name, team_id)
            )
        """)

        # Knowledge conflicts
        conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_conflicts (
                conflict_id TEXT PRIMARY KEY,
                conflict_type TEXT,
                entity_name TEXT,
                source_a TEXT,
                source_b TEXT,
                description TEXT,
                detected_at TIMESTAMP,
                resolved BOOLEAN DEFAULT FALSE,
                resolution TEXT DEFAULT ''
            )
        """)

        # Fabric scan history
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fabric_scans (
                source_path TEXT,
                scan_time TIMESTAMP,
                files_found INTEGER,
                new_files INTEGER,
                changed_files INTEGER,
                unchanged_files INTEGER,
                removed_files INTEGER
            )
        """)

        conn.close()

    # ------------------------------------------------------------------
    # Change Detection
    # ------------------------------------------------------------------

    def scan_source(self, source_path: str) -> FabricScanResult:
        """
        Scan a source directory for new/changed/removed documents.

        Returns FabricScanResult with detected changes.
        """
        start = time.time()
        source = Path(source_path)

        if not source.exists():
            return FabricScanResult(
                source_path=source_path, scan_time=0,
                files_found=0, new_files=0, changed_files=0,
                unchanged_files=0, removed_files=0,
                errors=[f"Source path does not exist: {source_path}"],
            )

        # Get supported extensions
        from kurukshetra.extractors.text_extractor import TextExtractor
        supported = TextExtractor.supported_extensions()

        # Scan files
        files_found = []
        for f in source.rglob("*"):
            if f.is_file() and f.suffix.lower() in supported:
                files_found.append(f)

        # Get existing state
        conn = get_connection()
        existing = {}
        rows = conn.execute(
            "SELECT source_path, document_id, sha256, state FROM document_state"
        ).fetchall()
        for r in rows:
            existing[r[0]] = {"document_id": r[1], "sha256": r[2], "state": r[3]}

        # Detect changes
        changes = []
        new_count = 0
        changed_count = 0
        unchanged_count = 0
        seen_paths = set()

        for f in files_found:
            path_str = str(f)
            seen_paths.add(path_str)

            if path_str in existing:
                # Check if content changed
                new_sha = generate_sha256(f)
                old_sha = existing[path_str]["sha256"]

                if new_sha != old_sha:
                    changes.append(ChangeDetection(
                        change_type=ChangeType.CONTENT_CHANGED,
                        document_id=existing[path_str]["document_id"],
                        source_path=path_str,
                        old_sha256=old_sha,
                        new_sha256=new_sha,
                        details=f"Content changed: {old_sha[:16]}... -> {new_sha[:16]}...",
                    ))
                    changed_count += 1
                else:
                    unchanged_count += 1
            else:
                # New file
                changes.append(ChangeDetection(
                    change_type=ChangeType.NEW_FILE,
                    document_id="",
                    source_path=path_str,
                    new_sha256=generate_sha256(f),
                    details=f"New file: {f.name}",
                ))
                new_count += 1

        # Detect removed files
        removed_count = 0
        for path_str, info in existing.items():
            if path_str not in seen_paths and Path(path_str).parent == source:
                changes.append(ChangeDetection(
                    change_type=ChangeType.REMOVED,
                    document_id=info["document_id"],
                    source_path=path_str,
                    details=f"File removed from source",
                ))
                removed_count += 1

        scan_time = time.time() - start

        # Record scan
        conn.execute(
            """INSERT INTO fabric_scans
            (source_path, scan_time, files_found, new_files, changed_files,
             unchanged_files, removed_files)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (source_path, datetime.utcnow(), len(files_found),
             new_count, changed_count, unchanged_count, removed_count),
        )
        conn.close()

        return FabricScanResult(
            source_path=source_path,
            scan_time=round(scan_time, 3),
            files_found=len(files_found),
            new_files=new_count,
            changed_files=changed_count,
            unchanged_files=unchanged_count,
            removed_files=removed_count,
            changes=changes,
        )

    # ------------------------------------------------------------------
    # Incremental Ingestion
    # ------------------------------------------------------------------

    def ingest_change(
        self, change: ChangeDetection, pipeline=None
    ) -> FabricIngestResult:
        """
        Ingest a single detected change through the canonical pipeline.

        For NEW_FILE: full ingestion.
        For CONTENT_CHANGED: re-ingest (replace chunks, update state).
        For REMOVED: mark as removed.
        """
        start = time.time()
        source_path = Path(change.source_path)

        if change.change_type == ChangeType.REMOVED:
            return self._handle_removed(change)

        if change.change_type == ChangeType.NEW_FILE:
            return self._handle_new_file(source_path, pipeline)

        if change.change_type == ChangeType.CONTENT_CHANGED:
            return self._handle_changed(source_path, change, pipeline)

        # UNCHANGED — skip
        return FabricIngestResult(
            document_id=change.document_id,
            source_path=change.source_path,
            change_type=ChangeType.NONE,
        )

    def _handle_new_file(
        self, source_path: Path, pipeline=None
    ) -> FabricIngestResult:
        """Handle a new file: full ingestion."""
        start = time.time()
        if pipeline is None:
            from kurukshetra.pipeline.ingest import IngestionPipeline
            pipeline = IngestionPipeline(use_semantic_chunking=False)

        try:
            result = pipeline.ingest(source_path)
        except Exception as e:
            return FabricIngestResult(
                document_id="", source_path=str(source_path),
                change_type=ChangeType.NEW_FILE, error=str(e),
                execution_time_ms=round((time.time() - start) * 1000, 1),
            )

        # Update document state
        sha256 = generate_sha256(source_path)
        state = DocumentState.INDEXED if not result.error else DocumentState.CONFLICT

        conn = get_connection()
        conn.execute(
            """INSERT OR REPLACE INTO document_state
            (document_id, source_path, sha256, file_size, last_modified,
             last_ingested, state, version, team_ids)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.document_id, str(source_path), sha256,
                source_path.stat().st_size if source_path.exists() else 0,
                datetime.fromtimestamp(source_path.stat().st_mtime) if source_path.exists() else None,
                datetime.utcnow(), state.value, "1.0.0",
                f'["{result.team_id}"]',
            ),
        )

        # Record version
        conn.execute(
            """INSERT INTO document_versions
            (document_id, version, sha256, ingested_at, source_path, chunks_count, is_current)
            VALUES (?, ?, ?, ?, ?, ?, TRUE)""",
            (result.document_id, "1.0.0", sha256, datetime.utcnow(),
             str(source_path), result.chunks_stored),
        )
        conn.close()

        # Track multi-team concepts from graph entities
        self._track_concepts(result.document_id, result.team_id, result.entities_extracted > 0)

        return FabricIngestResult(
            document_id=result.document_id,
            source_path=str(source_path),
            change_type=ChangeType.NEW_FILE,
            title=result.title or source_path.stem,
            chunks_stored=result.chunks_stored,
            entities_extracted=result.entities_extracted,
            relationships_extracted=result.relationships_extracted,
            unknown_terms=result.unknown_terms,
            teams_detected=[result.team_id] if result.team_id != "unknown" else [],
            version="1.0.0",
            error=result.error,
            stages=result.stages,
            execution_time_ms=round((time.time() - start) * 1000, 1),
        )

    def _handle_changed(
        self, source_path: Path, change: ChangeDetection, pipeline=None
    ) -> FabricIngestResult:
        """Handle a changed file: re-ingest, update version."""
        start = time.time()
        if pipeline is None:
            from kurukshetra.pipeline.ingest import IngestionPipeline
            pipeline = IngestionPipeline(use_semantic_chunking=False)

        document_id = change.document_id

        # Remove old chunks for this document
        conn = get_connection()
        try:
            conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
        except Exception:
            pass

        # Re-ingest
        try:
            result = pipeline.ingest(source_path)
        except Exception as e:
            conn.close()
            return FabricIngestResult(
                document_id=document_id, source_path=str(source_path),
                change_type=ChangeType.CONTENT_CHANGED, error=str(e),
                execution_time_ms=round((time.time() - start) * 1000, 1),
            )

        # Update state
        new_sha = generate_sha256(source_path)
        new_version = _bump_version(
            conn.execute("SELECT version FROM document_state WHERE document_id = ?",
                         (document_id,)).fetchone()
        )

        conn.execute(
            """UPDATE document_state SET
            sha256 = ?, last_ingested = ?, state = ?, version = ?, team_ids = ?
            WHERE document_id = ?""",
            (new_sha, datetime.utcnow(), DocumentState.INDEXED.value,
             new_version, f'["{result.team_id}"]', document_id),
        )

        # Record new version
        conn.execute(
            """UPDATE document_versions SET is_current = FALSE
            WHERE document_id = ? AND is_current = TRUE""",
            (document_id,),
        )
        conn.execute(
            """INSERT INTO document_versions
            (document_id, version, sha256, ingested_at, source_path, chunks_count, is_current)
            VALUES (?, ?, ?, ?, ?, ?, TRUE)""",
            (document_id, new_version, new_sha, datetime.utcnow(),
             str(source_path), result.chunks_stored),
        )
        conn.close()

        self._track_concepts(document_id, result.team_id, result.entities_extracted > 0)

        return FabricIngestResult(
            document_id=document_id,
            source_path=str(source_path),
            change_type=ChangeType.CONTENT_CHANGED,
            title=result.title or source_path.stem,
            chunks_stored=result.chunks_stored,
            entities_extracted=result.entities_extracted,
            relationships_extracted=result.relationships_extracted,
            unknown_terms=result.unknown_terms,
            teams_detected=[result.team_id] if result.team_id != "unknown" else [],
            version=new_version,
            error=result.error,
            stages=result.stages,
            execution_time_ms=round((time.time() - start) * 1000, 1),
        )

    def _handle_removed(self, change: ChangeDetection) -> FabricIngestResult:
        """Handle a removed file: mark state as removed, delete chunks."""
        conn = get_connection()

        # Delete chunks so they are no longer retrieved
        try:
            conn.execute(
                "DELETE FROM chunks WHERE document_id = ?",
                (change.document_id,),
            )
        except Exception:
            pass

        # Delete vectors for this document
        try:
            chunk_ids = conn.execute(
                "SELECT chunk_id FROM chunks WHERE document_id = ?",
                (change.document_id,),
            ).fetchall()
            if chunk_ids:
                ids = [r[0] for r in chunk_ids]
                placeholders = ",".join("?" * len(ids))
                conn.execute(
                    f"DELETE FROM vectors WHERE chunk_id IN ({placeholders})",
                    ids,
                )
        except Exception:
            pass

        # Update document state
        conn.execute(
            "UPDATE document_state SET state = ? WHERE document_id = ?",
            (DocumentState.REMOVED.value, change.document_id),
        )
        conn.execute(
            "UPDATE document_versions SET is_current = FALSE WHERE document_id = ?",
            (change.document_id,),
        )
        conn.close()

        return FabricIngestResult(
            document_id=change.document_id,
            source_path=change.source_path,
            change_type=ChangeType.REMOVED,
        )

    # ------------------------------------------------------------------
    # Multi-Team Concept Tracking
    # ------------------------------------------------------------------

    def _track_concepts(
        self, document_id: str, team_id: str, has_entities: bool
    ) -> None:
        """Track multi-team concept associations from ingested document."""
        if not has_entities or team_id == "unknown":
            return

        conn = get_connection()

        # Get entities linked to this document via graph_evidence
        try:
            rows = conn.execute(
                """SELECT DISTINCT ge.name, ge.entity_type
                FROM graph_evidence gev
                LEFT JOIN graph_entities ge ON gev.entity_id = ge.id
                WHERE gev.source_document = ?
                  AND gev.entity_id IS NOT NULL
                  AND ge.name IS NOT NULL AND ge.name != ''""",
                (document_id,),
            ).fetchall()

            for entity_name, entity_type in rows:
                entity_type = entity_type or "unknown"
                entity_name = entity_name.lower().strip()

                # Check if concept already has this team association
                existing = conn.execute(
                    """SELECT concept_name FROM concept_teams
                    WHERE concept_name = ? AND team_id = ?""",
                    (entity_name, team_id),
                ).fetchone()

                if existing:
                    # Update last_seen
                    conn.execute(
                        """UPDATE concept_teams SET last_seen = ?
                        WHERE concept_name = ? AND team_id = ?""",
                        (datetime.utcnow(), entity_name, team_id),
                    )
                else:
                    # New team association
                    conn.execute(
                        """INSERT INTO concept_teams
                        (concept_name, concept_type, team_id, association_type,
                         confidence, source_document_id, first_seen, last_seen)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (entity_name, entity_type, team_id, "associated",
                         0.5, document_id, datetime.utcnow(), datetime.utcnow()),
                    )
        except Exception:
            pass  # Graph tables may not exist yet

        conn.close()

    def add_concept_team(
        self, concept_name: str, concept_type: str, team_id: str,
        association_type: str, confidence: float, source_document_id: str,
    ) -> None:
        """Explicitly add a team association for a concept."""
        conn = get_connection()
        existing = conn.execute(
            """SELECT confidence FROM concept_teams
            WHERE concept_name = ? AND team_id = ?""",
            (concept_name, team_id),
        ).fetchone()

        if existing:
            # Update if new confidence is higher
            if confidence > existing[0]:
                conn.execute(
                    """UPDATE concept_teams SET confidence = ?, last_seen = ?
                    WHERE concept_name = ? AND team_id = ?""",
                    (confidence, datetime.utcnow(), concept_name, team_id),
                )
        else:
            conn.execute(
                """INSERT INTO concept_teams
                (concept_name, concept_type, team_id, association_type,
                 confidence, source_document_id, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (concept_name, concept_type, team_id, association_type,
                 confidence, source_document_id, datetime.utcnow(), datetime.utcnow()),
            )
        conn.close()

    def get_concept_teams(self, concept_name: str) -> list[dict]:
        """Get all team associations for a concept."""
        conn = get_connection()
        rows = conn.execute(
            """SELECT concept_name, concept_type, team_id, association_type,
            confidence, source_document_id, first_seen, last_seen
            FROM concept_teams WHERE concept_name = ?""",
            (concept_name,),
        ).fetchall()
        conn.close()
        return [
            {"concept_name": r[0], "concept_type": r[1], "team_id": r[2],
             "association_type": r[3], "confidence": r[4],
             "source_document_id": r[5], "first_seen": str(r[6]),
             "last_seen": str(r[7])}
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Conflict Detection
    # ------------------------------------------------------------------

    def detect_conflicts(self, entity_name: str) -> list[ConflictRecord]:
        """Detect conflicts for an entity across multiple sources."""
        conn = get_connection()

        # Check team mismatches
        teams = conn.execute(
            """SELECT DISTINCT team_id, source_document_id
            FROM concept_teams WHERE concept_name = ?""",
            (entity_name,),
        ).fetchall()

        conflicts = []
        if len(set(t[0] for t in teams)) > 1:
            team_list = list(set(t[0] for t in teams))
            for i in range(len(team_list)):
                for j in range(i + 1, len(team_list)):
                    conflict_id = f"CONFLICT-{entity_name[:20]}-{team_list[i]}-{team_list[j]}"
                    existing = conn.execute(
                        "SELECT conflict_id FROM knowledge_conflicts WHERE conflict_id = ?",
                        (conflict_id,),
                    ).fetchone()
                    if not existing:
                        conn.execute(
                            """INSERT INTO knowledge_conflicts
                            (conflict_id, conflict_type, entity_name, source_a, source_b,
                             description, detected_at, resolved)
                            VALUES (?, ?, ?, ?, ?, ?, ?, FALSE)""",
                            (conflict_id, ConflictType.TEAM_MISMATCH.value,
                             entity_name, team_list[i], team_list[j],
                             f"Entity '{entity_name}' associated with teams {team_list[i]} and {team_list[j]}",
                             datetime.utcnow()),
                        )
                    conflicts.append(ConflictRecord(
                        conflict_id=conflict_id,
                        conflict_type=ConflictType.TEAM_MISMATCH,
                        entity_name=entity_name,
                        source_a=team_list[i],
                        source_b=team_list[j],
                        description=f"Associated with teams {team_list[i]} and {team_list[j]}",
                    ))

        conn.close()
        return conflicts

    # ------------------------------------------------------------------
    # Knowledge State
    # ------------------------------------------------------------------

    def get_knowledge_state(self) -> KnowledgeState:
        """Get the machine-readable knowledge state for SANJAYA Brain."""
        conn = get_connection()

        total_docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        total_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

        try:
            total_entities = conn.execute("SELECT COUNT(*) FROM graph_entities").fetchone()[0]
        except Exception:
            total_entities = 0
        try:
            total_rels = conn.execute("SELECT COUNT(*) FROM graph_relationships").fetchone()[0]
        except Exception:
            total_rels = 0
        try:
            total_evidence = conn.execute("SELECT COUNT(*) FROM graph_evidence").fetchone()[0]
        except Exception:
            total_evidence = 0
        try:
            total_glossary = conn.execute("SELECT COUNT(*) FROM glossary").fetchone()[0]
        except Exception:
            total_glossary = 0
        try:
            total_unknown = conn.execute(
                "SELECT COUNT(*) FROM unknown_terms WHERE status = 'pending'"
            ).fetchone()[0]
        except Exception:
            total_unknown = 0

        try:
            total_concepts = conn.execute(
                "SELECT COUNT(DISTINCT concept_name) FROM concept_teams"
            ).fetchone()[0]
        except Exception:
            total_concepts = 0
        try:
            total_conflicts = conn.execute(
                "SELECT COUNT(*) FROM knowledge_conflicts WHERE resolved = FALSE"
            ).fetchone()[0]
        except Exception:
            total_conflicts = 0
        try:
            total_versions = conn.execute(
                "SELECT COUNT(*) FROM document_versions"
            ).fetchone()[0]
        except Exception:
            total_versions = 0

        # Teams represented
        try:
            team_rows = conn.execute(
                "SELECT DISTINCT team_id FROM concept_teams WHERE team_id != 'unknown'"
            ).fetchall()
            teams = [r[0] for r in team_rows]
        except Exception:
            teams = []

        # Documents by state
        try:
            state_rows = conn.execute(
                "SELECT state, COUNT(*) FROM document_state GROUP BY state"
            ).fetchall()
            docs_by_state = {r[0]: r[1] for r in state_rows}
        except Exception:
            docs_by_state = {}

        # Documents by team
        try:
            team_doc_rows = conn.execute(
                """SELECT team_owner, COUNT(*) FROM documents
                WHERE team_owner != 'UNKNOWN' GROUP BY team_owner"""
            ).fetchall()
            docs_by_team = {r[0]: r[1] for r in team_doc_rows}
        except Exception:
            docs_by_team = {}

        # Recent changes
        try:
            recent = conn.execute(
                """SELECT document_id, state, last_ingested, source_path
                FROM document_state ORDER BY last_ingested DESC LIMIT 10"""
            ).fetchall()
            recent_changes = [
                {"document_id": r[0], "state": r[1], "last_ingested": str(r[2]),
                 "source_path": r[3][:60] if r[3] else ""}
                for r in recent
            ]
        except Exception:
            recent_changes = []

        # Active conflicts
        try:
            conflict_rows = conn.execute(
                """SELECT conflict_id, conflict_type, entity_name, description
                FROM knowledge_conflicts WHERE resolved = FALSE LIMIT 10"""
            ).fetchall()
            active_conflicts = [
                {"conflict_id": r[0], "type": r[1], "entity": r[2], "description": r[3]}
                for r in conflict_rows
            ]
        except Exception:
            active_conflicts = []

        # Last scan time
        try:
            last_scan = conn.execute(
                "SELECT scan_time FROM fabric_scans ORDER BY scan_time DESC LIMIT 1"
            ).fetchone()
            last_scan_time = str(last_scan[0]) if last_scan else None
        except Exception:
            last_scan_time = None

        # Freshness summary
        try:
            fresh_rows = conn.execute(
                """SELECT state, COUNT(*) FROM document_state GROUP BY state"""
            ).fetchall()
            freshness = {r[0]: r[1] for r in fresh_rows}
        except Exception:
            freshness = {}

        conn.close()

        return KnowledgeState(
            total_documents=total_docs,
            total_chunks=total_chunks,
            total_entities=total_entities,
            total_relationships=total_rels,
            total_evidence=total_evidence,
            total_glossary_terms=total_glossary,
            total_unknown_terms=total_unknown,
            total_concepts=total_concepts,
            total_conflicts=total_conflicts,
            total_versions=total_versions,
            teams_represented=teams,
            documents_by_state=docs_by_state,
            documents_by_team=docs_by_team,
            recent_changes=recent_changes,
            active_conflicts=active_conflicts,
            last_scan_time=last_scan_time,
            freshness_summary=freshness,
        )

    def get_document_history(self, document_id: str) -> list[dict]:
        """Get version history for a document."""
        conn = get_connection()
        rows = conn.execute(
            """SELECT version, sha256, ingested_at, source_path, chunks_count, is_current
            FROM document_versions WHERE document_id = ?
            ORDER BY ingested_at DESC""",
            (document_id,),
        ).fetchall()
        conn.close()
        return [
            {"version": r[0], "sha256": r[1][:16] if r[1] else "",
             "ingested_at": str(r[2]), "source_path": r[3],
             "chunks_count": r[4], "is_current": bool(r[5])}
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Source Adapter Integration
    # ------------------------------------------------------------------

    def ingest_source_document(
        self, source_doc, pipeline=None
    ) -> FabricIngestResult:
        """
        Ingest a SourceDocument from any source adapter.

        This bridges the adapter contract to the canonical ingestion pipeline.
        SourceDocuments carry their own text content, so extraction is bypassed.

        Args:
            source_doc: SourceDocument from any adapter
            pipeline: Optional IngestionPipeline instance

        Returns:
            FabricIngestResult with ingestion details
        """
        import time as _time
        start = _time.time()

        # Handle deleted documents — route to removal path
        if source_doc.status == "deleted":
            external_id = source_doc.provenance.external_id
            if external_id:
                # Find existing document by external_id in source_path
                conn = get_connection()
                row = conn.execute(
                    "SELECT document_id FROM document_state WHERE source_path LIKE ?",
                    (f"%{external_id}%",),
                ).fetchone()
                conn.close()
                if row:
                    change = ChangeDetection(
                        change_type=ChangeType.REMOVED,
                        document_id=row[0],
                        source_path=source_doc.provenance.source_path,
                        details=f"Deleted by source adapter: {external_id}",
                    )
                    return self._handle_removed(change)
            return FabricIngestResult(
                document_id="", source_path=source_doc.provenance.source_path,
                change_type=ChangeType.REMOVED,
            )

        # Check deduplication via content hash
        content_hash = source_doc.provenance.content_hash
        conn = get_connection()
        existing = conn.execute(
            "SELECT document_id FROM document_state WHERE sha256 = ?",
            (content_hash,),
        ).fetchone()
        conn.close()

        if existing:
            return FabricIngestResult(
                document_id=existing[0],
                source_path=source_doc.provenance.source_path,
                change_type=ChangeType.NONE,
            )

        # Write content to a temporary file for the existing pipeline
        import tempfile
        from pathlib import Path

        suffix = ".md" if source_doc.format_hint in ("markdown", "md") else ".txt"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=suffix, delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(source_doc.text_content)
            tmp_path = Path(tmp.name)

        try:
            if pipeline is None:
                from kurukshetra.pipeline.ingest import IngestionPipeline
                pipeline = IngestionPipeline(use_semantic_chunking=False)

            result = pipeline.ingest(tmp_path)

            # Update document metadata with adapter-provided information
            if result.document_id:
                conn = get_connection()
                try:
                    # Update team info from adapter
                    team_ids = source_doc.team_ids or ["unknown"]
                    primary_team = team_ids[0] if team_ids else "unknown"

                    conn.execute(
                        """UPDATE documents SET
                        team_owner = ?,
                        visibility = ?,
                        source_path = ?
                        WHERE document_id = ?""",
                        (
                            primary_team.upper(),
                            source_doc.visibility,
                            source_doc.provenance.source_path,
                            result.document_id,
                        ),
                    )

                    # Update document state in fabric
                    conn.execute(
                        """INSERT OR REPLACE INTO document_state
                        (document_id, source_path, sha256, file_size, last_modified,
                         last_ingested, state, version, team_ids)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            result.document_id,
                            source_doc.provenance.source_path,
                            content_hash,
                            len(source_doc.text_content),
                            source_doc.provenance.last_modified_at,
                            datetime.utcnow(),
                            DocumentState.INDEXED.value,
                            "1.0.0",
                            f"{team_ids}",
                        ),
                    )

                    # Record version
                    conn.execute(
                        """INSERT INTO document_versions
                        (document_id, version, sha256, ingested_at, source_path,
                         chunks_count, is_current)
                        VALUES (?, ?, ?, ?, ?, ?, TRUE)""",
                        (
                            result.document_id, "1.0.0", content_hash,
                            datetime.utcnow(),
                            source_doc.provenance.source_path,
                            result.chunks_stored,
                        ),
                    )

                    # Track concepts
                    self._track_concepts(
                        result.document_id, primary_team,
                        result.entities_extracted > 0,
                    )
                finally:
                    conn.close()

            return FabricIngestResult(
                document_id=result.document_id,
                source_path=source_doc.provenance.source_path,
                change_type=ChangeType.NEW_FILE,
                chunks_stored=result.chunks_stored,
                entities_extracted=result.entities_extracted,
                relationships_extracted=result.relationships_extracted,
                unknown_terms=result.unknown_terms,
                teams_detected=source_doc.team_ids,
                version="1.0.0",
                error=result.error,
                execution_time_ms=round((_time.time() - start) * 1000, 1),
            )
        finally:
            # Clean up temp file
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # File-Based Ingestion (bridges API/Watcher to Fabric)
    # ------------------------------------------------------------------

    def ingest_file(self, file_path: Path, pipeline=None) -> FabricIngestResult:
        """
        Ingest a single file through the KnowledgeFabric.

        Handles change detection, version tracking, concept-team association,
        and all fabric bookkeeping. This is the canonical entry point for
        file-based ingestion (API, watcher, CLI).

        Args:
            file_path: Path to the file to ingest.
            pipeline: Optional pre-configured IngestionPipeline.

        Returns:
            FabricIngestResult with ingestion details.
        """
        source_path = Path(file_path)
        if not source_path.exists():
            return FabricIngestResult(
                document_id="", source_path=str(source_path),
                change_type=ChangeType.NEW_FILE,
                error=f"File not found: {source_path}",
            )

        # Check if document already exists by source_path
        sha256 = generate_sha256(source_path)
        conn = get_connection()
        existing = conn.execute(
            "SELECT document_id, sha256 FROM document_state WHERE source_path = ?",
            (str(source_path),),
        ).fetchone()
        conn.close()

        if existing:
            existing_doc_id, existing_sha = existing
            if existing_sha == sha256:
                # Unchanged
                return FabricIngestResult(
                    document_id=existing_doc_id,
                    source_path=str(source_path),
                    change_type=ChangeType.NONE,
                )
            else:
                # Changed
                change = ChangeDetection(
                    change_type=ChangeType.CONTENT_CHANGED,
                    document_id=existing_doc_id,
                    source_path=str(source_path),
                    details="Content hash changed",
                )
                return self._handle_changed(source_path, change, pipeline)

        # New file — full ingestion
        return self._handle_new_file(source_path, pipeline)

    def backfill_existing_documents(self, pipeline=None) -> dict:
        """
        Populate concept_teams and document_versions for documents
        that were ingested before the Fabric was wired in.

        Iterates all documents in the documents table, creates
        document_state and document_versions entries, and calls
        _track_concepts() for each.

        Returns dict with counts.
        """
        conn = get_connection()
        docs = conn.execute(
            "SELECT document_id, title, team_owner, source_path, sha256 "
            "FROM documents"
        ).fetchall()
        conn.close()

        backfilled = 0
        skipped = 0
        errors = 0

        for doc_id, title, team_owner, source_path, sha256 in docs:
            try:
                conn = get_connection()

                # Check if already has document_state
                existing_state = conn.execute(
                    "SELECT document_id FROM document_state WHERE document_id = ?",
                    (doc_id,),
                ).fetchone()

                if not existing_state:
                    # Insert document_state
                    team_ids = f'["{team_owner or "unknown"}"]'
                    conn.execute(
                        """INSERT OR IGNORE INTO document_state
                        (document_id, source_path, sha256, file_size,
                         last_modified, last_ingested, state, version, team_ids)
                        VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?)""",
                        (doc_id, source_path or "", sha256 or "",
                         datetime.utcnow(), datetime.utcnow(),
                         DocumentState.INDEXED.value, "1.0.0", team_ids),
                    )

                # Check if already has document_versions
                existing_ver = conn.execute(
                    "SELECT document_id FROM document_versions WHERE document_id = ?",
                    (doc_id,),
                ).fetchone()

                if not existing_ver:
                    # Count chunks for this document
                    chunk_count = conn.execute(
                        "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
                        (doc_id,),
                    ).fetchone()[0]

                    conn.execute(
                        """INSERT INTO document_versions
                        (document_id, version, sha256, ingested_at,
                         source_path, chunks_count, is_current)
                        VALUES (?, ?, ?, ?, ?, ?, TRUE)""",
                        (doc_id, "1.0.0", sha256 or "",
                         datetime.utcnow(), source_path or "", chunk_count),
                    )

                conn.close()

                # Track concepts
                team = team_owner or "unknown"
                if team != "unknown":
                    self._track_concepts(doc_id, team, True)

                backfilled += 1

            except Exception:
                errors += 1
                try:
                    conn.close()
                except Exception:
                    pass

        return {
            "total_documents": len(docs),
            "backfilled": backfilled,
            "skipped": skipped,
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # Source Adapter Cursor Management
    # ------------------------------------------------------------------

    def ensure_source_cursors_table(self) -> None:
        """Create the source_cursors table if it doesn't exist."""
        conn = get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS source_cursors (
                source_id TEXT PRIMARY KEY,
                cursor_type TEXT,
                cursor_value TEXT,
                last_run TIMESTAMP,
                items_processed INTEGER DEFAULT 0
            )
        """)
        conn.close()

    def load_source_cursor(self, source_id: str) -> Optional[str]:
        """Load persisted cursor for a source adapter."""
        self.ensure_source_cursors_table()
        conn = get_connection()
        row = conn.execute(
            "SELECT cursor_value FROM source_cursors WHERE source_id = ?",
            (source_id,),
        ).fetchone()
        conn.close()
        return row[0] if row else None

    def save_source_cursor(self, source_id: str, cursor_value: str) -> None:
        """Persist cursor for a source adapter."""
        self.ensure_source_cursors_table()
        conn = get_connection()
        conn.execute(
            """INSERT OR REPLACE INTO source_cursors
            (source_id, cursor_type, cursor_value, last_run)
            VALUES (?, 'adapter', ?, ?)""",
            (source_id, cursor_value, datetime.utcnow()),
        )
        conn.close()

    def get_source_cursors(self) -> list[dict]:
        """List all persisted source cursors."""
        self.ensure_source_cursors_table()
        conn = get_connection()
        rows = conn.execute(
            """SELECT source_id, cursor_type, cursor_value, last_run, items_processed
            FROM source_cursors ORDER BY last_run DESC"""
        ).fetchall()
        conn.close()
        return [
            {"source_id": r[0], "cursor_type": r[1], "cursor_value": r[2],
             "last_run": str(r[3]), "items_processed": r[4]}
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close any open resources."""
        pass


def _bump_version(version_row) -> str:
    """Bump a semantic version (1.0.0 -> 1.0.1, etc.)."""
    if not version_row:
        return "1.0.0"
    current = version_row[0] if isinstance(version_row, tuple) else version_row
    parts = current.split(".")
    if len(parts) >= 3:
        try:
            patch = int(parts[2]) + 1
            return f"{parts[0]}.{parts[1]}.{patch}"
        except ValueError:
            pass
    return "1.0.1"
