"""
Production Salesforce Adapter Tests
====================================

Deterministic tests for the production Salesforce adapter using
MockSalesforceTransport. No network access or credentials required.

Tests cover:
- Transport abstraction
- Full sync (no cursor)
- Incremental sync (with cursor)
- Record → SourceDocument conversion
- Pagination
- Retry with transient failures
- Error boundaries
- Deletion detection
- Cursor persistence
- Team detection
- System/process detection
- Content hash determinism
- Knowledge Fabric integration (adapter → fabric → retrieval → SANJAYA)
"""

from __future__ import annotations

import hashlib
import unittest
from datetime import datetime
from pathlib import Path

from kurukshetra.sources.models import (
    SourceDocument,
    SourceType,
)
from kurukshetra.sources.salesforce_transport import (
    MockSalesforceTransport,
    SFRecord,
    SFTransportStats,
)
from kurukshetra.sources.salesforce_adapter import SalesforceAdapter
from kurukshetra.sources.registry import SourceAdapterRegistry


# ==================================================================
# Test Fixtures
# ==================================================================


def _make_record(
    record_id: str,
    title: str,
    body: str,
    object_type: str = "Knowledge__kav",
    modstamp: Optional[datetime] = None,
    team: str = "",
    is_deleted: bool = False,
) -> SFRecord:
    """Create a deterministic SFRecord for testing."""
    fields = {
        "Title": title,
        "KnowledgeBody__c": body,
        "Summary": f"Summary of {title}",
        "ArticleNumber": f"ART-{record_id}",
        "PublishStatus": "Published",
        "ValidationStatus": "Approved",
        "Language": "en",
    }
    if team:
        fields["Team__c"] = team
    if object_type == "Case":
        fields = {
            "Subject": title,
            "Description": body,
            "CaseNumber": f"CASE-{record_id}",
            "Status": "Open",
            "Priority": "High",
            "Type": "Technical",
        }

    now = modstamp or datetime.utcnow()
    return SFRecord(
        record_id=record_id,
        object_type=object_type,
        fields=fields,
        system_modstamp=now,
        last_modified_date=now,
        created_date=datetime(2024, 1, 1),
        is_deleted=is_deleted,
    )


FIXTURE_RECORDS = [
    _make_record(
        "SF-001", "G3 Data Feed Configuration",
        "Configure G3 feeds for RMS to SFDC data flow. "
        "Contact SDOPS for infrastructure. "
        "Feed frequency: every 5 minutes.",
        modstamp=datetime(2025, 3, 1, 10, 0),
        team="sdops",
    ),
    _make_record(
        "SF-002", "AMS Recoding Workflow",
        "AMS Recoding process for SFDC cases. "
        "Step 1: Client Services receives request via CPM/CRM. "
        "Step 2: Case assigned to Case Owner. "
        "Systems: G3AMSRC0, SFDC, RMS. "
        "Primary team: SPM. Supporting: ICS.",
        modstamp=datetime(2025, 4, 1, 14, 30),
        team="spm",
    ),
    _make_record(
        "SF-003", "Rate Shopping Migration",
        "Migration of rate shopping from legacy RMS to G3. "
        "Prerequisites: G3 Rate Shopping module licensed. "
        "Rollback: Contact SDOPS for rollback support. "
        "Timeline: 2 weeks parallel, 1 week decommission.",
        modstamp=datetime(2025, 5, 15, 9, 0),
        team="sdops",
    ),
    _make_record(
        "SF-004", "Proactive Monitoring Setup",
        "G3 Proactive Monitoring for data discrepancy detection. "
        "Monitors G3 ↔ SFDC, G3 ↔ RMS, G3 ↔ D360. "
        "Alert channels: Datadog, email sdops-alerts@ideas.com, PagerDuty.",
        modstamp=datetime(2025, 6, 20, 16, 45),
        team="sdops",
    ),
    _make_record(
        "SF-005", "Stats to Inventory Transition",
        "Migration from G3 Stats to unified Inventory dashboard. "
        "Phase 1: Run parallel 4 weeks. "
        "Phase 2: Client migration 2 weeks. "
        "Phase 3: Decommission 1 week. "
        "Teams: SDOPS, SPM, ICS.",
        modstamp=datetime(2025, 7, 1, 11, 30),
        team="sdops",
    ),
]


# ==================================================================
# Transport Tests
# ==================================================================


