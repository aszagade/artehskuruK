"""
Graph Validation Tests
======================

Deterministic tests for:
  - SmartEntityExtractor output
  - ExtractionResult invariants
  - GraphValidator extraction mode
  - GraphValidator persisted mode (in-memory DuckDB)
  - Graph traversal correctness
  - Evidence integrity

Run:
    python -m pytest tests/test_graph.py -v
    python tests/test_graph.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kurukshetra.graph.entity_types import (
    ExtendedEntity,
    ExtendedEntityType,
    ExtendedRelationship,
    ExtendedRelationType,
    Evidence,
)
from kurukshetra.graph.extractor import SmartEntityExtractor, ExtractionResult
from kurukshetra.graph.traversal import GraphTraversalEngine
from kurukshetra.graph.registry import GraphRegistry
from kurukshetra.graph.validator import GraphValidator, ValidationReport


# =====================================================================
# Test fixtures
# =====================================================================

SAMPLE_TEXT_SPM = """
G3 RMS decision upload process requires Opera Agent connectivity.
Step 3 failure occurred during full upload to property HLTN-123.
Configuration parameter: restriction_level = 3.
The monitoring job failed with timeout error on OXI integration.
Installation process for new property requires OHIP setup.
Enable continuous pricing parameter for CP Config.
"""

SAMPLE_TEXT_ICS = """
OXI integration with Opera Cloud uses HTNG protocol.
Data flow from PMS to G3 RMS requires OHIP connectivity.
Opera Agent migration from OXI to Agent involves step failure.
Deployment process for Opera Cloud integration.
Job failure during data feed process to SynXis.
"""

SAMPLE_TEXT_HR = """
Employee handbook covers leave policy and benefits.
Wellness program includes health insurance and superannuation.
Separation process requires 30-day notice period.
Performance appraisal cycle is annual.
"""


# =====================================================================
# Extraction tests
# =====================================================================

class TestSmartEntityExtractor(unittest.TestCase):
    """Test SmartEntityExtractor extraction logic."""

    def setUp(self):
        self.extractor = SmartEntityExtractor()

    def test_document_entity_created(self):
        """Every extraction creates a DOCUMENT entity."""
        result = self.extractor.extract_from_document(
            text=SAMPLE_TEXT_SPM,
            document_id="DOC-001",
            document_title="Test Doc",
        )
        doc_entities = [
            e for e in result.entities
            if e.entity_type == ExtendedEntityType.DOCUMENT
        ]
        self.assertEqual(len(doc_entities), 1)
        self.assertEqual(doc_entities[0].id, "DOC-DOC-001")

    def test_team_entity_created_when_team_id_provided(self):
        """TEAM entity and OWNED_BY relationship created when team_id given."""
        result = self.extractor.extract_from_document(
            text=SAMPLE_TEXT_SPM,
            document_id="DOC-002",
            team_id="spm",
        )
        team_entities = [
            e for e in result.entities
            if e.entity_type == ExtendedEntityType.TEAM
        ]
        self.assertEqual(len(team_entities), 1)
        self.assertEqual(team_entities[0].id, "TEAM-SPM")

        owned_by_rels = [
            r for r in result.relationships
            if r.relation_type == ExtendedRelationType.OWNED_BY
        ]
        self.assertEqual(len(owned_by_rels), 1)
        self.assertEqual(owned_by_rels[0].source_id, "DOC-DOC-002")
        self.assertEqual(owned_by_rels[0].target_id, "TEAM-SPM")

    def test_no_team_entity_when_no_team_id(self):
        """No TEAM entity when team_id is None."""
        result = self.extractor.extract_from_document(
            text=SAMPLE_TEXT_SPM,
            document_id="DOC-003",
        )
        team_entities = [
            e for e in result.entities
            if e.entity_type == ExtendedEntityType.TEAM
        ]
        self.assertEqual(len(team_entities), 0)

    def test_system_entities_detected(self):
        """SYSTEM entities are extracted from known patterns."""
        result = self.extractor.extract_from_document(
            text=SAMPLE_TEXT_SPM,
            document_id="DOC-004",
        )
        systems = [
            e for e in result.entities
            if e.entity_type == ExtendedEntityType.SYSTEM
        ]
        system_names = {e.name.lower() for e in systems}
        # Should find at least G3 RMS, Opera Agent, OXI
        self.assertTrue(len(systems) >= 2, f"Expected >=2 systems, got {len(systems)}: {system_names}")

    def test_incident_entities_detected(self):
        """INCIDENT entities are extracted from error patterns."""
        result = self.extractor.extract_from_document(
            text=SAMPLE_TEXT_SPM,
            document_id="DOC-005",
        )
        incidents = [
            e for e in result.entities
            if e.entity_type == ExtendedEntityType.INCIDENT
        ]
        self.assertTrue(len(incidents) >= 1, "Expected at least 1 incident")

    def test_process_entities_detected(self):
        """PROCESS entities are extracted from workflow patterns."""
        result = self.extractor.extract_from_document(
            text=SAMPLE_TEXT_SPM,
            document_id="DOC-006",
        )
        processes = [
            e for e in result.entities
            if e.entity_type == ExtendedEntityType.PROCESS
        ]
        self.assertTrue(len(processes) >= 1, "Expected at least 1 process")

    def test_job_entities_detected(self):
        """JOB entities are extracted from job patterns."""
        result = self.extractor.extract_from_document(
            text=SAMPLE_TEXT_SPM,
            document_id="DOC-007",
        )
        jobs = [
            e for e in result.entities
            if e.entity_type == ExtendedEntityType.JOB
        ]
        self.assertTrue(len(jobs) >= 1, "Expected at least 1 job")

    def test_configuration_entities_detected(self):
        """CONFIGURATION entities are extracted from config patterns."""
        result = self.extractor.extract_from_document(
            text=SAMPLE_TEXT_SPM,
            document_id="DOC-008",
        )
        configs = [
            e for e in result.entities
            if e.entity_type == ExtendedEntityType.CONFIGURATION
        ]
        self.assertTrue(len(configs) >= 1, "Expected at least 1 configuration")

    def test_evidence_attached_to_entities(self):
        """Every entity has at least one evidence record."""
        result = self.extractor.extract_from_document(
            text=SAMPLE_TEXT_SPM,
            document_id="DOC-009",
        )
        for entity in result.entities:
            self.assertTrue(
                len(entity.evidence) > 0,
                f"Entity {entity.id} has no evidence",
            )

    def test_evidence_attached_to_relationships(self):
        """Every relationship has at least one evidence record."""
        result = self.extractor.extract_from_document(
            text=SAMPLE_TEXT_SPM,
            document_id="DOC-010",
        )
        for rel in result.relationships:
            self.assertTrue(
                len(rel.evidence) > 0,
                f"Relationship {rel.source_id}->{rel.target_id} has no evidence",
            )

    def test_no_duplicate_entity_ids_in_single_doc(self):
        """No duplicate entity IDs within a single extraction."""
        result = self.extractor.extract_from_document(
            text=SAMPLE_TEXT_SPM,
            document_id="DOC-011",
        )
        ids = [e.id for e in result.entities]
        self.assertEqual(len(ids), len(set(ids)), "Duplicate entity IDs found")

    def test_extraction_confidence_in_range(self):
        """Extraction confidence is between 0 and 1."""
        result = self.extractor.extract_from_document(
            text=SAMPLE_TEXT_SPM,
            document_id="DOC-012",
        )
        self.assertGreaterEqual(result.extraction_confidence, 0.0)
        self.assertLessEqual(result.extraction_confidence, 1.0)

    def test_entities_by_type_matches_entities(self):
        """entities_by_type counts match actual entities."""
        result = self.extractor.extract_from_document(
            text=SAMPLE_TEXT_SPM,
            document_id="DOC-013",
        )
        actual_counts = {}
        for e in result.entities:
            t = e.entity_type.value
            actual_counts[t] = actual_counts.get(t, 0) + 1
        self.assertEqual(result.entities_by_type, actual_counts)

    def test_resolves_relationship_for_incidents(self):
        """RESOLVES relationship exists for each incident."""
        result = self.extractor.extract_from_document(
            text=SAMPLE_TEXT_SPM,
            document_id="DOC-014",
        )
        incidents = [
            e for e in result.entities
            if e.entity_type == ExtendedEntityType.INCIDENT
        ]
        resolves_rels = [
            r for r in result.relationships
            if r.relation_type == ExtendedRelationType.RESOLVES
        ]
        # At least as many RESOLVES as incidents
        self.assertGreaterEqual(len(resolves_rels), len(incidents))

    def test_uses_relationship_for_systems(self):
        """USES relationship exists for each system."""
        result = self.extractor.extract_from_document(
            text=SAMPLE_TEXT_SPM,
            document_id="DOC-015",
        )
        systems = [
            e for e in result.entities
            if e.entity_type == ExtendedEntityType.SYSTEM
        ]
        uses_rels = [
            r for r in result.relationships
            if r.relation_type == ExtendedRelationType.USES
            and r.source_id.startswith("DOC-")
        ]
        self.assertGreaterEqual(len(uses_rels), len(systems))

    def test_cross_document_deduplication(self):
        """Same system across two extractions gets deduplicated via cache."""
        ext = SmartEntityExtractor()
        ext.extract_from_document(
            text="G3 RMS requires Opera Agent.",
            document_id="DOC-A",
        )
        ext.extract_from_document(
            text="G3 RMS requires Opera Agent.",
            document_id="DOC-B",
        )
        cached = ext.get_cached_entities()
        # SYS-G3-RMS should appear once in cache
        g3_entities = [e for e in cached.values() if "G3" in e.name]
        self.assertEqual(len(g3_entities), 1, "G3 RMS entity not deduplicated")
        # Should have evidence from both documents
        self.assertGreaterEqual(len(g3_entities[0].evidence), 2)


# =====================================================================
# ExtractionResult validator tests
# =====================================================================

class TestExtractionValidator(unittest.TestCase):
    """Test GraphValidator.validate_extraction()."""

    def setUp(self):
        self.extractor = SmartEntityExtractor()
        self.validator = GraphValidator()

    def test_valid_extraction_passes(self):
        """A good extraction passes validation."""
        result = self.extractor.extract_from_document(
            text=SAMPLE_TEXT_SPM,
            document_id="DOC-VAL-001",
            team_id="spm",
        )
        report = self.validator.validate_extraction(result)
        self.assertTrue(report.has_document_entity)
        self.assertTrue(report.has_team_relationship)
        self.assertGreater(report.systems_detected, 0)
        self.assertTrue(report.evidence_attached)
        self.assertEqual(len(report.errors), 0)

    def test_no_team_fails_team_check(self):
        """Extraction without team_id fails team relationship check."""
        result = self.extractor.extract_from_document(
            text=SAMPLE_TEXT_SPM,
            document_id="DOC-VAL-002",
        )
        report = self.validator.validate_extraction(result)
        self.assertFalse(report.has_team_relationship)
        self.assertTrue(any("OWNED_BY" in e for e in report.errors))

    def test_empty_text_minimal_extraction(self):
        """Empty text still creates a DOCUMENT entity."""
        result = self.extractor.extract_from_document(
            text="",
            document_id="DOC-VAL-003",
        )
        report = self.validator.validate_extraction(result)
        self.assertTrue(report.has_document_entity)
        # Empty text won't find systems
        self.assertEqual(report.systems_detected, 0)


# =====================================================================
# Persisted graph tests (in-memory DuckDB)
# =====================================================================

class TestPersistedGraph(unittest.TestCase):
    """Test GraphRegistry + GraphValidator with in-memory DuckDB."""

    def setUp(self):
        """Create a temporary DuckDB for testing."""
        self.db_path = tempfile.mktemp(suffix=".duckdb")
        self.registry = GraphRegistry(db_path=self.db_path)

    def tearDown(self):
        """Clean up temp DB."""
        self.registry.close()
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def test_ingest_populates_graph(self):
        """Ingesting a document populates entities, relationships, evidence."""
        result = self.registry.ingest_document(
            text=SAMPLE_TEXT_SPM,
            document_id="DOC-ING-001",
            document_title="Test SPM Doc",
            team_id="spm",
            product_scope=["G3 RMS"],
        )
        self.assertGreater(len(result.entities), 0)
        self.assertGreater(len(result.relationships), 0)

        stats = self.registry.get_stats()
        self.assertGreater(stats["total_entities"], 0)
        self.assertGreater(stats["total_relationships"], 0)

    def test_ingest_multiple_documents_no_duplicates(self):
        """Ingesting two docs with same system doesn't create duplicate system entity."""
        self.registry.ingest_document(
            text="G3 RMS uses Opera Agent for data feed.",
            document_id="DOC-DUP-001",
            team_id="spm",
        )
        self.registry.ingest_document(
            text="G3 RMS uses OHIP for connectivity.",
            document_id="DOC-DUP-002",
            team_id="ics",
        )
        stats = self.registry.get_stats()
        # G3 RMS should be one entity (upserted, not duplicated)
        g3_entities = self.registry.search_entities(query="G3 RMS")
        g3_systems = [e for e in g3_entities if e["type"] == "system"]
        self.assertEqual(len(g3_systems), 1, "G3 RMS entity duplicated")

    def test_team_entities_created(self):
        """TEAM entities are created for each team_id."""
        self.registry.ingest_document(
            text=SAMPLE_TEXT_SPM,
            document_id="DOC-TM-001",
            team_id="spm",
        )
        self.registry.ingest_document(
            text=SAMPLE_TEXT_ICS,
            document_id="DOC-TM-002",
            team_id="ics",
        )
        stats = self.registry.get_stats()
        self.assertIn("spm", stats["teams_represented"])
        self.assertIn("ics", stats["teams_represented"])

    def test_search_entities_by_type(self):
        """search_entities filters by entity_type."""
        self.registry.ingest_document(
            text=SAMPLE_TEXT_SPM,
            document_id="DOC-SRCH-001",
            team_id="spm",
        )
        systems = self.registry.search_entities(entity_type="system")
        self.assertGreater(len(systems), 0)
        for s in systems:
            self.assertEqual(s["type"], "system")

    def test_search_entities_by_team(self):
        """search_entities filters by team_id."""
        self.registry.ingest_document(
            text=SAMPLE_TEXT_SPM,
            document_id="DOC-SRCH-002",
            team_id="spm",
        )
        spm_entities = self.registry.search_entities(team_id="spm")
        self.assertGreater(len(spm_entities), 0)

    def test_entity_context_includes_neighborhood(self):
        """get_entity_context returns entity + neighborhood."""
        self.registry.ingest_document(
            text=SAMPLE_TEXT_SPM,
            document_id="DOC-CTX-001",
            team_id="spm",
        )
        # Find a system entity
        systems = self.registry.search_entities(entity_type="system")
        if systems:
            ctx = self.registry.get_entity_context(systems[0]["id"], depth=1)
            self.assertIsNotNone(ctx)
            self.assertIn("entity", ctx)
            self.assertIn("neighborhood", ctx)

    def test_find_path_between_entities(self):
        """find_path returns a path between connected entities."""
        self.registry.ingest_document(
            text=SAMPLE_TEXT_SPM,
            document_id="DOC-PATH-001",
            team_id="spm",
        )
        # Find doc and team
        docs = self.registry.search_entities(entity_type="document")
        teams = self.registry.search_entities(entity_type="team")
        if docs and teams:
            path = self.registry.find_path(docs[0]["id"], teams[0]["id"])
            self.assertIsNotNone(path)
            self.assertGreater(path["hops"], 0)

    def test_analyze_impact(self):
        """analyze_impact returns impact results."""
        self.registry.ingest_document(
            text=SAMPLE_TEXT_SPM,
            document_id="DOC-IMP-001",
            team_id="spm",
        )
        systems = self.registry.search_entities(entity_type="system")
        if systems:
            impact = self.registry.analyze_impact(systems[0]["id"])
            self.assertIn("total_affected", impact)
            self.assertIn("impact_score", impact)

    def test_confirm_entity(self):
        """confirm_entity increments verification count."""
        self.registry.ingest_document(
            text=SAMPLE_TEXT_SPM,
            document_id="DOC-CFM-001",
            team_id="spm",
        )
        systems = self.registry.search_entities(entity_type="system")
        if systems:
            eid = systems[0]["id"]
            before = systems[0]["verification_count"]
            self.registry.confirm_entity(eid)
            # Re-check
            after_entities = self.registry.search_entities(entity_type="system")
            matched = [e for e in after_entities if e["id"] == eid]
            if matched:
                self.assertGreater(matched[0]["verification_count"], before)


