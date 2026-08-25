"""Tests for KnowledgeFabric — continuous knowledge maintenance layer."""
from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

from kurukshetra.knowledge.fabric import (
    ChangeDetection,
    ChangeType,
    ConflictRecord,
    ConflictType,
    ConceptTeamAssociation,
    DocumentFingerprint,
    DocumentState,
    FabricIngestResult,
    FabricScanResult,
    KnowledgeFabric,
    KnowledgeState,
    VersionRecord,
    _bump_version,
)


class TestDocumentState(unittest.TestCase):
    """Test DocumentState enum values."""

    def test_all_states_exist(self):
        states = [s.value for s in DocumentState]
        self.assertIn("new", states)
        self.assertIn("indexed", states)
        self.assertIn("changed", states)
        self.assertIn("removed", states)
        self.assertIn("conflict", states)
        self.assertIn("stale", states)


class TestChangeType(unittest.TestCase):
    """Test ChangeType enum values."""

    def test_all_types_exist(self):
        types = [t.value for t in ChangeType]
        self.assertIn("none", types)
        self.assertIn("new_file", types)
        self.assertIn("content_changed", types)
        self.assertIn("removed", types)


class TestConflictType(unittest.TestCase):
    """Test ConflictType enum values."""

    def test_all_types_exist(self):
        types = [t.value for t in ConflictType]
        self.assertIn("team_mismatch", types)
        self.assertIn("version_conflict", types)


class TestVersionBump(unittest.TestCase):
    """Test version bumping logic."""

    def test_bump_patch(self):
        self.assertEqual(_bump_version(("1.0.0",)), "1.0.1")

    def test_bump_major(self):
        self.assertEqual(_bump_version(("2.3.9",)), "2.3.10")

    def test_bump_none(self):
        self.assertEqual(_bump_version(None), "1.0.0")

    def test_bump_invalid(self):
        self.assertEqual(_bump_version(("abc",)), "1.0.1")


class TestKnowledgeFabricTables(unittest.TestCase):
    """Test that KnowledgeFabric creates required tables."""

    def setUp(self):
        self.fabric = KnowledgeFabric()

    def tearDown(self):
        self.fabric.close()

    def test_document_state_table_exists(self):
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        cols = conn.execute("PRAGMA table_info(document_state)").fetchall()
        col_names = [c[1] for c in cols]
        conn.close()
        self.assertIn("document_id", col_names)
        self.assertIn("sha256", col_names)
        self.assertIn("state", col_names)
        self.assertIn("version", col_names)
        self.assertIn("team_ids", col_names)

    def test_document_versions_table_exists(self):
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        cols = conn.execute("PRAGMA table_info(document_versions)").fetchall()
        col_names = [c[1] for c in cols]
        conn.close()
        self.assertIn("document_id", col_names)
        self.assertIn("version", col_names)
        self.assertIn("is_current", col_names)

    def test_concept_teams_table_exists(self):
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        cols = conn.execute("PRAGMA table_info(concept_teams)").fetchall()
        col_names = [c[1] for c in cols]
        conn.close()
        self.assertIn("concept_name", col_names)
        self.assertIn("team_id", col_names)
        self.assertIn("association_type", col_names)

    def test_knowledge_conflicts_table_exists(self):
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        cols = conn.execute("PRAGMA table_info(knowledge_conflicts)").fetchall()
        col_names = [c[1] for c in cols]
        conn.close()
        self.assertIn("conflict_id", col_names)
        self.assertIn("conflict_type", col_names)
        self.assertIn("resolved", col_names)


class TestKnowledgeFabricScan(unittest.TestCase):
    """Test source directory scanning."""

    def setUp(self):
        self.fabric = KnowledgeFabric()
        self.tmpdir = tempfile.mkdtemp()
        self.source = Path(self.tmpdir) / "test_source"
        self.source.mkdir()
        # Clean fabric tables for isolation
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        for t in ['document_state', 'fabric_scans', 'document_versions', 'concept_teams']:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()

    def tearDown(self):
        self.fabric.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_scan_empty_directory(self):
        result = self.fabric.scan_source(str(self.source))
        self.assertEqual(result.files_found, 0)
        self.assertEqual(result.new_files, 0)
        self.assertEqual(result.changed_files, 0)

    def test_scan_nonexistent_directory(self):
        result = self.fabric.scan_source("/nonexistent/path")
        self.assertEqual(result.files_found, 0)
        self.assertTrue(len(result.errors) > 0)

    def test_scan_finds_supported_files(self):
        # Create test files
        (self.source / "test.txt").write_text("hello world")
        (self.source / "test.md").write_text("# Title")
        (self.source / "test.pdf").write_bytes(b"%PDF-1.4 fake")
        (self.source / "test.xyz").write_text("unsupported")

        result = self.fabric.scan_source(str(self.source))
        self.assertEqual(result.files_found, 3)  # txt, md, pdf
        self.assertEqual(result.new_files, 3)  # all new (state table is empty)

    def test_scan_detects_duplicates(self):
        (self.source / "a.txt").write_text("content")
        result = self.fabric.scan_source(str(self.source))
        self.assertEqual(result.new_files, 1)

        # Ingest the file to populate document_state
        for change in result.changes:
            self.fabric.ingest_change(change)

        # Scan again — should be unchanged
        result2 = self.fabric.scan_source(str(self.source))
        self.assertEqual(result2.unchanged_files, 1)
        self.assertEqual(result2.new_files, 0)

    def test_scan_detects_content_change(self):
        (self.source / "doc.txt").write_text("version 1")
        scan1 = self.fabric.scan_source(str(self.source))

        # Ingest to populate state
        for change in scan1.changes:
            self.fabric.ingest_change(change)

        # Modify file
        (self.source / "doc.txt").write_text("version 2")
        result = self.fabric.scan_source(str(self.source))
        self.assertEqual(result.changed_files, 1)
        self.assertEqual(result.new_files, 0)

    def test_scan_records_history(self):
        self.fabric.scan_source(str(self.source))
        self.fabric.scan_source(str(self.source))
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        count = conn.execute("SELECT COUNT(*) FROM fabric_scans").fetchone()[0]
        conn.close()
        self.assertGreaterEqual(count, 2)


