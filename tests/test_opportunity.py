"""
Opportunity Engine Tests
========================

Deterministic tests for event storage, pattern detection, and opportunity lifecycle.

Run:
    python -m pytest tests/test_opportunity.py -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kurukshetra.opportunity.models import (
    Event, Opportunity, OpportunityCategory, OpportunityStatus, SourceSystem,
)
from kurukshetra.opportunity.repository import OpportunityRepository
from kurukshetra.opportunity.detector import OpportunityDetector


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _event(
    event_id: str = "EVT-001",
    source: SourceSystem = SourceSystem.DATADOG,
    event_type: str = "alert",
    subject: str = "G3 RMS job failure",
    team: str = "spm",
    timestamp: str = "2025-01-15T10:00:00Z",
    **kwargs,
) -> Event:
    return Event(
        event_id=event_id, source=source, event_type=event_type,
        subject=subject, team=team, timestamp=timestamp, **kwargs,
    )


_TEMP_DB_COUNTER = 0


def _make_repo() -> tuple[OpportunityRepository, str]:
    """Create a temporary DuckDB. Returns (repo, db_path).

    Caller must patch DATABASE_PATH for the test duration.
    """
    global _TEMP_DB_COUNTER
    _TEMP_DB_COUNTER += 1
    tmp = tempfile.mktemp(suffix=f"{_TEMP_DB_COUNTER}.duckdb")

    import kurukshetra.registry.database as db_mod
    db_mod.DATABASE_PATH = type(db_mod.DATABASE_PATH)(tmp)
    repo = OpportunityRepository()
    return repo, tmp


# ------------------------------------------------------------------
# Repository tests
# ------------------------------------------------------------------

class TestOpportunityRepository(unittest.TestCase):

    def setUp(self):
        import kurukshetra.registry.database as db_mod
        self._orig_path = db_mod.DATABASE_PATH
        self.repo, self._db_path = _make_repo()

    def tearDown(self):
        import kurukshetra.registry.database as db_mod
        db_mod.DATABASE_PATH = self._orig_path
        try:
            os.unlink(self._db_path)
        except OSError:
            pass

    def test_insert_and_get_event(self):
        e = _event()
        self.repo.insert_event(e)
        events = self.repo.get_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_id, "EVT-001")

    def test_insert_events_batch(self):
        events = [_event(event_id=f"EVT-{i:03d}") for i in range(5)]
        self.repo.insert_events(events)
        self.assertEqual(self.repo.get_event_count(), 5)

    def test_get_events_filter_by_source(self):
        self.repo.insert_event(_event(source=SourceSystem.DATADOG))
        self.repo.insert_event(_event(event_id="EVT-002", source=SourceSystem.SALESFORCE))
        datadog = self.repo.get_events(source="datadog")
        self.assertEqual(len(datadog), 1)

    def test_get_events_filter_by_team(self):
        self.repo.insert_event(_event(team="spm"))
        self.repo.insert_event(_event(event_id="EVT-002", team="ics"))
        spm = self.repo.get_events(team="spm")
        self.assertEqual(len(spm), 1)

    def test_upsert_and_get_opportunity(self):
        opp = Opportunity(
            opportunity_id="OPP-TEST-001", title="Test opportunity",
            category=OpportunityCategory.AUTOMATION, source_system=SourceSystem.DATADOG,
            affected_team="spm", frequency=5, evidence="Test evidence", confidence=0.8,
        )
        self.repo.upsert_opportunity(opp)
        opps = self.repo.get_opportunities()
        self.assertEqual(len(opps), 1)
        self.assertEqual(opps[0].title, "Test opportunity")

    def test_upsert_increments_frequency(self):
        opp = Opportunity(
            opportunity_id="OPP-TEST-002", title="Test",
            category=OpportunityCategory.AUTOMATION, source_system=SourceSystem.DATADOG,
            affected_team="spm", frequency=3, evidence="evidence", confidence=0.7,
        )
        self.repo.upsert_opportunity(opp)
        opp.frequency = 5
        self.repo.upsert_opportunity(opp)
        stored = self.repo.get_opportunities()
        self.assertEqual(stored[0].frequency, 5)

    def test_update_status(self):
        opp = Opportunity(
            opportunity_id="OPP-TEST-003", title="Test",
            category=OpportunityCategory.MONITORING, source_system=SourceSystem.DATADOG,
            affected_team="spm", frequency=1, evidence="evidence", confidence=0.6,
        )
        self.repo.upsert_opportunity(opp)
        self.repo.update_status("OPP-TEST-003", "approved")
        stored = self.repo.get_opportunities(status="approved")
        self.assertEqual(len(stored), 1)

    def test_get_stats(self):
        self.repo.insert_event(_event())
        opp = Opportunity(
            opportunity_id="OPP-STATS", title="Stats test",
            category=OpportunityCategory.AUTOMATION, source_system=SourceSystem.DATADOG,
            affected_team="spm", frequency=1, evidence="evidence", confidence=0.5,
        )
        self.repo.upsert_opportunity(opp)
        stats = self.repo.get_stats()
        self.assertEqual(stats["total_events"], 1)
        self.assertEqual(stats["total_opportunities"], 1)


# ------------------------------------------------------------------
# Detector tests
# ------------------------------------------------------------------

class TestOpportunityDetector(unittest.TestCase):

    def setUp(self):
        import kurukshetra.registry.database as db_mod
        self._orig_path = db_mod.DATABASE_PATH
        self.repo, self._db_path = _make_repo()

    def tearDown(self):
        import kurukshetra.registry.database as db_mod
        db_mod.DATABASE_PATH = self._orig_path
        try:
            os.unlink(self._db_path)
        except OSError:
            pass

    def test_automation_detection(self):
        events = [_event(event_id=f"EVT-{i:03d}", subject="G3 job failure notification") for i in range(5)]
        self.repo.insert_events(events)
        result = OpportunityDetector(self.repo).run()
        self.assertGreater(result.opportunities_found, 0)
        opps = self.repo.get_opportunities(category="automation")
        self.assertGreater(len(opps), 0)
        self.assertIn("Automate", opps[0].title)

    def test_automation_below_threshold(self):
        events = [_event(event_id="EVT-001"), _event(event_id="EVT-002")]
        self.repo.insert_events(events)
        OpportunityDetector(self.repo).run()
        opps = self.repo.get_opportunities(category="automation")
        self.assertEqual(len(opps), 0)

    def test_monitoring_detection(self):
        events = [
            _event(event_id="EVT-001", event_type="error", team="sdops"),
            _event(event_id="EVT-002", event_type="error", team="sdops"),
            _event(event_id="EVT-003", event_type="failure", team="sdops"),
        ]
        self.repo.insert_events(events)
        OpportunityDetector(self.repo).run()
        opps = self.repo.get_opportunities(category="monitoring")
        self.assertGreater(len(opps), 0)

    def test_monitoring_already_exists(self):
        events = [
            _event(event_id="EVT-001", event_type="error", team="sdops"),
            _event(event_id="EVT-002", event_type="monitoring", team="sdops"),
        ]
        self.repo.insert_events(events)
        OpportunityDetector(self.repo).run()
        opps = self.repo.get_opportunities(category="monitoring")
        self.assertEqual(len(opps), 0)

    def test_documentation_detection(self):
        events = [_event(event_id="EVT-001", event_type="config_change", subject="G3 parameter update")]
        self.repo.insert_events(events)
        OpportunityDetector(self.repo).run()
        opps = self.repo.get_opportunities(category="documentation")
        self.assertGreater(len(opps), 0)

    def test_process_improvement_detection(self):
        events = [
            _event(event_id="EVT-001", subject="Oracle DB migration", team="spm"),
            _event(event_id="EVT-002", subject="Oracle DB migration", team="ics"),
            _event(event_id="EVT-003", subject="Oracle DB migration", team="sdops"),
        ]
        self.repo.insert_events(events)
        OpportunityDetector(self.repo).run()
        opps = self.repo.get_opportunities(category="process_improvement")
        self.assertGreater(len(opps), 0)

    def test_knowledge_gap_detection(self):
        events = [_event(event_id=f"EVT-{i}", event_type="search", subject="CP pricing algorithm") for i in range(3)]
        self.repo.insert_events(events)
        OpportunityDetector(self.repo).run()
        opps = self.repo.get_opportunities(category="knowledge_gap")
        self.assertGreater(len(opps), 0)

    def test_duplicate_work_detection(self):
        events = [
            _event(event_id="EVT-001", event_type="manual_report", subject="Weekly SLA report", team="spm"),
            _event(event_id="EVT-002", event_type="manual_report", subject="Weekly SLA report", team="ics"),
        ]
        self.repo.insert_events(events)
        OpportunityDetector(self.repo).run()
        opps = self.repo.get_opportunities(category="duplicate_work")
        self.assertGreater(len(opps), 0)

    def test_risk_detection(self):
        events = [
            _event(event_id="EVT-001", event_type="error", team="sdops", metadata={"severity": "critical"}),
            _event(event_id="EVT-002", event_type="failure", team="sdops", metadata={"severity": "critical"}),
        ]
        self.repo.insert_events(events)
        OpportunityDetector(self.repo).run()
        opps = self.repo.get_opportunities(category="risk_detection")
        self.assertGreater(len(opps), 0)
        self.assertEqual(opps[0].metadata.get("severity"), "high")

    def test_empty_events_produces_nothing(self):
        result = OpportunityDetector(self.repo).run()
        self.assertEqual(result.opportunities_found, 0)
        self.assertEqual(result.events_analyzed, 0)

    def test_deterministic_ids(self):
        events = [_event(subject="Test subject", team="spm") for _ in range(3)]
        self.repo.insert_events(events)
        OpportunityDetector(self.repo).run()
        opps1 = sorted(self.repo.get_opportunities(), key=lambda o: o.opportunity_id)

        # Run again with same events
        OpportunityDetector(self.repo).run()
        opps2 = sorted(self.repo.get_opportunities(), key=lambda o: o.opportunity_id)
        # IDs should be stable (upsert merges)
        self.assertEqual(len(opps1), len(opps2))

    def test_opportunity_carries_evidence(self):
        events = [_event(subject="Repeated task", team="spm") for _ in range(4)]
        self.repo.insert_events(events)
        OpportunityDetector(self.repo).run()
        for opp in self.repo.get_opportunities():
            self.assertTrue(len(opp.evidence) > 10, f"No evidence: {opp.opportunity_id}")

    def test_confidence_in_range(self):
        events = [_event(subject="Test", team="spm") for _ in range(5)]
        self.repo.insert_events(events)
        OpportunityDetector(self.repo).run()
        for opp in self.repo.get_opportunities():
            self.assertGreaterEqual(opp.confidence, 0.0)
            self.assertLessEqual(opp.confidence, 1.0)


# ------------------------------------------------------------------
# Integration: mixed events
# ------------------------------------------------------------------

class TestMixedEventDetection(unittest.TestCase):

    def setUp(self):
        import kurukshetra.registry.database as db_mod
        self._orig_path = db_mod.DATABASE_PATH
        self.repo, self._db_path = _make_repo()

    def tearDown(self):
        import kurukshetra.registry.database as db_mod
        db_mod.DATABASE_PATH = self._orig_path
        try:
            os.unlink(self._db_path)
        except OSError:
            pass

    def test_multiple_categories_from_mixed_events(self):
        events = [
            _event(event_id=f"AUTO-{i}", event_type="alert", subject="G3 job timeout", team="spm")
            for i in range(5)
        ] + [
            _event(event_id="MON-001", event_type="error", team="ics"),
            _event(event_id="MON-002", event_type="error", team="ics"),
            _event(event_id="PROC-001", subject="Client onboarding", team="spm"),
            _event(event_id="PROC-002", subject="Client onboarding", team="cpm"),
            _event(event_id="RISK-001", event_type="failure", team="sdops", metadata={"severity": "critical"}),
            _event(event_id="RISK-002", event_type="failure", team="sdops", metadata={"severity": "critical"}),
        ]
        self.repo.insert_events(events)
        result = OpportunityDetector(self.repo).run()
        self.assertGreater(result.opportunities_found, 0)
        categories = set(result.categories.keys())
        self.assertIn("automation", categories)


if __name__ == "__main__":
    unittest.main(verbosity=2)