class TestMockSalesforceTransport(unittest.TestCase):
    """Test the mock transport layer."""

    def test_connect(self):
        t = MockSalesforceTransport()
        self.assertTrue(t.connect())
        self.assertTrue(t.is_healthy())

    def test_query_returns_records(self):
        t = MockSalesforceTransport(records=FIXTURE_RECORDS)
        t.connect()
        result = t.query("SELECT Id, Title FROM Knowledge__kav")
        self.assertEqual(result.total_size, 5)
        self.assertEqual(len(result.records), 5)
        self.assertTrue(result.done)

    def test_query_filters_by_object_type(self):
        records = [
            _make_record("K1", "KA", "body", "Knowledge__kav"),
            _make_record("C1", "Case", "body", "Case"),
        ]
        t = MockSalesforceTransport(records=records)
        t.connect()
        result = t.query("SELECT Id FROM Knowledge__kav")
        self.assertEqual(result.total_size, 1)

    def test_query_with_limit(self):
        t = MockSalesforceTransport(records=FIXTURE_RECORDS)
        t.connect()
        result = t.query("SELECT Id FROM Knowledge__kav", limit=2)
        self.assertEqual(len(result.records), 2)

    def test_get_record(self):
        t = MockSalesforceTransport(records=FIXTURE_RECORDS)
        t.connect()
        rec = t.get_record("Knowledge__kav", "SF-001")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.get("Title"), "G3 Data Feed Configuration")

    def test_get_record_nonexistent(self):
        t = MockSalesforceTransport(records=FIXTURE_RECORDS)
        t.connect()
        rec = t.get_record("Knowledge__kav", "NONEXISTENT")
        self.assertIsNone(rec)

    def test_deletion_tracking(self):
        t = MockSalesforceTransport(records=FIXTURE_RECORDS)
        t.connect()
        t.remove_record("SF-003", "Knowledge__kav")
        deleted = t.get_deleted("Knowledge__kav", datetime(2020, 1, 1))
        self.assertIn("SF-003", deleted)
        self.assertEqual(len(deleted), 1)

    def test_update_record(self):
        t = MockSalesforceTransport(records=FIXTURE_RECORDS)
        t.connect()
        t.update_record("SF-001", {"Title": "Updated Title"})
        rec = t.get_record("Knowledge__kav", "SF-001")
        self.assertEqual(rec.get("Title"), "Updated Title")

    def test_transient_failure(self):
        t = MockSalesforceTransport(
            records=FIXTURE_RECORDS, fail_count=2
        )
        t.connect()
        # First two queries fail
        with self.assertRaises(ConnectionError):
            t.query("SELECT Id FROM Knowledge__kav")
        with self.assertRaises(ConnectionError):
            t.query("SELECT Id FROM Knowledge__kav")
        # Third succeeds
        result = t.query("SELECT Id FROM Knowledge__kav")
        self.assertEqual(result.total_size, 5)

    def test_stats_tracking(self):
        t = MockSalesforceTransport(records=FIXTURE_RECORDS)
        t.connect()
        t.query("SELECT Id FROM Knowledge__kav")
        t.get_record("Knowledge__kav", "SF-001")
        stats = t.get_stats()
        self.assertEqual(stats.queries_executed, 1)
        self.assertEqual(stats.records_fetched, 5)
        self.assertEqual(stats.api_calls, 2)


# ==================================================================
# Adapter Tests
# ==================================================================


class TestSalesforceAdapterIdentity(unittest.TestCase):
    """Test adapter identity and capabilities."""

    def test_identify(self):
        transport = MockSalesforceTransport(records=FIXTURE_RECORDS)
        adapter = SalesforceAdapter(
            config={"source_id": "sforce-test"},
            transport=transport,
        )
        identity = adapter.identify()
        self.assertEqual(identity.source_id, "sforce-test")
        self.assertEqual(identity.source_type, SourceType.SALESFORCE)

    def test_capabilities(self):
        transport = MockSalesforceTransport(records=FIXTURE_RECORDS)
        adapter = SalesforceAdapter(transport=transport)
        cap = adapter.capabilities()
        self.assertTrue(cap.supports_incremental)
        self.assertTrue(cap.supports_deletion)
        self.assertTrue(cap.supports_teams)
        self.assertTrue(cap.supports_visibility)

    def test_setup_connects(self):
        transport = MockSalesforceTransport(records=FIXTURE_RECORDS)
        adapter = SalesforceAdapter(transport=transport)
        adapter.setup()
        health = adapter.health()
        self.assertTrue(health.healthy)

    def test_setup_without_transport_raises(self):
        adapter = SalesforceAdapter(config={"source_id": "no-transport"})
        with self.assertRaises(RuntimeError):
            adapter.setup()


