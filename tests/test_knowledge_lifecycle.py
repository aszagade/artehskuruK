"""Tests for KnowledgeWatcher — continuous runtime refresh lifecycle."""
from __future__ import annotations

import shutil
import tempfile
import time
import unittest
from pathlib import Path

from kurukshetra.knowledge.fabric import (
    ChangeType,
    DocumentState,
    KnowledgeFabric,
)
from kurukshetra.runtime.knowledge_watcher import KnowledgeWatcher, WatcherResult


class TestKnowledgeWatcherScan(unittest.TestCase):
    """Test KnowledgeWatcher scanning behavior."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.source = Path(self.tmpdir) / "source"
        self.source.mkdir()
        self.inbox = Path(self.tmpdir) / "inbox"
        self.inbox.mkdir()
        self.processed = Path(self.tmpdir) / "processed"
        self.failed = Path(self.tmpdir) / "failed"

        # Clean fabric tables
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        for t in ['document_state', 'document_versions', 'concept_teams', 'fabric_scans']:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()

        self.watcher = KnowledgeWatcher(
            source_dirs=[str(self.source)],
            inbox_dir=str(self.inbox),
            processed_dir=str(self.processed),
            failed_dir=str(self.failed),
        )

    def tearDown(self):
        self.watcher.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_scan_detects_new_files(self):
        (self.source / "doc1.txt").write_text("G3 RMS configuration guide.")
        result = self.watcher.scan_and_ingest()
        self.assertEqual(result.new_documents, 1)
        self.assertGreater(result.ingest_results[0].chunks_stored, 0)

    def test_scan_no_changes(self):
        result = self.watcher.scan_and_ingest()
        self.assertEqual(result.new_documents, 0)
        self.assertEqual(result.changed_documents, 0)

    def test_scan_detects_multiple_new_files(self):
        (self.source / "doc1.txt").write_text("Document one.")
        (self.source / "doc2.txt").write_text("Document two.")
        (self.source / "doc3.md").write_text("# Document three")
        result = self.watcher.scan_and_ingest()
        self.assertEqual(result.new_documents, 3)


class TestKnowledgeWatcherChangeDetection(unittest.TestCase):
    """Test change detection through the watcher."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.source = Path(self.tmpdir) / "source"
        self.source.mkdir()
        self.inbox = Path(self.tmpdir) / "inbox"
        self.inbox.mkdir()
        self.processed = Path(self.tmpdir) / "processed"
        self.failed = Path(self.tmpdir) / "failed"

        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        for t in ['document_state', 'document_versions', 'concept_teams', 'fabric_scans']:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()

        self.watcher = KnowledgeWatcher(
            source_dirs=[str(self.source)],
            inbox_dir=str(self.inbox),
            processed_dir=str(self.processed),
            failed_dir=str(self.failed),
        )

    def tearDown(self):
        self.watcher.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_duplicate_ingestion_prevented(self):
        (self.source / "doc.txt").write_text("content v1")
        result1 = self.watcher.scan_and_ingest()
        self.assertEqual(result1.new_documents, 1)

        # Scan again without changes
        result2 = self.watcher.scan_and_ingest()
        self.assertEqual(result2.new_documents, 0)
        self.assertEqual(result2.changed_documents, 0)

    def test_content_change_detected(self):
        (self.source / "doc.txt").write_text("content v1")
        self.watcher.scan_and_ingest()

        # Modify file
        (self.source / "doc.txt").write_text("content v2 - updated")
        result = self.watcher.scan_and_ingest()
        self.assertEqual(result.changed_documents, 1)

    def test_removal_detected(self):
        (self.source / "doc.txt").write_text("content")
        self.watcher.scan_and_ingest()

        # Remove file
        (self.source / "doc.txt").unlink()
        result = self.watcher.scan_and_ingest()
        self.assertEqual(result.removed_documents, 1)


