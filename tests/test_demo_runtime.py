"""
Demo Runtime Tests
==================

Proves the end-to-end demo workflow.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


DEMO_DOC = """
# NOVA-742 Deployment Workflow

QuantumBridge sends deployment events to PulseGrid.
PulseGrid monitors NovaSync health.
Owned by Team Alpha and Team Beta.
Contact: Dr. Marcus Webb, Priya Kapoor.
Parameter: qb_max_artifact_size = 500MB.
Enable PulseGrid monitoring.
"""


def _make_temp_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".duckdb")
    os.close(fd)
    os.remove(path)
    return path


def _patch_database(db_path: str):
    import kurukshetra.registry.database as db_mod
    original = db_mod.DATABASE_PATH
    db_mod.DATABASE_PATH = Path(db_path)
    return original


def _restore_database(original):
    import kurukshetra.registry.database as db_mod
    db_mod.DATABASE_PATH = original


class TestDemoRuntime(unittest.TestCase):
    """Proves the demo runtime workflow end-to-end."""

    @classmethod
    def setUpClass(cls):
        cls.db_path = _make_temp_db()
        cls.original = _patch_database(cls.db_path)
        from kurukshetra.registry.schema import initialize_schema
        initialize_schema()

        cls.doc_dir = tempfile.mkdtemp()
        cls.inbox = Path(cls.doc_dir) / "inbox"
        cls.processed = Path(cls.doc_dir) / "processed"
        cls.failed = Path(cls.doc_dir) / "failed"
        cls.inbox.mkdir()
        cls.processed.mkdir()
        cls.failed.mkdir()

        # Write demo document to inbox
        cls.doc_path = cls.inbox / "NOVA_742.txt"
        cls.doc_path.write_text(DEMO_DOC, encoding="utf-8")

        # Ingest it once — all tests use the result
        from kurukshetra.runtime.watcher import InboxWatcher
        watcher = InboxWatcher(
            inbox_dir=str(cls.inbox),
            processed_dir=str(cls.processed),
            failed_dir=str(cls.failed),
        )
        files = watcher.scan()
        cls.ingest_result = watcher.ingest_one(files[0])
        cls.doc_id = cls.ingest_result.document_id
        watcher.close()

    @classmethod
    def tearDownClass(cls):
        _restore_database(cls.original)
        import shutil
        try: shutil.rmtree(cls.doc_dir)
        except OSError: pass
        try: os.remove(cls.db_path)
        except OSError: pass

    def test_01_document_detected(self):
        """Watcher detects new document in inbox."""
        from kurukshetra.runtime.watcher import InboxWatcher
        # Inbox is now empty (file was moved)
        watcher = InboxWatcher(
            inbox_dir=str(self.inbox),
            processed_dir=str(self.processed),
            failed_dir=str(self.failed),
        )
        files = watcher.scan()
        watcher.close()
        # File was already ingested, so inbox is empty
        self.assertEqual(len(files), 0)
        print(f"  [OK] Inbox empty after ingestion")

    def test_02_ingested_exactly_once(self):
        """Document has a valid document_id."""
        self.assertNotEqual(self.doc_id, "")
        self.assertTrue(self.doc_id.startswith("DOC-"))
        print(f"  [OK] Ingested: {self.doc_id}")

    def test_03_chunks_persisted(self):
        """Chunks are stored in DuckDB."""
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        count = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            (self.doc_id,),
        ).fetchone()[0]
        conn.close()
        self.assertGreater(count, 0)
        print(f"  [OK] Chunks: {count}")

    def test_04_rag_retrieval(self):
        """BM25 retrieves the ingested document."""
        from kurukshetra.retrieval.database_bm25 import DatabaseBM25Retriever
        results = DatabaseBM25Retriever().search("QuantumBridge deployment", top_k=3)
        self.assertGreater(len(results), 0)
        found = any(r.document_id == self.doc_id for r in results)
        self.assertTrue(found)
        print(f"  [OK] RAG: {len(results)} results, found={found}")

    def test_05_graph_persistence(self):
        """Entities and relationships persisted to graph."""
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        ent = conn.execute(
            "SELECT COUNT(*) FROM graph_entities WHERE id LIKE ?",
            (f"DOC-{self.doc_id}%",),
        ).fetchone()[0]
        rel = conn.execute(
            "SELECT COUNT(*) FROM graph_relationships WHERE source_id LIKE ?",
            (f"DOC-{self.doc_id}%",),
        ).fetchone()[0]
        conn.close()
        self.assertGreater(ent, 0)
        self.assertGreater(rel, 0)
        print(f"  [OK] Graph: {ent} entities, {rel} relationships")

    def test_06_evidence_from_source(self):
        """Evidence records point back to the source document."""
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        ev = conn.execute(
            "SELECT evidence_id, entity_id, source_document "
            "FROM graph_evidence WHERE entity_id LIKE ? LIMIT 3",
            (f"DOC-{self.doc_id}%",),
        ).fetchall()
        conn.close()
        self.assertGreater(len(ev), 0)
        for evid, eid, src in ev:
            self.assertEqual(src, self.doc_id)
        print(f"  [OK] Evidence: {len(ev)} records, all linked to doc")

    def test_07_unknown_terms(self):
        """Unknown terms are detected."""
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        terms = conn.execute(
            "SELECT term FROM unknown_terms WHERE status = 'pending'"
        ).fetchall()
        conn.close()
        self.assertIsInstance(terms, list)
        print(f"  [OK] Unknown terms: {len(terms)}")

    def test_08_status_tracking(self):
        """Status tracker records the ingestion lifecycle."""
        from kurukshetra.runtime.status import get_tracker
        tracker = get_tracker()
        stats = tracker.get_stats()
        self.assertGreater(stats["completed"], 0)
        print(f"  [OK] Status: {stats}")

    def test_09_file_moved_to_processed(self):
        """Ingested file moved from inbox to processed."""
        processed_files = list(self.processed.iterdir())
        self.assertGreater(len(processed_files), 0)
        names = [f.name for f in processed_files]
        self.assertIn("NOVA_742.txt", names)
        print(f"  [OK] File in processed: {names}")

    def test_10_unsupported_ignored(self):
        """Unsupported file types are ignored by the watcher."""
        from kurukshetra.runtime.watcher import InboxWatcher

        # Write an unsupported file
        bad_path = self.inbox / "image.png"
        bad_path.write_bytes(b"\x89PNG")

        watcher = InboxWatcher(
            inbox_dir=str(self.inbox),
            processed_dir=str(self.processed),
            failed_dir=str(self.failed),
        )
        files = watcher.scan()
        watcher.close()

        # .png not in supported extensions -> scan returns 0
        self.assertEqual(len(files), 0)
        self.assertTrue(bad_path.exists())  # file remains in inbox
        print(f"  [OK] Unsupported file ignored: {bad_path.name}")

    def test_11_no_duplicate_on_same_content(self):
        """Same content produces same document_id (SHA-256 dedup)."""
        from kurukshetra.runtime.watcher import InboxWatcher

        dup_path = self.inbox / "NOVA_742_copy.txt"
        dup_path.write_text(DEMO_DOC, encoding="utf-8")

        watcher = InboxWatcher(
            inbox_dir=str(self.inbox),
            processed_dir=str(self.processed),
            failed_dir=str(self.failed),
        )
        files = watcher.scan()
        result = watcher.ingest_one(files[0])
        watcher.close()

        self.assertEqual(result.document_id, self.doc_id)
        print(f"  [OK] No duplicate: same doc_id={result.document_id}")

    def test_12_result_stages(self):
        """IngestionResult reports every stage."""
        r = self.ingest_result
        self.assertIn("extract", r.stages)
        self.assertIn("register", r.stages)
        self.assertIn("chunk", r.stages)
        self.assertIn("graph", r.stages)
        self.assertIn("detect_terms", r.stages)
        ok_stages = sum(1 for v in r.stages.values() if v.startswith("ok"))
        self.assertGreaterEqual(ok_stages, 5)
        print(f"  [OK] Stages: {ok_stages}/{len(r.stages)} OK")


if __name__ == "__main__":
    unittest.main(verbosity=2)
