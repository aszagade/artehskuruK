"""
Connector Readiness Tests
==========================

Tests for shared architectural gaps that affect ALL future connectors:

1. Deletion handling in ingest_source_document()
2. Centralized source_cursors management
3. KnowledgeWatcher adapter sync
4. Visibility propagation
5. End-to-end adapter → fabric → retrieval
"""

from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path

from kurukshetra.knowledge.fabric import (
    ChangeType,
    KnowledgeFabric,
)
from kurukshetra.registry.database import get_connection
from kurukshetra.sources.models import (
    DocumentProvenance,
    SourceDocument,
    SourceType,
)
from kurukshetra.sources.salesforce_adapter import SalesforceAdapter
from kurukshetra.sources.salesforce_transport import (
    MockSalesforceTransport,
    SFRecord,
)
from kurukshetra.sources.registry import SourceAdapterRegistry


FIXTURE_RECORDS = [
    SFRecord(
        record_id="CR-001", object_type="Knowledge__kav",
        fields={"Title": "G3 Configuration Guide", "KnowledgeBody__c": "Configure G3 feeds. Contact SDOPS."},
        system_modstamp=datetime(2025, 3, 1), created_date=datetime(2024, 1, 1),
    ),
    SFRecord(
        record_id="CR-002", object_type="Knowledge__kav",
        fields={"Title": "AMS Recoding Process", "KnowledgeBody__c": "AMS Recoding workflow. Team: SPM."},
        system_modstamp=datetime(2025, 4, 1), created_date=datetime(2024, 1, 1),
    ),
]


# ==================================================================
# Fix 1: Deletion Handling
# ==================================================================


class TestDeletionHandling(unittest.TestCase):
    """Verify ingest_source_document handles status='deleted' correctly."""

    def setUp(self):
        self.fabric = KnowledgeFabric()
        conn = get_connection()
        for t in ["document_state", "document_versions"]:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()

    def test_deleted_document_yields_removal_result(self):
        doc = SourceDocument(
            title="Deleted: CR-001",
            text_content="[DELETED] Record CR-001 was removed",
            provenance=DocumentProvenance(
                source_id="test", source_type=SourceType.SALESFORCE,
                source_path="salesforce://Knowledge__kav/CR-001",
                external_id="CR-001",
            ),
            status="deleted",
        )
        result = self.fabric.ingest_source_document(doc)
        self.assertEqual(result.change_type, ChangeType.REMOVED)

    def test_deleted_document_no_existing_record(self):
        doc = SourceDocument(
            title="Deleted: NONEXISTENT",
            text_content="[DELETED] Record NONEXISTENT was removed",
            provenance=DocumentProvenance(
                source_id="test", source_type=SourceType.SALESFORCE,
                source_path="salesforce://Knowledge__kav/NONEXISTENT",
                external_id="NONEXISTENT",
            ),
            status="deleted",
        )
        result = self.fabric.ingest_source_document(doc)
        self.assertEqual(result.change_type, ChangeType.REMOVED)

    def test_active_document_still_ingests_normally(self):
        doc = SourceDocument(
            title="Active Document",
            text_content="This is active content for testing purposes.",
            provenance=DocumentProvenance(
                source_id="test", source_type=SourceType.SALESFORCE,
                source_path="salesforce://test/active",
                content_hash="abc123",
            ),
            status="active",
        )
        result = self.fabric.ingest_source_document(doc)
        self.assertIn(result.change_type, [ChangeType.NEW_FILE, ChangeType.NONE])


# ==================================================================
# Fix 2: Centralized Cursor Management
# ==================================================================