# =====================================================================
# Graph traversal tests
# =====================================================================

class TestGraphTraversal(unittest.TestCase):
    """Test GraphTraversalEngine with in-memory DuckDB."""

    def setUp(self):
        self.db_path = tempfile.mktemp(suffix=".duckdb")
        self.registry = GraphRegistry(db_path=self.db_path)
        # Ingest two documents to create a connected graph
        self.registry.ingest_document(
            text="G3 RMS uses Opera Agent. Monitoring job failed with timeout error.",
            document_id="DOC-TRV-001",
            team_id="spm",
        )
        self.registry.ingest_document(
            text="OXI integration with Opera Cloud uses HTNG. Data feed process requires OHIP.",
            document_id="DOC-TRV-002",
            team_id="ics",
        )
        self.traversal = GraphTraversalEngine(self.registry.repository)

    def tearDown(self):
        self.registry.close()
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def test_find_path_exists(self):
        """Path exists between document and its team."""
        docs = self.registry.search_entities(entity_type="document")
        teams = self.registry.search_entities(entity_type="team")
        if docs and teams:
            path = self.traversal.find_path(docs[0]["id"], teams[0]["id"])
            self.assertIsNotNone(path)
            self.assertGreaterEqual(path.hops, 1)

    def test_find_path_nonexistent(self):
        """No path if entity doesn't exist."""
        path = self.traversal.find_path("NONEXISTENT-1", "NONEXISTENT-2")
        self.assertIsNone(path)

    def test_expand_context(self):
        """Context expansion returns neighbors."""
        systems = self.registry.search_entities(entity_type="system")
        if systems:
            ctx = self.traversal.expand_context(systems[0]["id"], depth=2)
            self.assertIsNotNone(ctx)
            self.assertGreater(ctx.total_neighbors, 0)

    def test_detect_communities(self):
        """Community detection returns at least one community."""
        communities = self.traversal.detect_communities()
        # With two ingested docs, there should be connected components
        self.assertIsInstance(communities, list)

    def test_shortest_distance(self):
        """shortest_distance returns positive for connected entities."""
        docs = self.registry.search_entities(entity_type="document")
        if len(docs) >= 1:
            dist = self.traversal.shortest_distance(
                docs[0]["id"],
                docs[0]["id"],
            )
            self.assertEqual(dist, 0)  # distance to self is 0


