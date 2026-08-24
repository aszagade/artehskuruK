"""Event Bus Tests — deterministic tests for the Enterprise Event Bus."""

from __future__ import annotations

import os
import sys
import time
import unittest
from unittest.mock import patch
import hashlib

# Ensure project root is in path
sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..")))

from kurukshetra.events.models import (
    Event, EventBatch, EventStats, EventStatus,
    SourceSystem, EventType, EntityKind,
)
from kurukshetra.events.normalizer import EventNormalizer
from kurukshetra.events.repository import EventRepository
from kurukshetra.events.bus import EventBus


def _temp_db():
    """Create a temp DuckDB Path for isolated tests."""
    import tempfile
    from pathlib import Path
    return Path(tempfile.gettempdir()) / f"test_events_{os.getpid()}.duckdb"


def _make_event(**overrides) -> Event:
    """Create a minimal valid event for testing."""
    defaults = dict(
        event_id="EVT-TEST-001",
        source=SourceSystem.DATADOG,
        source_type="alert",
        entity_id="svc-payment",
        entity_type=EntityKind.SYSTEM,
        title="Payment service high latency",
        timestamp="2024-01-15T10:00:00Z",
        actor="datadog-monitor",
        team="spm",
        payload={"priority": "high", "latency_ms": 4500},
        evidence="Payment service latency exceeded 4000ms threshold",
        metadata={"region": "us-east-1"},
        fingerprint="",
        status=EventStatus.NEW,
    )
    defaults.update(overrides)
    return Event(**defaults)


# ======================================================================
# Model Tests
# ======================================================================

class TestEventModels(unittest.TestCase):
    """Test Event dataclass creation and defaults."""

    def test_event_creation(self):
        e = _make_event()
        self.assertEqual(e.event_id, "EVT-TEST-001")
        self.assertEqual(e.source, SourceSystem.DATADOG)
        self.assertEqual(e.entity_type, EntityKind.SYSTEM)
        self.assertEqual(e.status, EventStatus.NEW)

    def test_event_defaults(self):
        e = Event(
            event_id="X", source=SourceSystem.INTERNAL, source_type="test",
            entity_id="e", entity_type=EntityKind.UNKNOWN, title="t",
            timestamp="2024-01-01T00:00:00Z", actor="a", team="t",
        )
        self.assertEqual(e.payload, {})
        self.assertEqual(e.evidence, "")
        self.assertEqual(e.metadata, {})
        self.assertEqual(e.fingerprint, "")
        self.assertEqual(e.status, EventStatus.NEW)

    def test_source_system_enum(self):
        self.assertEqual(SourceSystem.DATADOG.value, "datadog")
        self.assertEqual(SourceSystem.SALESFORCE.value, "salesforce")
        self.assertEqual(SourceSystem.CONFLUENCE.value, "confluence")
        self.assertEqual(SourceSystem.TEAMS.value, "teams")
        self.assertEqual(SourceSystem.OUTLOOK.value, "outlook")
        self.assertEqual(SourceSystem.SQL.value, "sql")
        self.assertEqual(SourceSystem.SMARTSHEET.value, "smartsheet")
        self.assertEqual(SourceSystem.INTERNAL.value, "internal")

    def test_entity_kind_enum(self):
        self.assertEqual(EntityKind.SYSTEM.value, "system")
        self.assertEqual(EntityKind.PROCESS.value, "process")
        self.assertEqual(EntityKind.DOCUMENT.value, "document")
        self.assertEqual(EntityKind.UNKNOWN.value, "unknown")

    def test_event_status_enum(self):
        self.assertEqual(EventStatus.NEW.value, "new")
        self.assertEqual(EventStatus.PROCESSED.value, "processed")
        self.assertEqual(EventStatus.DEDUPLICATED.value, "deduplicated")


# ======================================================================
# Normalizer Tests
# ======================================================================