class TestCursorManagement(unittest.TestCase):
    """Verify centralized source_cursors management."""

    def setUp(self):
        self.fabric = KnowledgeFabric()
        conn = get_connection()
        try:
            conn.execute("DELETE FROM source_cursors")
        except Exception:
            pass
        conn.close()

    def test_ensure_table_creates(self):
        self.fabric.ensure_source_cursors_table()
        conn = get_connection()
        rows = conn.execute("SELECT * FROM source_cursors").fetchall()
        conn.close()
        self.assertEqual(len(rows), 0)

    def test_save_and_load_cursor(self):
        self.fabric.save_source_cursor("sforce-test", "2025-06-01T00:00:00")
        cursor = self.fabric.load_source_cursor("sforce-test")
        self.assertEqual(cursor, "2025-06-01T00:00:00")

    def test_load_nonexistent_cursor(self):
        cursor = self.fabric.load_source_cursor("nonexistent")
        self.assertIsNone(cursor)

    def test_overwrite_cursor(self):
        self.fabric.save_source_cursor("sforce-test", "2025-01-01")
        self.fabric.save_source_cursor("sforce-test", "2025-06-01")
        cursor = self.fabric.load_source_cursor("sforce-test")
        self.assertEqual(cursor, "2025-06-01")

    def test_multiple_source_cursors(self):
        self.fabric.save_source_cursor("sforce", "2025-01-01")
        self.fabric.save_source_cursor("confluence", "2025-02-01")
        cursors = self.fabric.get_source_cursors()
        self.assertEqual(len(cursors), 2)
        source_ids = {c["source_id"] for c in cursors}
        self.assertIn("sforce", source_ids)
        self.assertIn("confluence", source_ids)

    def test_adapter_uses_centralized_cursor(self):
        transport = MockSalesforceTransport(records=FIXTURE_RECORDS)
        adapter = SalesforceAdapter(
            config={"source_id": "sforce-cursor-test"},
            transport=transport,
        )
        adapter.setup()

        # No cursor yet — full sync
        docs = list(adapter.discover())
        self.assertEqual(len(docs), 2)

        # Cursor should have been saved
        cursor = self.fabric.load_source_cursor("sforce-cursor-test")
        self.assertIsNotNone(cursor)

        # Incremental sync with saved cursor
        adapter2 = SalesforceAdapter(
            config={"source_id": "sforce-cursor-test"},
            transport=transport,
        )
        adapter2.setup()
        # Should use the persisted cursor
        self.assertEqual(adapter2._cursor, cursor)


# ==================================================================
# Fix 3: KnowledgeWatcher Adapter Sync
# ==================================================================


class TestWatcherAdapterSync(unittest.TestCase):
    """Verify KnowledgeWatcher can sync from source adapters."""

    def setUp(self):
        from kurukshetra.runtime.knowledge_watcher import KnowledgeWatcher
        from kurukshetra.registry.database import get_connection

        self.watcher = KnowledgeWatcher(source_dirs=[])

        conn = get_connection()
        for t in ["document_state", "document_versions", "source_cursors"]:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()

    def test_sync_adapter_ingests_documents(self):
        transport = MockSalesforceTransport(records=FIXTURE_RECORDS)
        adapter = SalesforceAdapter(
            config={"source_id": "sforce-watcher"},
            transport=transport,
        )
        adapter.setup()

        result = self.watcher.sync_adapter(adapter)
        self.assertEqual(result["source_id"], "sforce-watcher")
        self.assertGreater(result["new_documents"], 0)
        self.assertEqual(len(result["errors"]), 0)

    def test_sync_adapter_deduplicates(self):
        transport = MockSalesforceTransport(records=FIXTURE_RECORDS)
        adapter = SalesforceAdapter(
            config={"source_id": "sforce-watcher-dedup"},
            transport=transport,
        )
        adapter.setup()

        # First sync
        r1 = self.watcher.sync_adapter(adapter)
        self.assertEqual(r1["new_documents"], 2)

        # Second sync — adapter cursor filters already-processed records
        # (incremental sync returns 0 new docs, not 2 skipped)
        r2 = self.watcher.sync_adapter(adapter)
        self.assertEqual(r2["new_documents"], 0)
        self.assertEqual(len(r2["errors"]), 0)

    def test_sync_adapter_handles_deletion(self):
        transport = MockSalesforceTransport(records=FIXTURE_RECORDS)
        adapter = SalesforceAdapter(
            config={"source_id": "sforce-watcher-del"},
            transport=transport,
        )
        adapter.setup()

        # Initial sync
        self.watcher.sync_adapter(adapter)

        # Delete a record
        transport.remove_record("CR-001", "Knowledge__kav")

        # Sync with cursor — should detect deletion
        result = self.watcher.sync_adapter(adapter)
        self.assertGreater(result["deleted_documents"], 0)

    def test_sync_all_adapters(self):
        registry = SourceAdapterRegistry()

        t1 = MockSalesforceTransport(records=FIXTURE_RECORDS[:1])
        a1 = SalesforceAdapter(config={"source_id": "sforce-multi-1"}, transport=t1)
        a1.setup()
        registry.register(a1)

        t2 = MockSalesforceTransport(records=FIXTURE_RECORDS[1:])
        a2 = SalesforceAdapter(config={"source_id": "sforce-multi-2"}, transport=t2)
        a2.setup()
        registry.register(a2)

        results = self.watcher.sync_all_adapters(registry)
        self.assertEqual(len(results), 2)
        total_new = sum(r.get("new_documents", 0) for r in results)
        self.assertEqual(total_new, 2)

    def test_sync_adapter_caches_refreshed(self):
        transport = MockSalesforceTransport(records=FIXTURE_RECORDS)
        adapter = SalesforceAdapter(
            config={"source_id": "sforce-cache"},
            transport=transport,
        )
        adapter.setup()

        result = self.watcher.sync_adapter(adapter)
        self.assertTrue(self.watcher._bm25_invalidated)