class TestMultiTeamConcepts(unittest.TestCase):
    """Test multi-team concept tracking through the watcher."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.source = Path(self.tmpdir) / "source"
        self.source.mkdir()
        self.inbox = Path(self.tmpdir) / "inbox"
        self.inbox.mkdir()
        self.processed = Path(self.tmpdir) / "processed"
        self.failed = Path(self.tmpdir) / "failed"

        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        for t in ['document_state', 'document_versions', 'concept_teams', 'fabric_scans']:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()

        self.watcher = KnowledgeWatcher(
            source_dirs=[str(self.source)],
            inbox_dir=str(self.inbox),
            processed_dir=str(self.processed),
            failed_dir=str(self.failed),
        )

    def tearDown(self):
        self.watcher.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_concept_team_tracking(self):
        # Ingest a document
        (self.source / "g3_doc.txt").write_text(
            "G3 RMS Data Feed Configuration Guide. "
            "The G3 RMS system uses SFTP for data transfer."
        )
        result = self.watcher.scan_and_ingest()
        self.assertEqual(result.new_documents, 1)

        # Verify document state is tracked
        state = self.watcher.get_knowledge_state()
        self.assertIn("indexed", state["documents_by_state"])
        self.assertGreater(state["total_documents"], 0)


class TestVersionTracking(unittest.TestCase):
    """Test version history through the watcher."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.source = Path(self.tmpdir) / "source"
        self.source.mkdir()
        self.inbox = Path(self.tmpdir) / "inbox"
        self.inbox.mkdir()
        self.processed = Path(self.tmpdir) / "processed"
        self.failed = Path(self.tmpdir) / "failed"

        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        for t in ['document_state', 'document_versions', 'concept_teams', 'fabric_scans']:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()

        self.watcher = KnowledgeWatcher(
            source_dirs=[str(self.source)],
            inbox_dir=str(self.inbox),
            processed_dir=str(self.processed),
            failed_dir=str(self.failed),
        )

    def tearDown(self):
        self.watcher.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_version_created_on_ingest(self):
        (self.source / "doc.txt").write_text("version 1")
        result = self.watcher.scan_and_ingest()
        doc_id = result.ingest_results[0].document_id

        # Check version history
        history = self.watcher.fabric.get_document_history(doc_id)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["version"], "1.0.0")

    def test_version_bumped_on_change(self):
        (self.source / "doc.txt").write_text("version 1")
        result1 = self.watcher.scan_and_ingest()
        doc_id = result1.ingest_results[0].document_id

        # Modify file
        (self.source / "doc.txt").write_text("version 2 - updated content")
        result2 = self.watcher.scan_and_ingest()

        # Check version history
        history = self.watcher.fabric.get_document_history(doc_id)
        self.assertEqual(len(history), 2)
        self.assertTrue(history[0]["is_current"])  # New version is current
        self.assertFalse(history[1]["is_current"])  # Old version is not current


class TestRetrievalExclusion(unittest.TestCase):
    """Test that removed documents are no longer retrieved."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.source = Path(self.tmpdir) / "source"
        self.source.mkdir()
        self.inbox = Path(self.tmpdir) / "inbox"
        self.inbox.mkdir()
        self.processed = Path(self.tmpdir) / "processed"
        self.failed = Path(self.tmpdir) / "failed"

        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        for t in ['document_state', 'document_versions', 'concept_teams', 'fabric_scans']:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()

        self.watcher = KnowledgeWatcher(
            source_dirs=[str(self.source)],
            inbox_dir=str(self.inbox),
            processed_dir=str(self.processed),
            failed_dir=str(self.failed),
        )

    def tearDown(self):
        self.watcher.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_removed_doc_state_updated(self):
        (self.source / "doc.txt").write_text("QuantumBridge is a system.")
        result1 = self.watcher.scan_and_ingest()
        doc_id = result1.ingest_results[0].document_id

        # Verify document is indexed
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        state = conn.execute(
            "SELECT state FROM document_state WHERE document_id = ?",
            (doc_id,),
        ).fetchone()
        conn.close()
        self.assertEqual(state[0], "indexed")

        # Remove file
        (self.source / "doc.txt").unlink()
        result2 = self.watcher.scan_and_ingest()
        self.assertEqual(result2.removed_documents, 1)

        # Verify state is updated to removed
        conn = get_connection()
        state = conn.execute(
            "SELECT state FROM document_state WHERE document_id = ?",
            (doc_id,),
        ).fetchone()
        conn.close()
        self.assertEqual(state[0], "removed")


class TestKnowledgeState(unittest.TestCase):
    """Test knowledge state reflects live changes."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.source = Path(self.tmpdir) / "source"
        self.source.mkdir()
        self.inbox = Path(self.tmpdir) / "inbox"
        self.inbox.mkdir()
        self.processed = Path(self.tmpdir) / "processed"
        self.failed = Path(self.tmpdir) / "failed"

        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        for t in ['document_state', 'document_versions', 'concept_teams', 'fabric_scans']:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()

        self.watcher = KnowledgeWatcher(
            source_dirs=[str(self.source)],
            inbox_dir=str(self.inbox),
            processed_dir=str(self.processed),
            failed_dir=str(self.failed),
        )

    def tearDown(self):
        self.watcher.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_state_reflects_ingestion(self):
        # Ingest a document
        (self.source / "doc.txt").write_text("New knowledge.")
        result = self.watcher.scan_and_ingest()
        self.assertEqual(result.new_documents, 1)

        # Verify document_state table has the new entry
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        count = conn.execute("SELECT COUNT(*) FROM document_state").fetchone()[0]
        conn.close()
        self.assertGreater(count, 0)

    def test_state_reflects_removal(self):
        (self.source / "doc.txt").write_text("Temporary knowledge.")
        self.watcher.scan_and_ingest()

        state1 = self.watcher.get_knowledge_state()
        docs_before = state1["total_documents"]

        # Remove file
        (self.source / "doc.txt").unlink()
        self.watcher.scan_and_ingest()

        # State should reflect removal
        state2 = self.watcher.get_knowledge_state()
        self.assertLessEqual(state2["total_documents"], docs_before)


