#!/usr/bin/env python3
"""
Opportunity Engine Demo
=======================

Ingests sample enterprise events and runs pattern detection.

Usage:
    python -m kurukshetra.opportunity.demo
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kurukshetra.opportunity.models import Event, SourceSystem
from kurukshetra.opportunity.repository import OpportunityRepository
from kurukshetra.opportunity.detector import OpportunityDetector


SAMPLE_EVENTS = [
    # Datadog alerts — repeated (automation signal)
    Event("DD-001", SourceSystem.DATADOG, "alert", "G3 job timeout on property HLTN-001", "spm", "2025-08-01T09:00:00Z"),
    Event("DD-002", SourceSystem.DATADOG, "alert", "G3 job timeout on property HLTN-001", "spm", "2025-08-02T09:00:00Z"),
    Event("DD-003", SourceSystem.DATADOG, "alert", "G3 job timeout on property HLTN-001", "spm", "2025-08-03T09:00:00Z"),
    Event("DD-004", SourceSystem.DATADOG, "alert", "G3 job timeout on property HLTN-001", "spm", "2025-08-04T09:00:00Z"),
    Event("DD-005", SourceSystem.DATADOG, "alert", "G3 job timeout on property HLTN-001", "spm", "2025-08-05T09:00:00Z"),

    # ICS errors without monitoring (monitoring gap)
    Event("DD-010", SourceSystem.DATADOG, "error", "Opera connectivity timeout", "ics", "2025-08-01T11:00:00Z"),
    Event("DD-011", SourceSystem.DATADOG, "error", "Opera connectivity timeout", "ics", "2025-08-03T11:00:00Z"),
    Event("DD-012", SourceSystem.DATADOG, "failure", "OHIP connection refused", "ics", "2025-08-04T11:00:00Z"),

    # Config changes without docs (documentation gap)
    Event("CONF-001", SourceSystem.SQL, "config_change", "G3 parameter restriction_level", "spm", "2025-08-01T14:00:00Z"),
    Event("CONF-002", SourceSystem.SMARTSHEET, "process_update", "CP pricing config update", "roa", "2025-08-02T14:00:00Z"),

    # Cross-team process (process improvement)
    Event("PROC-001", SourceSystem.TEAMS, "discussion", "Client onboarding workflow", "spm", "2025-08-01T10:00:00Z"),
    Event("PROC-002", SourceSystem.CONFLUENCE, "document_update", "Client onboarding workflow", "cpm", "2025-08-02T10:00:00Z"),
    Event("PROC-003", SourceSystem.SMARTSHEET, "task", "Client onboarding workflow", "ics", "2025-08-03T10:00:00Z"),

    # Duplicate reports across teams
    Event("RPT-001", SourceSystem.SMARTSHEET, "manual_report", "Weekly SLA report", "spm", "2025-08-01T16:00:00Z"),
    Event("RPT-002", SourceSystem.SMARTSHEET, "manual_report", "Weekly SLA report", "ics", "2025-08-01T16:30:00Z"),
    Event("RPT-003", SourceSystem.SMARTSHEET, "manual_report", "Weekly SLA report", "sdops", "2025-08-01T17:00:00Z"),

    # Search queries without docs (knowledge gap)
    Event("Q-001", SourceSystem.INTERNAL, "search", "CP pricing algorithm", "roa", "2025-08-01T08:00:00Z"),
    Event("Q-002", SourceSystem.INTERNAL, "search", "CP pricing algorithm", "roa", "2025-08-02T08:00:00Z"),
    Event("Q-003", SourceSystem.INTERNAL, "search", "CP pricing algorithm", "spm", "2025-08-03T08:00:00Z"),

    # Critical errors on core team (risk)
    Event("RISK-001", SourceSystem.DATADOG, "failure", "Production data feed failure", "sdops", "2025-08-01T03:00:00Z", metadata={"severity": "critical"}),
    Event("RISK-002", SourceSystem.DATADOG, "failure", "Production data feed failure", "sdops", "2025-08-02T03:00:00Z", metadata={"severity": "critical"}),
    Event("RISK-003", SourceSystem.DATADOG, "failure", "Production data feed failure", "sdops", "2025-08-03T03:00:00Z", metadata={"severity": "critical"}),
]


def main() -> None:
    print("Opportunity Engine Demo")
    print("=" * 50)

    # Ingest events
    repo = OpportunityRepository()
    print(f"\nIngesting {len(SAMPLE_EVENTS)} sample events...")
    repo.insert_events(SAMPLE_EVENTS)
    print(f"Events stored: {repo.get_event_count()}")

    # Run detection
    print("\nRunning pattern detection...")
    detector = OpportunityDetector(repo)
    result = detector.run()

    print(f"\nDetection complete in {result.elapsed_seconds}s")
    print(f"Opportunities found: {result.opportunities_found}")
    print(f"Events analyzed: {result.events_analyzed}")

    # Show results
    opps = repo.get_opportunities()
    print(f"\n{'=' * 60}")
    print(f"DETECTED OPPORTUNITIES ({len(opps)})")
    print(f"{'=' * 60}")

    for opp in sorted(opps, key=lambda o: -o.confidence):
        print(f"\n[{opp.category.value.upper()}] {opp.title}")
        print(f"  Team: {opp.affected_team}  |  Frequency: {opp.frequency}  |  Confidence: {opp.confidence:.2f}")
        print(f"  Evidence: {opp.evidence[:120]}...")

    # Stats
    stats = repo.get_stats()
    print(f"\n{'=' * 50}")
    print(f"SUMMARY")
    print(f"{'=' * 50}")
    print(f"  Total events:     {stats['total_events']}")
    print(f"  Total opps:       {stats['total_opportunities']}")
    print(f"  By category:      {stats['by_category']}")
    print(f"  By status:        {stats['by_status']}")


if __name__ == "__main__":
    main()