# ==================================================================
# Visibility Propagation
# ==================================================================


class TestVisibilityPropagation(unittest.TestCase):
    """Verify visibility from SourceDocument propagates to documents table."""

    def setUp(self):
        self.fabric = KnowledgeFabric()
        conn = get_connection()
        for t in ["document_state", "document_versions"]:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()

    def test_visibility_propagated(self):
        doc = SourceDocument(
            title="Confidential Doc",
            text_content="This is confidential content for testing.",
            provenance=DocumentProvenance(
                source_id="test", source_type=SourceType.SALESFORCE,
                source_path="salesforce://test/conf",
                content_hash="conf123",
            ),
            visibility="Confidential",
        )
        result = self.fabric.ingest_source_document(doc)
        if result.document_id:
            conn = get_connection()
            row = conn.execute(
                "SELECT visibility FROM documents WHERE document_id = ?",
                (result.document_id,),
            ).fetchone()
            conn.close()
            self.assertEqual(row[0], "Confidential")


# ==================================================================
# End-to-End: Adapter → Fabric → Retrieval
# ==================================================================


class TestAdapterToEndToEnd(unittest.TestCase):
    """Verify the complete adapter → fabric → retrieval → SANJAYA path."""

    def setUp(self):
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        for t in ["document_state", "document_versions", "source_cursors"]:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()

    def test_full_e2e_with_watcher_sync(self):
        from kurukshetra.runtime.knowledge_watcher import KnowledgeWatcher

        watcher = KnowledgeWatcher(source_dirs=[])
        transport = MockSalesforceTransport(records=FIXTURE_RECORDS)
        adapter = SalesforceAdapter(
            config={"source_id": "sforce-e2e"},
            transport=transport,
        )
        adapter.setup()

        # Sync through watcher
        sync_result = watcher.sync_adapter(adapter)
        self.assertGreater(sync_result["new_documents"], 0)

        # Retrieve via BM25
        from kurukshetra.retrieval.database_bm25 import DatabaseBM25Retriever
        retriever = DatabaseBM25Retriever()
        results = retriever.search("G3 configuration", top_k=5)
        self.assertTrue(len(results) > 0)

        # Verify knowledge state
        state = watcher.get_knowledge_state()
        self.assertGreater(state["total_documents"], 0)
        self.assertGreater(state["total_chunks"], 0)

        watcher.close()


if __name__ == "__main__":
    unittest.main()