class TestKnowledgeFabricIngest(unittest.TestCase):
    """Test incremental ingestion."""

    def setUp(self):
        self.fabric = KnowledgeFabric()
        self.tmpdir = tempfile.mkdtemp()
        self.source = Path(self.tmpdir) / "test_source"
        self.source.mkdir()
        # Clean fabric tables for isolation
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        for t in ['document_state', 'document_versions', 'concept_teams', 'fabric_scans']:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()

    def tearDown(self):
        self.fabric.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_ingest_new_file(self):
        test_file = self.source / "test_doc.txt"
        test_file.write_text("This is a test document about G3 RMS configuration.")

        change = ChangeDetection(
            change_type=ChangeType.NEW_FILE,
            document_id="",
            source_path=str(test_file),
            new_sha256="abc123",
        )

        result = self.fabric.ingest_change(change)
        self.assertIsNotNone(result.document_id)
        self.assertEqual(result.change_type, ChangeType.NEW_FILE)
        self.assertGreater(result.chunks_stored, 0)

    def test_ingest_skips_unchanged(self):
        change = ChangeDetection(
            change_type=ChangeType.NONE,
            document_id="DOC-TEST",
            source_path="/fake/path",
        )
        result = self.fabric.ingest_change(change)
        self.assertEqual(result.change_type, ChangeType.NONE)

    def test_ingest_marks_removed(self):
        # First insert a state entry
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        conn.execute(
            """INSERT OR REPLACE INTO document_state
            (document_id, source_path, sha256, state, version)
            VALUES (?, ?, ?, ?, ?)""",
            ("DOC-TEST", "/fake/path", "abc", "indexed", "1.0.0"),
        )
        conn.close()

        change = ChangeDetection(
            change_type=ChangeType.REMOVED,
            document_id="DOC-TEST",
            source_path="/fake/path",
        )
        result = self.fabric.ingest_change(change)
        self.assertEqual(result.change_type, ChangeType.REMOVED)

        # Verify state is updated
        conn = get_connection()
        row = conn.execute(
            "SELECT state FROM document_state WHERE document_id = ?",
            ("DOC-TEST",),
        ).fetchone()
        conn.close()
        self.assertEqual(row[0], "removed")


class TestMultiTeamConcepts(unittest.TestCase):
    """Test multi-team concept tracking."""

    def setUp(self):
        self.fabric = KnowledgeFabric()
        # Clean fabric tables
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        for t in ['concept_teams', 'knowledge_conflicts', 'document_state', 'document_versions']:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()

    def tearDown(self):
        self.fabric.close()

    def test_add_concept_team(self):
        self.fabric.add_concept_team(
            "G3 RMS", "system", "spm", "owner", 0.9, "DOC-001"
        )
        teams = self.fabric.get_concept_teams("G3 RMS")
        self.assertEqual(len(teams), 1)
        self.assertEqual(teams[0]["team_id"], "spm")
        self.assertEqual(teams[0]["association_type"], "owner")

    def test_multi_team_association(self):
        self.fabric.add_concept_team(
            "G3 RMS", "system", "spm", "owner", 0.9, "DOC-001"
        )
        self.fabric.add_concept_team(
            "G3 RMS", "system", "ics", "supporting", 0.7, "DOC-002"
        )
        teams = self.fabric.get_concept_teams("G3 RMS")
        self.assertEqual(len(teams), 2)
        team_ids = {t["team_id"] for t in teams}
        self.assertIn("spm", team_ids)
        self.assertIn("ics", team_ids)

    def test_concept_team_update_higher_confidence(self):
        self.fabric.add_concept_team(
            "G3 RMS", "system", "spm", "associated", 0.5, "DOC-001"
        )
        self.fabric.add_concept_team(
            "G3 RMS", "system", "spm", "owner", 0.9, "DOC-002"
        )
        teams = self.fabric.get_concept_teams("G3 RMS")
        self.assertEqual(len(teams), 1)  # Should update, not duplicate
        self.assertAlmostEqual(teams[0]["confidence"], 0.9, places=1)


