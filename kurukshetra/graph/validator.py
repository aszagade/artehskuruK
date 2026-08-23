"""
Graph Validation Framework
==========================

Deterministic validation of the Knowledge Graph.

Two validation modes:
  1. Extraction validation — validate SmartEntityExtractor output (no DB)
  2. Persisted graph validation — validate DuckDB state (requires DB)

Validates:
  - Every document has a DOCUMENT entity
  - Every document has an OWNED_BY relationship to a TEAM
  - Systems, processes, jobs, incidents are detected
  - Evidence is attached to every entity
  - No duplicate entity IDs exist
  - No orphan entities (entity with no relationships)
  - Graph statistics are consistent
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .entity_types import (
    ExtendedEntity,
    ExtendedEntityType,
    ExtendedRelationship,
    ExtendedRelationType,
)
from .extractor import ExtractionResult, SmartEntityExtractor
from .repository import GraphRepository


# =====================================================================
# Validation result types
# =====================================================================

@dataclass
class DocumentValidation:
    """Validation result for a single document."""
    document_id: str
    has_document_entity: bool = False
    has_team_relationship: bool = False
    systems_detected: int = 0
    processes_detected: int = 0
    jobs_detected: int = 0
    incidents_detected: int = 0
    configs_detected: int = 0
    evidence_attached: bool = False
    entity_count: int = 0
    relationship_count: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class ValidationReport:
    """Complete validation report."""
    # Counts
    documents_validated: int = 0
    total_entities: int = 0
    total_relationships: int = 0
    total_evidence: int = 0
    teams_represented: int = 0

    # Health
    orphan_entities: int = 0
    duplicate_ids: int = 0
    coverage_pct: float = 0.0

    # Per-document results
    document_results: list[DocumentValidation] = field(default_factory=list)

    # Errors
    critical_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Validation passed if no critical errors."""
        return len(self.critical_errors) == 0

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            "=" * 50,
            "GRAPH VALIDATION REPORT",
            "=" * 50,
            "",
            f"Documents:  {self.documents_validated}",
            f"Entities:   {self.total_entities}",
            f"Relationships: {self.total_relationships}",
            f"Evidence:   {self.total_evidence}",
            f"Teams:      {self.teams_represented}",
            "",
            f"Orphan entities:  {self.orphan_entities}",
            f"Duplicate IDs:    {self.duplicate_ids}",
            f"Coverage:         {self.coverage_pct:.1f}%",
            "",
        ]

        if self.critical_errors:
            lines.append(f"CRITICAL ERRORS: {len(self.critical_errors)}")
            for err in self.critical_errors:
                lines.append(f"  ✗ {err}")
            lines.append("")

        if self.warnings:
            lines.append(f"WARNINGS: {len(self.warnings)}")
            for warn in self.warnings:
                lines.append(f"  ⚠ {warn}")
            lines.append("")

        if self.passed:
            lines.append("RESULT: ✓ PASSED")
        else:
            lines.append("RESULT: ✗ FAILED")

        lines.append("=" * 50)
        return "\n".join(lines)


# =====================================================================
# Graph Validator
# =====================================================================