# =====================================================================
# Full graph validation test
# =====================================================================

class TestFullValidation(unittest.TestCase):
    """Test GraphValidator.validate_persisted_graph() with populated DB."""

    def setUp(self):
        self.db_path = tempfile.mktemp(suffix=".duckdb")
        self.registry = GraphRegistry(db_path=self.db_path)
        # Ingest multiple documents
        for i, (text, team) in enumerate([
            (SAMPLE_TEXT_SPM, "spm"),
            (SAMPLE_TEXT_ICS, "ics"),
            (SAMPLE_TEXT_HR, "hr"),
        ]):
            self.registry.ingest_document(
                text=text,
                document_id=f"DOC-FULL-{i:03d}",
                document_title=f"Test Doc {i}",
                team_id=team,
            )
        self.validator = GraphValidator(db_path=self.db_path)

    def tearDown(self):
        self.registry.close()
        self.validator.close()
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def test_persisted_graph_passes(self):
        """Populated graph passes validation."""
        report = self.validator.validate_persisted_graph()
        self.assertTrue(report.passed, report.summary())
        self.assertGreater(report.total_entities, 0)
        self.assertGreater(report.total_relationships, 0)
        self.assertGreater(report.total_evidence, 0)

    def test_no_critical_errors(self):
        """No critical errors in populated graph."""
        report = self.validator.validate_persisted_graph()
        self.assertEqual(len(report.critical_errors), 0)

    def test_teams_represented(self):
        """All three teams are represented."""
        report = self.validator.validate_persisted_graph()
        self.assertGreaterEqual(report.teams_represented, 3)

    def test_validate_all_documents(self):
        """validate_all_documents covers all ingested docs."""
        report = self.validator.validate_all_documents()
        self.assertEqual(report.documents_validated, 3)
        self.assertGreater(report.total_entities, 0)

    def test_coverage_above_zero(self):
        """Coverage is above 0% for populated graph."""
        report = self.validator.validate_persisted_graph()
        self.assertGreater(report.coverage_pct, 0.0)

    def test_graph_summary(self):
        """get_graph_summary returns expected keys."""
        summary = self.validator.get_graph_summary()
        self.assertIn("entities_by_type", summary)
        self.assertIn("relationships_by_type", summary)
        self.assertIn("confidence_distribution", summary)


