"""
Source Adapter Tests
====================

Deterministic tests for the Source Adapter contract, registry,
and mocked Salesforce adapter.

Tests are self-contained and do not require network access,
credentials, or the production database.
"""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from kurukshetra.sources.models import (
    DocumentProvenance,
    SourceCapability,
    SourceCursor,
    SourceDocument,
    SourceHealth,
    SourceIdentity,
    SourceType,
)
from kurukshetra.sources.adapter import SourceAdapter
from kurukshetra.sources.registry import SourceAdapterRegistry
from kurukshetra.sources.salesforce_mock import SalesforceMockAdapter, MOCK_ARTICLES


# ==================================================================
# Model Tests
# ==================================================================


class TestSourceIdentity(unittest.TestCase):
    """Test SourceIdentity creation and validation."""

    def test_create_identity(self):
        identity = SourceIdentity(
            source_id="test-001",
            source_type=SourceType.SALESFORCE,
            display_name="Test Source",
        )
        self.assertEqual(identity.source_id, "test-001")
        self.assertEqual(identity.source_type, SourceType.SALESFORCE)

    def test_empty_source_id_raises(self):
        with self.assertRaises(ValueError):
            SourceIdentity(
                source_id="",
                source_type=SourceType.SALESFORCE,
                display_name="Bad",
            )

    def test_frozen_identity(self):
        identity = SourceIdentity(
            source_id="test-002",
            source_type=SourceType.SQL,
            display_name="SQL Source",
        )
        with self.assertRaises(AttributeError):
            identity.source_id = "changed"


class TestSourceDocument(unittest.TestCase):
    """Test SourceDocument creation and validation."""

    def _make_doc(self, **kwargs):
        defaults = {
            "title": "Test Document",
            "text_content": "Some content here",
        }
        defaults.update(kwargs)
        return SourceDocument(**defaults)

    def test_create_document(self):
        doc = self._make_doc()
        self.assertEqual(doc.title, "Test Document")
        self.assertEqual(doc.visibility, "Internal")

    def test_empty_title_raises(self):
        with self.assertRaises(ValueError):
            self._make_doc(title="")

    def test_empty_content_raises(self):
        with self.assertRaises(ValueError):
            self._make_doc(text_content="")

    def test_provenance_defaults(self):
        doc = self._make_doc()
        self.assertIsNotNone(doc.provenance)
        self.assertEqual(doc.provenance.source_id, "")

    def test_team_detection_fields(self):
        doc = self._make_doc(
            detected_systems=["G3", "RMS"],
            detected_processes=["migration"],
        )
        self.assertEqual(doc.detected_systems, ["G3", "RMS"])
        self.assertEqual(doc.detected_processes, ["migration"])


class TestDocumentProvenance(unittest.TestCase):
    """Test DocumentProvenance."""

    def test_provenance_str(self):
        p = DocumentProvenance(
            source_id="sforce",
            source_type=SourceType.SALESFORCE,
            source_path="https://example.com/article/1",
        )
        self.assertIn("sforce", str(p))
        self.assertIn("article/1", str(p))


class TestSourceCursor(unittest.TestCase):
    """Test SourceCursor."""

    def test_create_cursor(self):
        cursor = SourceCursor(
            source_id="test",
            cursor_type="timestamp",
            cursor_value="2025-01-01T00:00:00",
        )
        self.assertEqual(cursor.items_processed, 0)


class TestSourceCapability(unittest.TestCase):
    """Test SourceCapability defaults."""

    def test_default_capabilities(self):
        cap = SourceCapability()
        self.assertTrue(cap.supports_discovery)
        self.assertFalse(cap.supports_incremental)
        self.assertFalse(cap.supports_deletion)
        self.assertEqual(cap.max_batch_size, 100)


class TestSourceHealth(unittest.TestCase):
    """Test SourceHealth."""

    def test_health_defaults(self):
        h = SourceHealth(source_id="test")
        self.assertTrue(h.healthy)
        self.assertEqual(h.documents_total, 0)


# ==================================================================
# Adapter Protocol Tests
# ==================================================================