class TestSalesforceAdapterFullSync(unittest.TestCase):
    """Test full sync (no cursor)."""

    def setUp(self):
        # Clean stale cursors from previous test runs
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        try:
            conn.execute("DELETE FROM source_cursors")
        except Exception:
            pass
        conn.close()

        self.transport = MockSalesforceTransport(records=FIXTURE_RECORDS)
        self.adapter = SalesforceAdapter(
            config={"source_id": "sforce-test"},
            transport=self.transport,
        )
        self.adapter.setup()

    def test_full_sync_yields_all_records(self):
        docs = list(self.adapter.discover())
        self.assertEqual(len(docs), len(FIXTURE_RECORDS))

    def test_documents_have_valid_ids(self):
        docs = list(self.adapter.discover())
        for doc in docs:
            self.assertTrue(doc.provenance.external_id.startswith("SF-"))

    def test_documents_have_content(self):
        docs = list(self.adapter.discover())
        for doc in docs:
            self.assertTrue(len(doc.text_content) > 0)
            self.assertTrue(len(doc.title) > 0)

    def test_documents_have_provenance(self):
        docs = list(self.adapter.discover())
        for doc in docs:
            self.assertEqual(doc.provenance.source_id, "sforce-test")
            self.assertEqual(doc.provenance.source_type, SourceType.SALESFORCE)
            self.assertTrue(doc.provenance.external_url.startswith("https://"))

    def test_documents_have_team_detection(self):
        docs = list(self.adapter.discover())
        docs_with_teams = [d for d in docs if d.team_ids]
        self.assertTrue(len(docs_with_teams) > 0)

    def test_documents_have_system_detection(self):
        docs = list(self.adapter.discover())
        all_systems = []
        for doc in docs:
            all_systems.extend(doc.detected_systems)
        self.assertIn("G3", all_systems)
        self.assertIn("RMS", all_systems)

    def test_documents_have_process_detection(self):
        docs = list(self.adapter.discover())
        all_processes = []
        for doc in docs:
            all_processes.extend(doc.detected_processes)
        self.assertIn("configuration", all_processes)
        self.assertIn("migration", all_processes)

    def test_content_hash_determinism(self):
        docs1 = list(self.adapter.discover())
        docs2 = list(self.adapter.discover())
        for d1, d2 in zip(docs1, docs2):
            self.assertEqual(
                d1.provenance.content_hash,
                d2.provenance.content_hash,
            )


class TestSalesforceAdapterIncrementalSync(unittest.TestCase):
    """Test incremental sync with cursor."""

    def setUp(self):
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        try:
            conn.execute("DELETE FROM source_cursors")
        except Exception:
            pass
        conn.close()

        self.transport = MockSalesforceTransport(records=FIXTURE_RECORDS)
        self.adapter = SalesforceAdapter(
            config={"source_id": "sforce-incr"},
            transport=self.transport,
        )
        self.adapter.setup()

    def test_cursor_filters_records(self):
        # Full sync first
        all_docs = list(self.adapter.discover())
        self.assertEqual(len(all_docs), 5)

        # Incremental sync with cursor after record 3
        cursor = datetime(2025, 4, 15).isoformat()
        incr_docs = list(self.adapter.discover(cursor=cursor))
        self.assertLess(len(incr_docs), 5)
        # Should only get records modified after April 15
        for doc in incr_docs:
            if doc.status != "deleted":
                self.assertGreater(
                    doc.provenance.last_modified_at,
                    datetime(2025, 4, 15),
                )

    def test_early_cursor_returns_all(self):
        cursor = datetime(2020, 1, 1).isoformat()
        docs = list(self.adapter.discover(cursor=cursor))
        self.assertEqual(len(docs), 5)

    def test_late_cursor_returns_none(self):
        cursor = datetime(2030, 1, 1).isoformat()
        docs = list(self.adapter.discover(cursor=cursor))
        self.assertEqual(len(docs), 0)