class TestEventNormalizer(unittest.TestCase):
    """Test normalization from all source systems."""

    def setUp(self):
        self.norm = EventNormalizer()

    def test_fingerprint_deterministic(self):
        fp1 = EventNormalizer.compute_fingerprint("datadog", "svc-1", "alert", "High latency")
        fp2 = EventNormalizer.compute_fingerprint("datadog", "svc-1", "alert", "High latency")
        self.assertEqual(fp1, fp2)
        self.assertEqual(len(fp1), 16)

    def test_fingerprint_differs_on_title(self):
        fp1 = EventNormalizer.compute_fingerprint("datadog", "svc-1", "alert", "High latency")
        fp2 = EventNormalizer.compute_fingerprint("datadog", "svc-1", "alert", "Low latency")
        self.assertNotEqual(fp1, fp2)

    def test_fingerprint_differs_on_source(self):
        fp1 = EventNormalizer.compute_fingerprint("datadog", "svc-1", "alert", "Alert")
        fp2 = EventNormalizer.compute_fingerprint("salesforce", "svc-1", "alert", "Alert")
        self.assertNotEqual(fp1, fp2)

    def test_normalize_datadog_alert(self):
        e = self.norm.normalize_datadog_alert(
            alert_id="DD-12345",
            title="CPU spike on web-01",
            body="CPU usage exceeded 95%",
            priority="critical",
            team="spm",
        )
        self.assertEqual(e.source, SourceSystem.DATADOG)
        self.assertEqual(e.event_id, "DD-DD-12345")
        self.assertIn("CPU spike", e.title)
        self.assertEqual(e.team, "spm")
        self.assertNotEqual(e.fingerprint, "")

    def test_normalize_salesforce_ticket(self):
        e = self.norm.normalize_salesforce_ticket(
            ticket_id="SF-9999",
            subject="Client cannot log in to G3 RMS",
            description="User receives 403 error",
            status="open",
            team="ics",
        )
        self.assertEqual(e.source, SourceSystem.SALESFORCE)
        self.assertEqual(e.entity_type, EntityKind.UNKNOWN)
        self.assertIn("G3 RMS", e.title)

    def test_normalize_salesforce_incident(self):
        e = self.norm.normalize_salesforce_ticket(
            ticket_id="SF-8888",
            subject="Production incident: database down",
            description="",
        )
        self.assertEqual(e.entity_type, EntityKind.INCIDENT)

    def test_normalize_confluence_page(self):
        e = self.norm.normalize_confluence_page(
            page_id="CONF-100",
            title="G3 RMS Setup Guide",
            space="SPM",
            content_preview="Step 1: Install prerequisites",
            author="john.doe",
            team="spm",
        )
        self.assertEqual(e.source, SourceSystem.CONFLUENCE)
        self.assertEqual(e.entity_type, EntityKind.DOCUMENT)
        self.assertEqual(e.actor, "john.doe")

    def test_normalize_teams_message(self):
        e = self.norm.normalize_teams_message(
            message_id="MSG-500",
            channel="spm-alerts",
            content="G3 RMS deploy completed successfully",
            author="jane.smith",
            team="spm",
        )
        self.assertEqual(e.source, SourceSystem.TEAMS)
        self.assertEqual(e.entity_type, EntityKind.PERSON)
        self.assertIn("G3 RMS", e.title)

    def test_normalize_teams_question(self):
        e = self.norm.normalize_teams_message(
            message_id="MSG-501",
            channel="general",
            content="How do I configure OXI integration?",
            is_question=True,
        )
        self.assertEqual(e.source_type, "message")
        self.assertTrue(e.payload["is_question"])

    def test_normalize_outlook_email(self):
        e = self.norm.normalize_outlook_email(
            message_id="OUT-200",
            subject="Weekly SPM Report",
            body_preview="Attached is the weekly report...",
            from_address="manager@company.com",
            team="spm",
        )
        self.assertEqual(e.source, SourceSystem.OUTLOOK)
        self.assertEqual(e.entity_type, EntityKind.DOCUMENT)

    def test_normalize_sql_event(self):
        e = self.norm.normalize_sql_event(
            query_id="SQL-300",
            query_text="SELECT * FROM guests WHERE hotel_id = 42",
            database="g3_rms",
            team="spm",
            rows_affected=150,
            duration_ms=120.5,
        )
        self.assertEqual(e.source, SourceSystem.SQL)
        self.assertEqual(e.entity_type, EntityKind.SYSTEM)
        self.assertEqual(e.payload["database"], "g3_rms")

    def test_normalize_generic(self):
        e = self.norm.normalize_generic(
            event_id="GEN-1",
            source=SourceSystem.SMARTSHEET,
            source_type="update",
            title="Project timeline updated",
            entity_id="sheet-42",
            entity_type=EntityKind.DOCUMENT,
            team="cpm",
        )
        self.assertEqual(e.source, SourceSystem.SMARTSHEET)
        self.assertEqual(e.entity_type, EntityKind.DOCUMENT)

    def test_infer_entity_type_incident(self):
        et = EventNormalizer._infer_entity_type("Timeout on payment service", "Connection timed out after 30s")
        self.assertEqual(et, EntityKind.INCIDENT)

    def test_infer_entity_type_process(self):
        et = EventNormalizer._infer_entity_type("Deployment completed", "Build #1234 deployed")
        self.assertEqual(et, EntityKind.PROCESS)

    def test_infer_entity_type_config(self):
        et = EventNormalizer._infer_entity_type("Threshold updated", "CP config parameter changed")
        self.assertEqual(et, EntityKind.CONFIGURATION)

    def test_infer_entity_type_default(self):
        et = EventNormalizer._infer_entity_type("System status check")
        self.assertEqual(et, EntityKind.SYSTEM)