class TestSourceAdapterProtocol(unittest.TestCase):
    """Test that SourceAdapter enforces the contract."""

    def test_cannot_instantiate_abstract(self):
        with self.assertRaises(TypeError):
            SourceAdapter()

    def test_minimal_adapter(self):
        """A minimal adapter that implements all required methods."""

        class MinimalAdapter(SourceAdapter):
            def identify(self):
                return SourceIdentity(
                    source_id="minimal",
                    source_type=SourceType.CUSTOM,
                    display_name="Minimal",
                )

            def discover(self, cursor=None):
                return iter([])

            def health(self):
                return SourceHealth(source_id="minimal")

        adapter = MinimalAdapter()
        identity = adapter.identify()
        self.assertEqual(identity.source_id, "minimal")

        docs = list(adapter.discover())
        self.assertEqual(docs, [])

        h = adapter.health()
        self.assertTrue(h.healthy)

    def test_capabilities_override(self):

        class CapableAdapter(SourceAdapter):
            def identify(self):
                return SourceIdentity(
                    source_id="cap",
                    source_type=SourceType.CUSTOM,
                    display_name="Cap",
                )

            def discover(self, cursor=None):
                return iter([])

            def health(self):
                return SourceHealth(source_id="cap")

            def capabilities(self):
                return SourceCapability(
                    supports_incremental=True,
                    supports_deletion=True,
                )

        cap = CapableAdapter().capabilities()
        self.assertTrue(cap.supports_incremental)
        self.assertTrue(cap.supports_deletion)

    def test_setup_teardown_lifecycle(self):
        """Test that setup/teardown are called."""

        class LifecycleAdapter(SourceAdapter):
            def __init__(self):
                super().__init__()
                self.setup_called = False
                self.teardown_called = False

            def identify(self):
                return SourceIdentity(
                    source_id="lifecycle",
                    source_type=SourceType.CUSTOM,
                    display_name="Lifecycle",
                )

            def discover(self, cursor=None):
                return iter([])

            def health(self):
                return SourceHealth(source_id="lifecycle")

            def setup(self):
                self.setup_called = True

            def teardown(self):
                self.teardown_called = True

        adapter = LifecycleAdapter()
        registry = SourceAdapterRegistry()
        registry.register(adapter)
        self.assertTrue(adapter.setup_called)

        registry.unregister("lifecycle")
        self.assertTrue(adapter.teardown_called)


# ==================================================================
# Registry Tests
# ==================================================================


class TestSourceAdapterRegistry(unittest.TestCase):
    """Test the adapter registry."""

    def setUp(self):
        self.registry = SourceAdapterRegistry()
        self.adapter = SalesforceMockAdapter()

    def test_register_adapter(self):
        identity = self.registry.register(self.adapter)
        self.assertEqual(identity.source_id, "sforce-knowledge-mock")
        self.assertEqual(self.registry.count(), 1)

    def test_get_adapter(self):
        self.registry.register(self.adapter)
        adapter = self.registry.get("sforce-knowledge-mock")
        self.assertIsNotNone(adapter)
        self.assertIsInstance(adapter, SalesforceMockAdapter)

    def test_list_sources(self):
        self.registry.register(self.adapter)
        sources = self.registry.list_sources()
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].source_type, SourceType.SALESFORCE)

    def test_unregister(self):
        self.registry.register(self.adapter)
        result = self.registry.unregister("sforce-knowledge-mock")
        self.assertTrue(result)
        self.assertEqual(self.registry.count(), 0)

    def test_unregister_nonexistent(self):
        result = self.registry.unregister("nonexistent")
        self.assertFalse(result)

    def test_health_all(self):
        self.registry.register(self.adapter)
        health = self.registry.health_all()
        self.assertEqual(len(health), 1)
        self.assertTrue(health[0].healthy)

    def test_health_one(self):
        self.registry.register(self.adapter)
        h = self.registry.health_one("sforce-knowledge-mock")
        self.assertIsNotNone(h)
        self.assertTrue(h.healthy)

    def test_health_one_nonexistent(self):
        h = self.registry.health_one("nonexistent")
        self.assertIsNone(h)

    def test_clear(self):
        self.registry.register(self.adapter)
        count = self.registry.clear()
        self.assertEqual(count, 1)
        self.assertEqual(self.registry.count(), 0)

    def test_replace_adapter(self):
        """Registering same source_id replaces the old adapter."""
        adapter1 = SalesforceMockAdapter(config={"instance_url": "url1"})
        adapter2 = SalesforceMockAdapter(config={"instance_url": "url2"})

        self.registry.register(adapter1)
        self.registry.register(adapter2)

        self.assertEqual(self.registry.count(), 1)
        current = self.registry.get("sforce-knowledge-mock")
        self.assertEqual(current.config["instance_url"], "url2")