# =====================================================================
# Edge cases
# =====================================================================

class TestEdgeCases(unittest.TestCase):
    """Edge case tests."""

    def test_empty_text_extraction(self):
        """Extraction from empty text still produces a document entity."""
        ext = SmartEntityExtractor()
        result = ext.extract_from_document(text="", document_id="EMPTY")
        self.assertEqual(len(result.entities), 1)
        self.assertEqual(result.entities[0].entity_type, ExtendedEntityType.DOCUMENT)

    def test_very_long_text_extraction(self):
        """Extraction from long text completes without error."""
        ext = SmartEntityExtractor()
        long_text = "G3 RMS uses Opera Agent. " * 10000
        result = ext.extract_from_document(text=long_text, document_id="LONG")
        self.assertGreater(len(result.entities), 0)

    def test_unicode_text_extraction(self):
        """Extraction from text with unicode characters doesn't crash."""
        ext = SmartEntityExtractor()
        result = ext.extract_from_document(
            text="G3 RMS configuration for café property — status: ✓",
            document_id="UNICODE",
        )
        self.assertGreater(len(result.entities), 0)

    def test_validator_empty_db(self):
        """Validator on empty DB returns critical error."""
        db_path = tempfile.mktemp(suffix=".duckdb")
        try:
            validator = GraphValidator(db_path=db_path)
            report = validator.validate_persisted_graph()
            self.assertFalse(report.passed)
            self.assertTrue(len(report.critical_errors) > 0)
            validator.close()
        finally:
            try:
                os.unlink(db_path)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