class TestSalesforceAdapterDeletion(unittest.TestCase):
    """Test deletion detection."""

    def test_deleted_records_yield_deleted_documents(self):
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        try:
            conn.execute("DELETE FROM source_cursors")
        except Exception:
            pass
        conn.close()

        transport = MockSalesforceTransport(records=FIXTURE_RECORDS)
        # Delete a record
        transport.remove_record("SF-003", "Knowledge__kav")

        adapter = SalesforceAdapter(
            config={"source_id": "sforce-del"},
            transport=transport,
        )
        adapter.setup()

        # Full sync won't show deleted (they're removed from store)
        docs = list(adapter.discover())
        self.assertEqual(len(docs), 4)

        # Incremental sync with cursor will detect deletion
        adapter._cursor = datetime(2025, 1, 1).isoformat()
        docs_incr = list(adapter.discover())
        deleted_docs = [d for d in docs_incr if d.status == "deleted"]
        self.assertTrue(len(deleted_docs) > 0)
        self.assertIn("SF-003", deleted_docs[0].provenance.external_id)


class TestSalesforceAdapterRetry(unittest.TestCase):
    """Test retry with transient failures."""

    def test_retries_on_failure(self):
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        try:
            conn.execute("DELETE FROM source_cursors")
        except Exception:
            pass
        conn.close()

        transport = MockSalesforceTransport(
            records=FIXTURE_RECORDS, fail_count=2
        )
        adapter = SalesforceAdapter(
            config={
                "source_id": "sforce-retry",
                "max_retries": 3,
                "retry_base_delay_ms": 10,  # Fast for testing
            },
            transport=transport,
        )
        adapter.setup()

        # Should succeed after 2 retries
        docs = list(adapter.discover())
        self.assertEqual(len(docs), 5)

        stats = transport.get_stats()
        self.assertGreaterEqual(stats.errors, 2)

    def test_gives_up_after_max_retries(self):
        transport = MockSalesforceTransport(
            records=FIXTURE_RECORDS, fail_query=True
        )
        adapter = SalesforceAdapter(
            config={
                "source_id": "sforce-retry-max",
                "max_retries": 2,
                "retry_base_delay_ms": 10,
            },
            transport=transport,
        )
        adapter.setup()

        # Should return empty (all queries fail)
        docs = list(adapter.discover())
        self.assertEqual(len(docs), 0)


class TestSalesforceAdapterErrorBoundary(unittest.TestCase):
    """Test that one bad record doesn't stop discovery."""

    def test_bad_record_skipped(self):
        records = [
            _make_record("OK-1", "Good Record", "Good body"),
            SFRecord(
                record_id="BAD-1",
                object_type="Knowledge__kav",
                fields={},  # Missing Title and body
                system_modstamp=datetime(2025, 1, 1),
            ),
            _make_record("OK-2", "Another Good", "Another body"),
        ]
        transport = MockSalesforceTransport(records=records)
        adapter = SalesforceAdapter(
            config={"source_id": "sforce-err"},
            transport=transport,
        )
        adapter.setup()

        docs = list(adapter.discover())
        # Bad record should be skipped, others should succeed
        self.assertGreaterEqual(len(docs), 2)


class TestSalesforceAdapterHealth(unittest.TestCase):
    """Test health reporting."""

    def test_health_after_setup(self):
        transport = MockSalesforceTransport(records=FIXTURE_RECORDS)
        adapter = SalesforceAdapter(
            config={"source_id": "sforce-health"},
            transport=transport,
        )
        adapter.setup()
        h = adapter.health()
        self.assertTrue(h.healthy)
        self.assertIn("objects", h.details)

    def test_health_without_transport(self):
        adapter = SalesforceAdapter(config={"source_id": "sforce-no-transport"})
        h = adapter.health()
        self.assertFalse(h.healthy)


# ==================================================================
# Knowledge Fabric Integration Tests
# ==================================================================