class TestConflictDetection(unittest.TestCase):
    """Test conflict detection."""

    def setUp(self):
        self.fabric = KnowledgeFabric()
        # Clean fabric tables
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        for t in ['concept_teams', 'knowledge_conflicts']:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()

    def tearDown(self):
        self.fabric.close()

    def test_no_conflict_single_team(self):
        self.fabric.add_concept_team(
            "TestEntity", "system", "spm", "owner", 0.9, "DOC-001"
        )
        conflicts = self.fabric.detect_conflicts("TestEntity")
        self.assertEqual(len(conflicts), 0)

    def test_team_mismatch_conflict(self):
        self.fabric.add_concept_team(
            "TestEntity", "system", "spm", "owner", 0.9, "DOC-001"
        )
        self.fabric.add_concept_team(
            "TestEntity", "system", "ics", "owner", 0.8, "DOC-002"
        )
        conflicts = self.fabric.detect_conflicts("TestEntity")
        self.assertGreater(len(conflicts), 0)
        self.assertEqual(conflicts[0].conflict_type, ConflictType.TEAM_MISMATCH)


class TestKnowledgeState(unittest.TestCase):
    """Test knowledge state API."""

    def setUp(self):
        self.fabric = KnowledgeFabric()

    def tearDown(self):
        self.fabric.close()

    def test_get_knowledge_state(self):
        state = self.fabric.get_knowledge_state()
        self.assertIsInstance(state, KnowledgeState)
        self.assertGreater(state.total_documents, 0)
        self.assertGreater(state.total_chunks, 0)

    def test_state_has_required_fields(self):
        state = self.fabric.get_knowledge_state()
        self.assertIsNotNone(state.teams_represented)
        self.assertIsNotNone(state.documents_by_state)
        self.assertIsNotNone(state.recent_changes)
        self.assertIsNotNone(state.active_conflicts)


class TestDocumentHistory(unittest.TestCase):
    """Test document version history."""

    def setUp(self):
        self.fabric = KnowledgeFabric()
        self.tmpdir = tempfile.mkdtemp()
        self.source = Path(self.tmpdir) / "test_source"
        self.source.mkdir()
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        for t in ['document_state', 'document_versions', 'concept_teams']:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()

    def tearDown(self):
        self.fabric.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_version_recorded_on_ingest(self):
        test_file = self.source / "versioned_doc.txt"
        test_file.write_text("Version 1 of the document.")

        change = ChangeDetection(
            change_type=ChangeType.NEW_FILE,
            document_id="",
            source_path=str(test_file),
        )
        result = self.fabric.ingest_change(change)

        history = self.fabric.get_document_history(result.document_id)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["version"], "1.0.0")
        self.assertTrue(history[0]["is_current"])


class TestEndToEndFabricFlow(unittest.TestCase):
    """End-to-end test: scan → detect → ingest → state."""

    def setUp(self):
        self.fabric = KnowledgeFabric()
        self.tmpdir = tempfile.mkdtemp()
        self.source = Path(self.tmpdir) / "e2e_source"
        self.source.mkdir()
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        for t in ['document_state', 'document_versions', 'concept_teams', 'fabric_scans']:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()

    def tearDown(self):
        self.fabric.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_full_cycle(self):
        # 1. Create initial documents
        (self.source / "doc1.txt").write_text("G3 RMS Data Feed Configuration.")
        (self.source / "doc2.txt").write_text("Property Merge-Split Workflow.")

        # 2. Scan — should detect 2 new files
        scan1 = self.fabric.scan_source(str(self.source))
        self.assertEqual(scan1.new_files, 2)
        self.assertEqual(scan1.changed_files, 0)

        # 3. Ingest new files
        for change in scan1.changes:
            result = self.fabric.ingest_change(change)
            self.assertIsNotNone(result.document_id)

        # 4. Scan again — should be unchanged
        scan2 = self.fabric.scan_source(str(self.source))
        self.assertEqual(scan2.unchanged_files, 2)
        self.assertEqual(scan2.new_files, 0)

        # 5. Modify a file
        (self.source / "doc1.txt").write_text("G3 RMS Data Feed Configuration v2.")

        # 6. Scan — should detect 1 change
        scan3 = self.fabric.scan_source(str(self.source))
        self.assertEqual(scan3.changed_files, 1)
        self.assertEqual(scan3.unchanged_files, 1)

        # 7. Ingest change
        for change in scan3.changes:
            if change.change_type == ChangeType.CONTENT_CHANGED:
                result = self.fabric.ingest_change(change)
                self.assertEqual(result.change_type, ChangeType.CONTENT_CHANGED)

        # 8. Check knowledge state
        state = self.fabric.get_knowledge_state()
        self.assertGreater(state.total_documents, 0)

        # 9. Check version history
        # Get a document_id from state
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        doc_id = conn.execute(
            "SELECT document_id FROM document_state LIMIT 1"
        ).fetchone()
        conn.close()
        if doc_id:
            history = self.fabric.get_document_history(doc_id[0])
            self.assertGreater(len(history), 0)


if __name__ == "__main__":
    unittest.main()