# ======================================================================
# Repository Tests
# ======================================================================

class TestEventRepository(unittest.TestCase):
    """Test DuckDB persistence for events."""

    def setUp(self):
        self.db_path = _temp_db()
        # Patch DATABASE_PATH before creating repo
        self._patcher = patch("kurukshetra.registry.database.DATABASE_PATH", self.db_path)
        self._patcher.start()
        self.repo = EventRepository()

    def tearDown(self):
        self._patcher.stop()
        if self.db_path.exists():
            self.db_path.unlink()
        for suffix in (".wal", ".tmp"):
            p = self.db_path.with_suffix(self.db_path.suffix + suffix)
            if p.exists():
                p.unlink()

    def test_insert_and_get(self):
        e = _make_event()
        result = self.repo.insert_event(e)
        self.assertTrue(result)
        fetched = self.repo.get_event("EVT-TEST-001")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.event_id, "EVT-TEST-001")
        self.assertEqual(fetched.source, SourceSystem.DATADOG)
        self.assertEqual(fetched.team, "spm")

    def test_insert_duplicate_returns_false(self):
        e = _make_event()
        self.assertTrue(self.repo.insert_event(e))
        self.assertFalse(self.repo.insert_event(e))

    def test_fingerprint_dedup(self):
        e1 = _make_event(event_id="EVT-A")
        e1.fingerprint = EventNormalizer.compute_fingerprint("datadog", "svc", "alert", "Alert")
        e2 = _make_event(event_id="EVT-B")
        e2.fingerprint = e1.fingerprint  # Same fingerprint, different ID
        self.assertTrue(self.repo.insert_event(e1))
        self.assertFalse(self.repo.insert_event(e2))  # Deduplicated

    def test_insert_batch(self):
        events = [_make_event(event_id=f"EVT-{i}") for i in range(5)]
        batch = self.repo.insert_events(events)
        self.assertEqual(batch.total, 5)
        self.assertEqual(batch.inserted, 5)
        self.assertEqual(batch.deduplicated, 0)

    def test_insert_batch_with_duplicates(self):
        events = [_make_event(event_id="EVT-1"), _make_event(event_id="EVT-1")]
        batch = self.repo.insert_events(events)
        self.assertEqual(batch.total, 2)
        self.assertEqual(batch.inserted, 1)
        self.assertEqual(batch.deduplicated, 1)

    def test_get_events_filters(self):
        self.repo.insert_event(_make_event(event_id="EVT-1", source=SourceSystem.DATADOG, team="spm"))
        self.repo.insert_event(_make_event(event_id="EVT-2", source=SourceSystem.SALESFORCE, team="ics"))
        self.repo.insert_event(_make_event(event_id="EVT-3", source=SourceSystem.DATADOG, team="ics"))

        by_source = self.repo.get_events(source="datadog")
        self.assertEqual(len(by_source), 2)

        by_team = self.repo.get_events(team="ics")
        self.assertEqual(len(by_team), 2)

        by_both = self.repo.get_events(source="datadog", team="ics")
        self.assertEqual(len(by_both), 1)

    def test_get_event_count(self):
        self.assertEqual(self.repo.get_event_count(), 0)
        self.repo.insert_event(_make_event(event_id="EVT-1"))
        self.assertEqual(self.repo.get_event_count(), 1)

    def test_update_status(self):
        self.repo.insert_event(_make_event())
        self.repo.update_status("EVT-TEST-001", EventStatus.PROCESSED)
        fetched = self.repo.get_event("EVT-TEST-001")
        self.assertEqual(fetched.status, EventStatus.PROCESSED)

    def test_stats(self):
        self.repo.insert_event(_make_event(event_id="EVT-1", source=SourceSystem.DATADOG, team="spm"))
        self.repo.insert_event(_make_event(event_id="EVT-2", source=SourceSystem.SALESFORCE, team="ics"))
        stats = self.repo.get_stats()
        self.assertEqual(stats.total_events, 2)
        self.assertIn("datadog", stats.by_source)
        self.assertIn("spm", stats.by_team)

    def test_clear(self):
        self.repo.insert_event(_make_event(event_id="EVT-1"))
        self.repo.insert_event(_make_event(event_id="EVT-2"))
        n = self.repo.clear()
        self.assertEqual(n, 2)
        self.assertEqual(self.repo.get_event_count(), 0)

    def test_deduplicated_count(self):
        e1 = _make_event(event_id="EVT-1")
        e1.fingerprint = "fp-dup-001"
        e2 = _make_event(event_id="EVT-2")
        e2.fingerprint = "fp-dup-001"
        self.repo.insert_event(e1)
        self.repo.insert_event(e2)
        self.assertEqual(self.repo.get_deduplicated_count(), 1)