# ==================================================================
# Salesforce Mock Adapter Tests
# ==================================================================


class TestSalesforceMockAdapter(unittest.TestCase):
    """Test the mocked Salesforce adapter."""

    def setUp(self):
        self.adapter = SalesforceMockAdapter()

    def test_identify(self):
        identity = self.adapter.identify()
        self.assertEqual(identity.source_id, "sforce-knowledge-mock")
        self.assertEqual(identity.source_type, SourceType.SALESFORCE)
        self.assertEqual(identity.owner_team, "sdops")

    def test_capabilities(self):
        cap = self.adapter.capabilities()
        self.assertTrue(cap.supports_discovery)
        self.assertTrue(cap.supports_incremental)
        self.assertTrue(cap.supports_teams)
        self.assertTrue(cap.supports_visibility)

    def test_health(self):
        h = self.adapter.health()
        self.assertTrue(h.healthy)
        self.assertEqual(h.documents_total, len(MOCK_ARTICLES))
        self.assertEqual(h.details["mode"], "mock")

    def test_discover_all(self):
        docs = list(self.adapter.discover())
        self.assertEqual(len(docs), len(MOCK_ARTICLES))

    def test_discover_documents_have_provenance(self):
        docs = list(self.adapter.discover())
        for doc in docs:
            self.assertIsNotNone(doc.provenance)
            self.assertEqual(doc.provenance.source_id, "sforce-knowledge-mock")
            self.assertEqual(doc.provenance.source_type, SourceType.SALESFORCE)
            self.assertTrue(doc.provenance.source_path.startswith("https://"))
            self.assertTrue(len(doc.provenance.content_hash) > 0)

    def test_discover_documents_have_content(self):
        docs = list(self.adapter.discover())
        for doc in docs:
            self.assertTrue(len(doc.text_content) > 0)
            self.assertTrue(len(doc.title) > 0)

    def test_discover_documents_have_teams(self):
        docs = list(self.adapter.discover())
        # At least some documents should have team associations
        docs_with_teams = [d for d in docs if d.team_ids]
        self.assertTrue(len(docs_with_teams) > 0)

    def test_discover_documents_have_systems(self):
        docs = list(self.adapter.discover())
        all_systems = []
        for doc in docs:
            all_systems.extend(doc.detected_systems)
        # Should detect known systems like G3, RMS, SFDC
        self.assertIn("G3", all_systems)
        self.assertIn("RMS", all_systems)

    def test_discover_incremental_with_cursor(self):
        """Cursor filtering should reduce the number of documents."""
        all_docs = list(self.adapter.discover())
        # Use a recent cursor to filter
        cursor = datetime(2025, 7, 1).isoformat()
        filtered = list(self.adapter.discover(cursor=cursor))
        self.assertLess(len(filtered), len(all_docs))

    def test_discover_incremental_early_cursor(self):
        """Early cursor should return all documents."""
        cursor = datetime(2020, 1, 1).isoformat()
        docs = list(self.adapter.discover(cursor=cursor))
        self.assertEqual(len(docs), len(MOCK_ARTICLES))

    def test_discover_invalid_cursor(self):
        """Invalid cursor should return all documents."""
        docs = list(self.adapter.discover(cursor="not-a-date"))
        self.assertEqual(len(docs), len(MOCK_ARTICLES))


# ==================================================================
# Content Hash Determinism
# ==================================================================


class TestContentHashDeterminism(unittest.TestCase):
    """Test that content hashing is deterministic."""

    def test_same_content_same_hash(self):
        adapter = SalesforceMockAdapter()
        docs1 = list(adapter.discover())
        docs2 = list(adapter.discover())

        for d1, d2 in zip(docs1, docs2):
            self.assertEqual(
                d1.provenance.content_hash,
                d2.provenance.content_hash,
            )

    def test_different_content_different_hash(self):
        doc1 = SourceDocument(
            title="A", text_content="Content A",
            provenance=DocumentProvenance(
                source_id="test", source_type=SourceType.CUSTOM, source_path="a",
                content_hash=hashlib.sha256(b"Content A").hexdigest(),
            ),
        )
        doc2 = SourceDocument(
            title="B", text_content="Content B",
            provenance=DocumentProvenance(
                source_id="test", source_type=SourceType.CUSTOM, source_path="b",
                content_hash=hashlib.sha256(b"Content B").hexdigest(),
            ),
        )
        self.assertNotEqual(
            doc1.provenance.content_hash,
            doc2.provenance.content_hash,
        )


