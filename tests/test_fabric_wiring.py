"""
Tests for Mission 3.33 — Knowledge Fabric Wiring
================================================

Proves that:
- KnowledgeFabric.ingest_file() populates document_state
- KnowledgeFabric.ingest_file() populates document_versions
- KnowledgeFabric.ingest_file() populates concept_teams (when entities exist)
- Backfill populates document_state and document_versions for existing docs
- Changed files get version increments
- Existing tests remain unaffected

Uses per-test database isolation to avoid DuckDB locking conflicts.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import kurukshetra.registry.database as db_mod
from kurukshetra.registry.database import get_connection


def _setup_isolated_db():
    """Create an isolated DuckDB, return (original_path, tmp_dir)."""
    original = db_mod.DATABASE_PATH
    tmp_dir = Path(tempfile.mkdtemp(prefix="fabric_wiring_"))
    db_path = tmp_dir / "test.db"
    db_mod.DATABASE_PATH = db_path

    # Initialize core schema
    from kurukshetra.registry.schema import initialize_schema
    initialize_schema()

    # Create additional tables needed by fabric/pipeline
    conn = get_connection()
    for table_def in [
        "CREATE TABLE IF NOT EXISTS chunks (chunk_id TEXT PRIMARY KEY, document_id TEXT, chunk_index INTEGER, text TEXT, start_offset INTEGER, end_offset INTEGER)",
        "CREATE TABLE IF NOT EXISTS graph_entities (id VARCHAR PRIMARY KEY, name VARCHAR, entity_type VARCHAR, description VARCHAR, metadata JSON, owner VARCHAR, visibility VARCHAR, quality_score DOUBLE DEFAULT 0.5, quality_label VARCHAR DEFAULT 'MEDIUM')",
        "CREATE TABLE IF NOT EXISTS graph_entity_meta (entity_id VARCHAR PRIMARY KEY, team_id VARCHAR, product_scope JSON, visibility VARCHAR, average_confidence DOUBLE, first_seen VARCHAR, last_verified VARCHAR, verification_count INTEGER DEFAULT 0)",
        "CREATE TABLE IF NOT EXISTS graph_relationships (source_id VARCHAR, target_id VARCHAR, relationship_type VARCHAR, confidence REAL, evidence TEXT)",
        "CREATE TABLE IF NOT EXISTS vectors (chunk_id TEXT PRIMARY KEY, embedding TEXT)",
        "CREATE TABLE IF NOT EXISTS unknown_terms (term TEXT, status TEXT, source_document TEXT, first_seen TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS glossary (term TEXT PRIMARY KEY, definition TEXT, confirmed_by TEXT, confirmed_at TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS rag_feedback (feedback_id TEXT PRIMARY KEY, query TEXT, chunk_id TEXT, rating INTEGER, created_at TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS agent_registry (agent_id TEXT PRIMARY KEY, agent_type TEXT, status TEXT, registered_at TIMESTAMP)",
    ]:
        try:
            conn.execute(table_def)
        except Exception:
            pass
    conn.close()
    return original, tmp_dir


def _teardown_isolated_db(original, tmp_dir):
    """Restore original database and clean up temp dir."""
    db_mod.DATABASE_PATH = original
    shutil.rmtree(tmp_dir, ignore_errors=True)


SAMPLE_TEXT = (
    "G3 Data Feed Configuration\n\n"
    "The G3 system requires the following configuration:\n"
    "- SPM team settings\n"
    "- ICS team settings\n"
    "- Demand360 integration\n\n"
    "RPM Configuration Case Workflow:\n"
    "Step 1: Create case\n"
    "Step 2: Configure settings\n"
    "Step 3: Deploy\n"
)


class TestIngestFilePopulatesDocumentState(unittest.TestCase):
    """Verify ingest_file() creates a document_state entry."""

    def test_document_state_created(self):
        from kurukshetra.knowledge.fabric import KnowledgeFabric

        original, tmp_dir = _setup_isolated_db()
        try:
            inbox = tmp_dir / "inbox"
            inbox.mkdir()
            test_file = inbox / "test_document.txt"
            test_file.write_text(SAMPLE_TEXT, encoding="utf-8")

            fabric = KnowledgeFabric()
            try:
                result = fabric.ingest_file(test_file)
            finally:
                fabric.close()

            self.assertEqual(result.change_type.value, "new_file")
            self.assertNotEqual(result.document_id, "")

            conn = get_connection()
            row = conn.execute(
                "SELECT document_id, state, version, source_path "
                "FROM document_state WHERE document_id = ?",
                (result.document_id,),
            ).fetchone()
            conn.close()

            self.assertIsNotNone(row, "document_state entry must exist")
            self.assertEqual(row[1], "indexed")
            self.assertEqual(row[2], "1.0.0")
            self.assertIn("test_document.txt", row[3])
        finally:
            _teardown_isolated_db(original, tmp_dir)


class TestIngestFilePopulatesDocumentVersions(unittest.TestCase):
    """Verify ingest_file() creates a document_versions entry."""

    def test_document_version_created(self):
        from kurukshetra.knowledge.fabric import KnowledgeFabric

        original, tmp_dir = _setup_isolated_db()
        try:
            inbox = tmp_dir / "inbox"
            inbox.mkdir()
            test_file = inbox / "test_document.txt"
            test_file.write_text(SAMPLE_TEXT, encoding="utf-8")

            fabric = KnowledgeFabric()
            try:
                result = fabric.ingest_file(test_file)
            finally:
                fabric.close()

            conn = get_connection()
            row = conn.execute(
                "SELECT document_id, version, is_current, chunks_count "
                "FROM document_versions WHERE document_id = ?",
                (result.document_id,),
            ).fetchone()
            conn.close()

            self.assertIsNotNone(row, "document_versions entry must exist")
            self.assertEqual(row[1], "1.0.0")
            self.assertTrue(row[2])  # is_current
            self.assertGreater(row[3], 0)  # chunks_count
        finally:
            _teardown_isolated_db(original, tmp_dir)


class TestIngestFileDeduplicates(unittest.TestCase):
    """Verify second ingest of same file is detected as unchanged."""

    def test_same_file_returns_none(self):
        from kurukshetra.knowledge.fabric import KnowledgeFabric

        original, tmp_dir = _setup_isolated_db()
        try:
            inbox = tmp_dir / "inbox"
            inbox.mkdir()
            test_file = inbox / "test_document.txt"
            test_file.write_text(SAMPLE_TEXT, encoding="utf-8")

            fabric = KnowledgeFabric()
            try:
                r1 = fabric.ingest_file(test_file)
                r2 = fabric.ingest_file(test_file)
            finally:
                fabric.close()

            self.assertNotEqual(r1.document_id, "")
            self.assertEqual(r1.change_type.value, "new_file")
            self.assertEqual(r2.change_type.value, "none")
            self.assertEqual(r1.document_id, r2.document_id)
        finally:
            _teardown_isolated_db(original, tmp_dir)


class TestIngestFileDetectsChange(unittest.TestCase):
    """Verify changed file gets a version increment."""

    def test_changed_file_gets_new_version(self):
        from kurukshetra.knowledge.fabric import KnowledgeFabric

        original, tmp_dir = _setup_isolated_db()
        try:
            inbox = tmp_dir / "inbox"
            inbox.mkdir()
            test_file = inbox / "test_document.txt"
            test_file.write_text(SAMPLE_TEXT, encoding="utf-8")

            fabric = KnowledgeFabric()
            try:
                r1 = fabric.ingest_file(test_file)
                # Modify the file
                test_file.write_text(
                    "Updated G3 Data Feed Configuration\n\nNew configuration.\n",
                    encoding="utf-8",
                )
                r2 = fabric.ingest_file(test_file)
            finally:
                fabric.close()

            self.assertEqual(r1.change_type.value, "new_file")
            self.assertEqual(r2.change_type.value, "content_changed")

            conn = get_connection()
            versions = conn.execute(
                "SELECT version, is_current FROM document_versions "
                "WHERE document_id = ? ORDER BY is_current DESC",
                (r1.document_id,),
            ).fetchall()
            conn.close()

            self.assertGreaterEqual(len(versions), 2)
            self.assertEqual(versions[0][0], "1.0.1")
            self.assertTrue(versions[0][1])  # is_current
        finally:
            _teardown_isolated_db(original, tmp_dir)


class TestIngestFileNotFound(unittest.TestCase):
    """Verify ingest_file handles missing files gracefully."""

    def test_missing_file_returns_error(self):
        from kurukshetra.knowledge.fabric import KnowledgeFabric

        original, tmp_dir = _setup_isolated_db()
        try:
            inbox = tmp_dir / "inbox"
            inbox.mkdir()
            missing = inbox / "nonexistent.txt"

            fabric = KnowledgeFabric()
            try:
                result = fabric.ingest_file(missing)
            finally:
                fabric.close()

            self.assertEqual(result.document_id, "")
            self.assertIsNotNone(result.error)
            self.assertIn("not found", result.error.lower())
        finally:
            _teardown_isolated_db(original, tmp_dir)


class TestBackfillExistingDocuments(unittest.TestCase):
    """Verify backfill populates document_state and document_versions."""

    def test_backfill_creates_entries(self):
        from kurukshetra.knowledge.fabric import KnowledgeFabric

        original, tmp_dir = _setup_isolated_db()
        try:
            inbox = tmp_dir / "inbox"
            inbox.mkdir()
            test_file = inbox / "test_document.txt"
            test_file.write_text(SAMPLE_TEXT, encoding="utf-8")

            fabric = KnowledgeFabric()
            try:
                result = fabric.ingest_file(test_file)
                doc_id = result.document_id
            finally:
                fabric.close()

            # Delete fabric entries
            conn = get_connection()
            conn.execute("DELETE FROM document_state WHERE document_id = ?", (doc_id,))
            conn.execute("DELETE FROM document_versions WHERE document_id = ?", (doc_id,))
            conn.commit()

            self.assertIsNone(
                conn.execute("SELECT 1 FROM document_state WHERE document_id = ?", (doc_id,)).fetchone()
            )
            conn.close()

            # Run backfill
            fabric2 = KnowledgeFabric()
            try:
                summary = fabric2.backfill_existing_documents()
            finally:
                fabric2.close()

            self.assertGreaterEqual(summary["backfilled"], 1)

            conn = get_connection()
            self.assertIsNotNone(
                conn.execute("SELECT 1 FROM document_state WHERE document_id = ?", (doc_id,)).fetchone()
            )
            self.assertIsNotNone(
                conn.execute("SELECT 1 FROM document_versions WHERE document_id = ?", (doc_id,)).fetchone()
            )
            conn.close()
        finally:
            _teardown_isolated_db(original, tmp_dir)


class TestConceptTeamsPopulated(unittest.TestCase):
    """Verify concept_teams is populated when entities exist."""

    def test_concept_teams_after_ingest(self):
        from datetime import datetime
        from kurukshetra.knowledge.fabric import KnowledgeFabric

        original, tmp_dir = _setup_isolated_db()
        try:
            inbox = tmp_dir / "inbox"
            inbox.mkdir()
            test_file = inbox / "test_document.txt"
            test_file.write_text(SAMPLE_TEXT, encoding="utf-8")

            fabric = KnowledgeFabric()
            try:
                result = fabric.ingest_file(test_file)
            finally:
                fabric.close()

            self.assertNotEqual(result.document_id, "")

            # Manually insert a graph entity and evidence to simulate extraction
            conn = get_connection()
            conn.execute(
                "INSERT OR IGNORE INTO graph_entities "
                "(id, name, entity_type, description, metadata, owner, visibility) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("TEST-ENT-001", "G3 RMS", "system", "test", "{}",
                 result.document_id, "Internal"),
            )
            conn.execute(
                "INSERT OR IGNORE INTO graph_evidence "
                "(evidence_id, entity_id, source_document, source_text, confidence) "
                "VALUES (?, ?, ?, ?, ?)",
                ("EVD-TEST-001", "TEST-ENT-001", result.document_id,
                 "G3 RMS test evidence", 0.8),
            )
            conn.commit()
            conn.close()

            # Run concept tracking
            fabric2 = KnowledgeFabric()
            try:
                fabric2._track_concepts(result.document_id, "SPM", True)
            finally:
                fabric2.close()

            # Verify concept_teams (query by entity name, lowercased)
            conn = get_connection()
            rows = conn.execute(
                "SELECT concept_name, team_id FROM concept_teams "
                "WHERE concept_name = ?",
                ("g3 rms",),
            ).fetchall()
            conn.close()

            self.assertGreater(len(rows), 0, "concept_teams must have entries for G3 RMS")
            teams = [r[1] for r in rows]
            self.assertIn("SPM", teams)
        finally:
            _teardown_isolated_db(original, tmp_dir)


class TestEmptyFileSafe(unittest.TestCase):
    """Verify empty or minimal files are handled safely."""

    def test_empty_file_ingested(self):
        from kurukshetra.knowledge.fabric import KnowledgeFabric

        original, tmp_dir = _setup_isolated_db()
        try:
            inbox = tmp_dir / "inbox"
            inbox.mkdir()
            empty = inbox / "empty.txt"
            empty.write_text("", encoding="utf-8")

            fabric = KnowledgeFabric()
            try:
                result = fabric.ingest_file(empty)
            finally:
                fabric.close()

            self.assertIsNotNone(result)
        finally:
            _teardown_isolated_db(original, tmp_dir)


if __name__ == "__main__":
    unittest.main()