# ======================================================================
# Bus Tests
# ======================================================================

class TestEventBus(unittest.TestCase):
    """Test the EventBus integration layer."""

    def setUp(self):
        self.db_path = _temp_db()
        self._patcher = patch("kurukshetra.registry.database.DATABASE_PATH", self.db_path)
        self._patcher.start()
        self.bus = EventBus()

    def tearDown(self):
        self._patcher.stop()
        if self.db_path.exists():
            self.db_path.unlink()
        for suffix in (".wal", ".tmp"):
            p = self.db_path.with_suffix(self.db_path.suffix + suffix)
            if p.exists():
                p.unlink()

    def test_ingest_single(self):
        e = _make_event()
        self.assertTrue(self.bus.ingest(e))
        fetched = self.bus.get_event("EVT-TEST-001")
        self.assertIsNotNone(fetched)

    def test_ingest_dedup(self):
        e1 = _make_event(event_id="EVT-1")
        e2 = _make_event(event_id="EVT-2")
        e2.fingerprint = EventNormalizer.compute_fingerprint(
            e1.source.value, e1.entity_id, e1.source_type, e1.title
        )
        e1.fingerprint = e2.fingerprint
        self.assertTrue(self.bus.ingest(e1))
        self.assertFalse(self.bus.ingest(e2))

    def test_ingest_batch(self):
        events = [_make_event(event_id=f"EVT-{i}", title=f"Event {i}") for i in range(10)]
        result = self.bus.ingest_batch(events)
        self.assertEqual(result.total, 10)
        self.assertEqual(result.inserted, 10)

    def test_query(self):
        self.bus.ingest(_make_event(event_id="EVT-1", team="spm"))
        self.bus.ingest(_make_event(event_id="EVT-2", team="ics"))
        results = self.bus.query(team="spm")
        self.assertEqual(len(results), 1)

    def test_stats(self):
        self.bus.ingest(_make_event(event_id="EVT-1"))
        stats = self.bus.get_stats()
        self.assertEqual(stats.total_events, 1)

    def test_clear(self):
        self.bus.ingest(_make_event(event_id="EVT-1"))
        n = self.bus.clear()
        self.assertEqual(n, 1)

    def test_ingest_auto_fingerprint(self):
        e = _make_event()
        self.assertEqual(e.fingerprint, "")
        self.bus.ingest(e)
        self.assertNotEqual(e.fingerprint, "")

    def test_ingest_raw(self):
        raw = {
            "event_id": "RAW-001",
            "source_type": "alert",
            "title": "Test alert",
            "entity_id": "svc-test",
            "team": "spm",
        }
        event = self.bus.ingest_raw(raw, "datadog")
        self.assertEqual(event.source, SourceSystem.DATADOG)
        self.assertEqual(event.title, "Test alert")