class TestSalesforceEndToEnd(unittest.TestCase):
    """Test full flow: adapter → fabric → retrieval."""

    def setUp(self):
        from kurukshetra.knowledge.fabric import KnowledgeFabric
        from kurukshetra.registry.database import get_connection

        self.fabric = KnowledgeFabric()

        # Clean state
        conn = get_connection()
        for table in ['document_state', 'document_versions', 'source_cursors']:
            try:
                conn.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        conn.close()

        # Set up adapter
        self.transport = MockSalesforceTransport(records=FIXTURE_RECORDS)
        self.adapter = SalesforceAdapter(
            config={"source_id": "sforce-e2e"},
            transport=self.transport,
        )
        self.adapter.setup()

    def test_adapter_to_fabric_ingestion(self):
        docs = list(self.adapter.discover())
        results = []
        for doc in docs:
            result = self.fabric.ingest_source_document(doc)
            results.append(result)

        successful = [r for r in results if not r.error]
        self.assertEqual(len(successful), len(FIXTURE_RECORDS))

    def test_fabric_deduplication(self):
        docs = list(self.adapter.discover())
        # Ingest all
        for doc in docs:
            self.fabric.ingest_source_document(doc)

        # Ingest again — should deduplicate
        results2 = []
        for doc in docs:
            result = self.fabric.ingest_source_document(doc)
            results2.append(result)

        no_ops = [r for r in results2 if r.change_type.value == "none"]
        self.assertEqual(len(no_ops), len(FIXTURE_RECORDS))

    def test_retrieval_finds_ingested_content(self):
        """After ingestion, BM25 should find the content."""
        docs = list(self.adapter.discover())
        for doc in docs:
            self.fabric.ingest_source_document(doc)

        from kurukshetra.retrieval.database_bm25 import DatabaseBM25Retriever
        retriever = DatabaseBM25Retriever()
        results = retriever.search("G3 data feed configuration", top_k=5)
        self.assertTrue(len(results) > 0)
        # At least one result should match our ingested docs
        titles = [r.text[:100] for r in results]
        self.assertTrue(
            any("G3" in t or "Data Feed" in t for t in titles)
        )

    def test_sanjaya_can_answer_from_ingested_salesforce_data(self):
        """SANJAYA should be able to answer from adapter-ingested data."""
        docs = list(self.adapter.discover())
        for doc in docs:
            self.fabric.ingest_source_document(doc)

        from kurukshetra.agent.planner import SANJAYAPlanner
        from kurukshetra.retrieval.hybrid import HybridRetriever
        from kurukshetra.retrieval.access_control import (
            VisibilityFilter, VisibilityLevel,
        )
        from kurukshetra.agent.answer_generator import AnswerGenerator

        planner = SANJAYAPlanner()
        retriever = VisibilityFilter(
            max_level=VisibilityLevel.INTERNAL,
        ).wrap(HybridRetriever())
        generator = AnswerGenerator()

        query = "What is G3 Data Feed Configuration?"
        plan = planner.create_plan(query)
        evidence = retriever.search(query, top_k=5)
        answer = generator.generate(
            query=query, results=evidence,
            strategy=plan.recommended_strategy,
        )

        self.assertTrue(len(answer.answer) > 0)
        self.assertTrue(len(answer.citations) > 0)
        # Should not abstain — we have the data
        self.assertFalse(answer.abstained)

    def test_knowledge_state_reflects_salesforce_docs(self):
        docs = list(self.adapter.discover())
        for doc in docs:
            self.fabric.ingest_source_document(doc)

        state = self.fabric.get_knowledge_state()
        self.assertGreater(state.total_documents, 0)
        self.assertGreater(state.total_chunks, 0)


# ==================================================================
# Registry Integration Tests
# ==================================================================


class TestSalesforceRegistryIntegration(unittest.TestCase):
    """Test adapter registration and discovery through the registry."""

    def setUp(self):
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        try:
            conn.execute("DELETE FROM source_cursors")
        except Exception:
            pass
        conn.close()

    def test_register_and_discover(self):
        transport = MockSalesforceTransport(records=FIXTURE_RECORDS)
        adapter = SalesforceAdapter(
            config={"source_id": "sforce-reg"},
            transport=transport,
        )

        registry = SourceAdapterRegistry()
        registry.register(adapter)

        self.assertEqual(registry.count(), 1)
        sources = registry.list_sources()
        self.assertEqual(sources[0].source_type, SourceType.SALESFORCE)

        # Discover through registry
        registered = registry.get("sforce-reg")
        docs = list(registered.discover())
        self.assertEqual(len(docs), len(FIXTURE_RECORDS))

    def test_health_through_registry(self):
        transport = MockSalesforceTransport(records=FIXTURE_RECORDS)
        adapter = SalesforceAdapter(
            config={"source_id": "sforce-hreg"},
            transport=transport,
        )
        adapter.setup()

        registry = SourceAdapterRegistry()
        registry.register(adapter)

        health = registry.health_all()
        self.assertEqual(len(health), 1)
        self.assertTrue(health[0].healthy)


if __name__ == "__main__":
    unittest.main()