class TestCacheRefresh(unittest.TestCase):
    """Test that caches are refreshed after ingestion."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.source = Path(self.tmpdir) / "source"
        self.source.mkdir()
        self.inbox = Path(self.tmpdir) / "inbox"
        self.inbox.mkdir()
        self.processed = Path(self.tmpdir) / "processed"
        self.failed = Path(self.tmpdir) / "failed"

        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        for t in ['document_state', 'document_versions', 'concept_teams', 'fabric_scans']:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()

        self.watcher = KnowledgeWatcher(
            source_dirs=[str(self.source)],
            inbox_dir=str(self.inbox),
            processed_dir=str(self.processed),
            failed_dir=str(self.failed),
        )

    def tearDown(self):
        self.watcher.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_cache_refreshed_after_ingestion(self):
        (self.source / "doc.txt").write_text("New content.")
        result = self.watcher.scan_and_ingest()
        self.assertTrue(result.cache_refreshed)

    def test_cache_not_refreshed_when_no_changes(self):
        result = self.watcher.scan_and_ingest()
        self.assertFalse(result.cache_refreshed)


class TestEndToEndLifecycle(unittest.TestCase):
    """End-to-end lifecycle: new → version → remove."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.source = Path(self.tmpdir) / "source"
        self.source.mkdir()
        self.inbox = Path(self.tmpdir) / "inbox"
        self.inbox.mkdir()
        self.processed = Path(self.tmpdir) / "processed"
        self.failed = Path(self.tmpdir) / "failed"

        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        for t in ['document_state', 'document_versions', 'concept_teams', 'fabric_scans']:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()

        self.watcher = KnowledgeWatcher(
            source_dirs=[str(self.source)],
            inbox_dir=str(self.inbox),
            processed_dir=str(self.processed),
            failed_dir=str(self.failed),
        )

    def tearDown(self):
        self.watcher.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_full_lifecycle(self):
        # 1. Ingest new document
        (self.source / "lifecycle_doc.txt").write_text(
            "G3 RMS Data Feed Configuration. Uses SFTP for transfer."
        )
        result1 = self.watcher.scan_and_ingest()
        self.assertEqual(result1.new_documents, 1)
        self.assertTrue(result1.cache_refreshed)
        doc_id = result1.ingest_results[0].document_id

        # 2. Verify document is in knowledge state
        state1 = self.watcher.get_knowledge_state()
        self.assertIn("indexed", state1["documents_by_state"])

        # 3. Verify version history
        history1 = self.watcher.fabric.get_document_history(doc_id)
        self.assertEqual(len(history1), 1)

        # 4. Modify document
        (self.source / "lifecycle_doc.txt").write_text(
            "G3 RMS Data Feed Configuration v2. Updated SFTP process."
        )
        result2 = self.watcher.scan_and_ingest()
        self.assertEqual(result2.changed_documents, 1)

        # 5. Verify version bumped
        history2 = self.watcher.fabric.get_document_history(doc_id)
        self.assertEqual(len(history2), 2)

        # 6. Remove document
        (self.source / "lifecycle_doc.txt").unlink()
        result3 = self.watcher.scan_and_ingest()
        self.assertEqual(result3.removed_documents, 1)

        # 7. Verify state is removed
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        state = conn.execute(
            "SELECT state FROM document_state WHERE document_id = ?",
            (doc_id,),
        ).fetchone()
        conn.close()
        self.assertEqual(state[0], "removed")


if __name__ == "__main__":
    unittest.main()