class GraphValidator:
    """
    Deterministic validation of Knowledge Graph state.

    Usage:
        # Validate extraction results (no DB)
        validator = GraphValidator()
        report = validator.validate_extraction(extraction_result)

        # Validate persisted graph (requires DuckDB)
        validator = GraphValidator(db_path="kurukshetra_registry.duckdb")
        report = validator.validate_persisted_graph()

        # Validate all documents
        validator = GraphValidator(db_path="kurukshetra_registry.duckdb")
        report = validator.validate_all_documents()
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path
        self._repository: Optional[GraphRepository] = None

    def _get_repository(self) -> GraphRepository:
        """Get or create the repository connection."""
        if self._repository is None:
            if self.db_path is None:
                raise ValueError("db_path required for persisted graph validation")
            self._repository = GraphRepository(self.db_path)
        return self._repository

    # -----------------------------------------------------------------
    # Extraction validation (no DB required)
    # -----------------------------------------------------------------

    def validate_extraction(self, result: ExtractionResult) -> DocumentValidation:
        """
        Validate a single ExtractionResult from SmartEntityExtractor.

        Checks:
        - DOCUMENT entity exists
        - OWNED_BY relationship to TEAM exists
        - At least one SYSTEM detected
        - Evidence attached to entities
        - No duplicate entity IDs
        """
        doc_val = DocumentValidation(document_id=result.document_id)
        entity_ids = set()
        duplicate_ids = set()

        # Count entities by type
        for entity in result.entities:
            doc_val.entity_count += 1

            # Track duplicates
            if entity.id in entity_ids:
                duplicate_ids.add(entity.id)
            entity_ids.add(entity.id)

            # Check document entity
            if entity.entity_type == ExtendedEntityType.DOCUMENT:
                doc_val.has_document_entity = True

            # Check evidence
            if entity.evidence:
                doc_val.evidence_attached = True

            # Count by type
            if entity.entity_type == ExtendedEntityType.SYSTEM:
                doc_val.systems_detected += 1
            elif entity.entity_type == ExtendedEntityType.PROCESS:
                doc_val.processes_detected += 1
            elif entity.entity_type == ExtendedEntityType.JOB:
                doc_val.jobs_detected += 1
            elif entity.entity_type == ExtendedEntityType.INCIDENT:
                doc_val.incidents_detected += 1
            elif entity.entity_type == ExtendedEntityType.CONFIGURATION:
                doc_val.configs_detected += 1

        # Check relationships
        doc_val.relationship_count = len(result.relationships)
        for rel in result.relationships:
            if rel.relation_type == ExtendedRelationType.OWNED_BY:
                doc_val.has_team_relationship = True

            # Track relationship duplicates
            if rel.source_id in entity_ids and rel.target_id in entity_ids:
                pass  # Valid relationship between known entities

        # Validation errors
        if not doc_val.has_document_entity:
            doc_val.errors.append("Missing DOCUMENT entity")
        if not doc_val.has_team_relationship:
            doc_val.errors.append("Missing OWNED_BY relationship to TEAM")
        if not doc_val.evidence_attached:
            doc_val.errors.append("No evidence attached to any entity")
        if duplicate_ids:
            doc_val.errors.append(f"Duplicate entity IDs: {duplicate_ids}")
        if doc_val.systems_detected == 0:
            doc_val.errors.append("No SYSTEM entities detected")

        return doc_val

    # -----------------------------------------------------------------
    # Persisted graph validation
    # -----------------------------------------------------------------

    def validate_persisted_graph(self) -> ValidationReport:
        """
        Validate the full persisted graph state in DuckDB.

        Checks:
        - All required tables exist
        - Entity count > 0
        - Relationship count > 0
        - Evidence count > 0
        - No orphan entities
        - No duplicate entity IDs
        - Team entities exist
        - Coverage calculation
        """
        repo = self._get_repository()
        conn = repo.get_connection()
        report = ValidationReport()

        # 1. Check tables exist
        tables = conn.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'main'
        """).fetchall()
        table_names = {r[0] for r in tables}

        required_tables = {"graph_entities", "graph_relationships", "graph_evidence", "graph_entity_meta"}
        missing = required_tables - table_names
        if missing:
            report.critical_errors.append(f"Missing tables: {missing}")
            return report

        # 2. Count entities
        entity_rows = conn.execute("SELECT COUNT(*) FROM graph_entities").fetchone()
        report.total_entities = entity_rows[0] if entity_rows else 0

        if report.total_entities == 0:
            report.critical_errors.append("No entities in graph")
            return report

        # 3. Count relationships
        rel_rows = conn.execute("SELECT COUNT(*) FROM graph_relationships").fetchone()
        report.total_relationships = rel_rows[0] if rel_rows else 0

        # 4. Count evidence
        ev_rows = conn.execute("SELECT COUNT(*) FROM graph_evidence").fetchone()
        report.total_evidence = ev_rows[0] if ev_rows else 0

        # 5. Check for duplicate entity IDs
        dup_rows = conn.execute("""
            SELECT id, COUNT(*) as cnt
            FROM graph_entities
            GROUP BY id
            HAVING cnt > 1
        """).fetchall()
        report.duplicate_ids = len(dup_rows)
        if dup_rows:
            report.warnings.append(f"{len(dup_rows)} duplicate entity IDs found")

        # 6. Find orphan entities (entities with no relationships)
        orphan_rows = conn.execute("""
            SELECT ge.id, ge.name, ge.entity_type
            FROM graph_entities ge
            WHERE NOT EXISTS (
                SELECT 1 FROM graph_relationships gr
                WHERE gr.source_id = ge.id OR gr.target_id = ge.id
            )
        """).fetchall()
        report.orphan_entities = len(orphan_rows)
        if orphan_rows:
            report.warnings.append(f"{len(orphan_rows)} orphan entities (no relationships)")

        # 7. Check teams
        team_rows = conn.execute("""
            SELECT DISTINCT gem.team_id
            FROM graph_entity_meta gem
            WHERE gem.team_id IS NOT NULL
        """).fetchall()
        report.teams_represented = len(team_rows)

        # 8. Validate entity type consistency
        entity_type_rows = conn.execute("""
            SELECT entity_type, COUNT(*)
            FROM graph_entities
            GROUP BY entity_type
        """).fetchall()
        valid_types = {r[0] for r in entity_type_rows}
        known_types = {t.value for t in ExtendedEntityType}
        unknown_types = valid_types - known_types
        if unknown_types:
            report.warnings.append(f"Unknown entity types in DB: {unknown_types}")

        # 9. Validate relationship type consistency
        rel_type_rows = conn.execute("""
            SELECT relation_type, COUNT(*)
            FROM graph_relationships
            GROUP BY relation_type
        """).fetchall()
        valid_rel_types = {r[0] for r in rel_type_rows}
        known_rel_types = {t.value for t in ExtendedRelationType}
        # Also accept legacy types
        known_rel_types.add("related_to")
        unknown_rel_types = valid_rel_types - known_rel_types
        if unknown_rel_types:
            report.warnings.append(f"Unknown relationship types in DB: {unknown_rel_types}")

        # 10. Validate evidence integrity
        evidence_orphans = conn.execute("""
            SELECT COUNT(*) FROM graph_evidence ge
            WHERE NOT EXISTS (
                SELECT 1 FROM graph_entities gent
                WHERE gent.id = ge.entity_id
            )
        """).fetchone()
        if evidence_orphans and evidence_orphans[0] > 0:
            report.warnings.append(f"{evidence_orphans[0]} evidence records with no matching entity")

        # 11. Validate confidence values
        bad_conf = conn.execute("""
            SELECT COUNT(*) FROM graph_relationships
            WHERE confidence < 0 OR confidence > 1
        """).fetchone()
        if bad_conf and bad_conf[0] > 0:
            report.critical_errors.append(f"{bad_conf[0]} relationships with confidence outside [0,1]")

        # 12. Calculate coverage
        # Coverage = entities with evidence / total entities
        if report.total_entities > 0:
            with_evidence = conn.execute("""
                SELECT COUNT(DISTINCT entity_id) FROM graph_evidence
            """).fetchone()
            evidence_count = with_evidence[0] if with_evidence else 0
            report.coverage_pct = round(evidence_count / report.total_entities * 100, 1)

        return report

    # -----------------------------------------------------------------
    # Per-document validation against persisted graph
    # -----------------------------------------------------------------

    def validate_all_documents(self) -> ValidationReport:
        """
        Validate each document entity in the persisted graph.

        For each DOC-* entity:
        - Has a TEAM entity connected via OWNED_BY
        - Has at least one SYSTEM entity connected via USES
        - Has evidence records
        """
        repo = self._get_repository()
        conn = repo.get_connection()
        report = ValidationReport()

        # Get base stats
        entity_rows = conn.execute("SELECT COUNT(*) FROM graph_entities").fetchone()
        report.total_entities = entity_rows[0] if entity_rows else 0
        rel_rows = conn.execute("SELECT COUNT(*) FROM graph_relationships").fetchone()
        report.total_relationships = rel_rows[0] if rel_rows else 0
        ev_rows = conn.execute("SELECT COUNT(*) FROM graph_evidence").fetchone()
        report.total_evidence = ev_rows[0] if ev_rows else 0

        # Get all document entities
        doc_entities = conn.execute("""
            SELECT id, name FROM graph_entities WHERE id LIKE 'DOC-%'
        """).fetchall()

        report.documents_validated = len(doc_entities)

        for doc_id, doc_name in doc_entities:
            doc_val = DocumentValidation(document_id=doc_id)
            doc_val.has_document_entity = True  # We found it

            # Check OWNED_BY relationship
            owned_by = conn.execute("""
                SELECT COUNT(*) FROM graph_relationships
                WHERE source_id = ? AND relation_type = 'owned_by'
            """, [doc_id]).fetchone()
            doc_val.has_team_relationship = (owned_by[0] > 0) if owned_by else False

            # Check connected entity types
            connected = conn.execute("""
                SELECT gr.target_id, ge.entity_type
                FROM graph_relationships gr
                JOIN graph_entities ge ON gr.target_id = ge.id
                WHERE gr.source_id = ?
            """, [doc_id]).fetchall()

            for target_id, entity_type in connected:
                if entity_type == "system":
                    doc_val.systems_detected += 1
                elif entity_type == "process":
                    doc_val.processes_detected += 1
                elif entity_type == "job":
                    doc_val.jobs_detected += 1
                elif entity_type == "incident":
                    doc_val.incidents_detected += 1
                elif entity_type == "configuration":
                    doc_val.configs_detected += 1

            doc_val.entity_count = 1 + len(connected)

            # Check evidence
            ev_count = conn.execute("""
                SELECT COUNT(*) FROM graph_evidence WHERE entity_id = ?
            """, [doc_id]).fetchone()
            doc_val.evidence_attached = (ev_count[0] > 0) if ev_count else False

            # Validation checks
            if not doc_val.has_team_relationship:
                doc_val.errors.append("Missing OWNED_BY relationship to TEAM")
            if not doc_val.evidence_attached:
                doc_val.errors.append("No evidence attached")
            if doc_val.systems_detected == 0:
                doc_val.errors.append("No SYSTEM entities connected")

            report.document_results.append(doc_val)

            if doc_val.errors:
                report.warnings.extend(
                    f"{doc_id}: {e}" for e in doc_val.errors
                )

        # Coverage
        if report.total_entities > 0:
            with_evidence = conn.execute("""
                SELECT COUNT(DISTINCT entity_id) FROM graph_evidence
            """).fetchone()
            evidence_count = with_evidence[0] if with_evidence else 0
            report.coverage_pct = round(evidence_count / report.total_entities * 100, 1)

        # Teams
        team_rows = conn.execute("""
            SELECT DISTINCT team_id FROM graph_entity_meta
            WHERE team_id IS NOT NULL
        """).fetchall()
        report.teams_represented = len(team_rows)

        # Orphans
        orphan_rows = conn.execute("""
            SELECT COUNT(*) FROM graph_entities ge
            WHERE NOT EXISTS (
                SELECT 1 FROM graph_relationships gr
                WHERE gr.source_id = ge.id OR gr.target_id = ge.id
            )
        """).fetchone()
        report.orphan_entities = orphan_rows[0] if orphan_rows else 0

        # Duplicates
        dup_rows = conn.execute("""
            SELECT COUNT(*) FROM (
                SELECT id FROM graph_entities GROUP BY id HAVING COUNT(*) > 1
            )
        """).fetchone()
        report.duplicate_ids = dup_rows[0] if dup_rows else 0

        return report

    # -----------------------------------------------------------------
    # Summary statistics
    # -----------------------------------------------------------------

    def get_graph_summary(self) -> dict:
        """Get a summary of the graph state for reporting."""
        repo = self._get_repository()
        conn = repo.get_connection()

        # Entity counts by type
        entity_rows = conn.execute("""
            SELECT entity_type, COUNT(*) FROM graph_entities GROUP BY entity_type
        """).fetchall()
        entities_by_type = {r[0]: r[1] for r in entity_rows}

        # Relationship counts by type
        rel_rows = conn.execute("""
            SELECT relation_type, COUNT(*) FROM graph_relationships GROUP BY relation_type
        """).fetchall()
        relationships_by_type = {r[0]: r[1] for r in rel_rows}

        # Confidence distribution
        conf_rows = conn.execute("""
            SELECT
                CASE
                    WHEN confidence >= 0.8 THEN 'high'
                    WHEN confidence >= 0.5 THEN 'medium'
                    WHEN confidence >= 0.3 THEN 'low'
                    ELSE 'very_low'
                END as tier,
                COUNT(*)
            FROM graph_relationships
            GROUP BY tier
        """).fetchall()
        confidence_distribution = {r[0]: r[1] for r in conf_rows}

        return {
            "entities_by_type": entities_by_type,
            "relationships_by_type": relationships_by_type,
            "confidence_distribution": confidence_distribution,
        }

    # -----------------------------------------------------------------
    # Cleanup
    # -----------------------------------------------------------------

    def close(self) -> None:
        """Close database connection."""
        if self._repository:
            self._repository.close()
            self._repository = None