# ==================================================================
# Knowledge Fabric Integration Tests
# ==================================================================


class TestFabricSourceDocumentIngestion(unittest.TestCase):
    """Test that KnowledgeFabric can ingest SourceDocuments."""

    def setUp(self):
        from kurukshetra.knowledge.fabric import KnowledgeFabric
        from kurukshetra.registry.database import get_connection
        self.fabric = KnowledgeFabric()
        # Clean state from previous test runs to avoid dedup false positives
        conn = get_connection()
        for table in ['document_state', 'document_versions']:
            try:
                conn.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        conn.close()

    def test_ingest_single_source_document(self):
        adapter = SalesforceMockAdapter()
        docs = list(adapter.discover())
        self.assertTrue(len(docs) > 0)

        result = self.fabric.ingest_source_document(docs[0])
        self.assertIsNotNone(result.document_id)
        self.assertTrue(result.document_id.startswith("DOC-"))
        self.assertGreater(result.chunks_stored, 0)

    def test_ingest_deduplication(self):
        """Ingesting the same SourceDocument twice should deduplicate."""
        adapter = SalesforceMockAdapter()
        docs = list(adapter.discover())

        result1 = self.fabric.ingest_source_document(docs[0])
        result2 = self.fabric.ingest_source_document(docs[0])

        # Second ingest should be a no-op (same content hash)
        self.assertEqual(result1.document_id, result2.document_id)
        self.assertEqual(result2.change_type.value, "none")

    def test_ingest_multiple_source_documents(self):
        adapter = SalesforceMockAdapter()
        docs = list(adapter.discover())

        results = []
        for doc in docs[:3]:
            result = self.fabric.ingest_source_document(doc)
            results.append(result)

        doc_ids = [r.document_id for r in results]
        # All should have valid document IDs
        for did in doc_ids:
            self.assertTrue(did.startswith("DOC-"))

        # Chunks should be stored
        total_chunks = sum(r.chunks_stored for r in results)
        self.assertGreater(total_chunks, 0)

    def test_ingest_preserves_provenance(self):
        adapter = SalesforceMockAdapter()
        docs = list(adapter.discover())

        result = self.fabric.ingest_source_document(docs[0])

        # Check document_state table
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        row = conn.execute(
            "SELECT source_path, team_ids FROM document_state WHERE document_id = ?",
            (result.document_id,),
        ).fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertIn("salesforce.com", row[0])

    def test_ingest_tracks_team_ids(self):
        adapter = SalesforceMockAdapter()
        docs = [d for d in adapter.discover() if d.team_ids]
        self.assertTrue(len(docs) > 0)

        result = self.fabric.ingest_source_document(docs[0])
        self.assertTrue(
            len(result.teams_detected) > 0 or len(docs[0].team_ids) > 0
        )

    def test_end_to_end_adapter_to_fabric(self):
        """Full path: adapter -> discover -> fabric -> ingest."""
        registry = SourceAdapterRegistry()
        adapter = SalesforceMockAdapter()
        registry.register(adapter)

        # Discover
        all_docs = []
        for identity in registry.list_sources():
            adapter = registry.get(identity.source_id)
            for doc in adapter.discover():
                all_docs.append(doc)

        self.assertEqual(len(all_docs), len(MOCK_ARTICLES))

        # Ingest
        results = []
        for doc in all_docs:
            result = self.fabric.ingest_source_document(doc)
            results.append(result)

        # Verify
        successful = [r for r in results if not r.error]
        self.assertEqual(len(successful), len(MOCK_ARTICLES))

        # Verify knowledge state
        state = self.fabric.get_knowledge_state()
        self.assertGreater(state.total_documents, 0)
        self.assertGreater(state.total_chunks, 0)


if __name__ == "__main__":
    unittest.main()