# ======================================================================
# Integration: Multi-Source Scenario
# ======================================================================

class TestMultiSourceScenario(unittest.TestCase):
    """Simulate events from multiple enterprise systems."""

    def setUp(self):
        self.db_path = _temp_db()
        self._patcher = patch("kurukshetra.registry.database.DATABASE_PATH", self.db_path)
        self._patcher.start()
        self.bus = EventBus()
        self.norm = EventNormalizer()

    def tearDown(self):
        self._patcher.stop()
        if self.db_path.exists():
            self.db_path.unlink()
        for suffix in (".wal", ".tmp"):
            p = self.db_path.with_suffix(self.db_path.suffix + suffix)
            if p.exists():
                p.unlink()

    def test_all_sources_ingest(self):
        """Events from all 7 source systems ingest correctly."""
        events = [
            self.norm.normalize_datadog_alert("DD-1", "CPU high", "95%", team="spm"),
            self.norm.normalize_salesforce_ticket("SF-1", "Login issue", "403 error", team="ics"),
            self.norm.normalize_confluence_page("C-1", "Setup Guide", "SPM", team="spm"),
            self.norm.normalize_teams_message("T-1", "general", "Hello team", team="sdops"),
            self.norm.normalize_outlook_email("O-1", "Weekly Report", "Attached...", team="cpm"),
            self.norm.normalize_sql_event("SQL-1", "SELECT * FROM guests", "g3_rms", team="spm"),
            self.norm.normalize_generic("G-1", SourceSystem.SMARTSHEET, "update", "Timeline", team="cpm"),
        ]
        result = self.bus.ingest_batch(events)
        self.assertEqual(result.inserted, 7)
        self.assertEqual(result.deduplicated, 0)

        stats = self.bus.get_stats()
        self.assertEqual(stats.total_events, 7)
        self.assertEqual(len(stats.by_source), 7)

    def test_cross_source_dedup(self):
        """Same event from two different sources does NOT dedup (different fingerprints)."""
        e1 = self.norm.normalize_datadog_alert("DD-1", "Alert", "body", team="spm")
        e2 = self.norm.normalize_salesforce_ticket("SF-1", "Alert", "body", team="spm")
        # Different sources → different fingerprints
        self.assertNotEqual(e1.fingerprint, e2.fingerprint)
        self.assertTrue(self.bus.ingest(e1))
        self.assertTrue(self.bus.ingest(e2))
        self.assertEqual(self.bus.get_stats().total_events, 2)

    def test_same_source_dedup(self):
        """Same alert from Datadog arriving twice → deduplicated."""
        e1 = self.norm.normalize_datadog_alert("DD-1", "CPU spike", "95%", team="spm")
        e2 = self.norm.normalize_datadog_alert("DD-2", "CPU spike", "95%", team="spm")
        # Same source + same title + same entity → same fingerprint
        self.assertEqual(e1.fingerprint, e2.fingerprint)
        self.assertTrue(self.bus.ingest(e1))
        self.assertFalse(self.bus.ingest(e2))
        self.assertEqual(self.bus.get_stats().total_events, 1)


if __name__ == "__main__":
    unittest.main()
