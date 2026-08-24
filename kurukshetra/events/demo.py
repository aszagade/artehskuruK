"""
Event Bus Demo
==============

Demonstrates the Enterprise Event Bus with simulated events
from all 7 source systems.

Usage:
    python -m kurukshetra.events.demo
"""

from __future__ import annotations

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from kurukshetra.events.bus import EventBus
from kurukshetra.events.normalizer import EventNormalizer
from kurukshetra.events.models import SourceSystem


def main():
    print("=" * 60)
    print("  KURUKSHETRA Enterprise Event Bus — Demo")
    print("=" * 60)

    bus = EventBus()
    norm = EventNormalizer()

    # Clear previous demo data for a clean run
    bus.clear()

    # ------------------------------------------------------------------
    # 1. Ingest events from all source systems
    # ------------------------------------------------------------------
    print("\n[1] Ingesting events from 7 source systems...\n")

    events = [
        # Datadog
        norm.normalize_datadog_alert(
            "DD-1001", "G3 RMS API latency spike",
            "P95 latency exceeded 5000ms on g3-api-01",
            priority="critical", team="spm",
        ),
        norm.normalize_datadog_alert(
            "DD-1002", "Opera PMS connection pool exhausted",
            "Connection pool at 100% utilization",
            priority="high", team="ics",
        ),
        norm.normalize_datadog_alert(
            "DD-1003", "G3 RMS API latency spike",  # Duplicate of DD-1001
            "P95 latency exceeded 5000ms on g3-api-01",
            priority="critical", team="spm",
        ),

        # Salesforce
        norm.normalize_salesforce_ticket(
            "SF-5001", "Client cannot upload rates to G3 RMS",
            "Marriott reports 502 error during bulk upload",
            status="open", team="ics",
        ),
        norm.normalize_salesforce_ticket(
            "SF-5002", "OXI integration failing for Hilton properties",
            "All Hilton properties returning timeout on OXI sync",
            status="in_progress", team="ics",
        ),

        # Confluence
        norm.normalize_confluence_page(
            "CONF-2001", "G3 RMS Installation Guide v3.2",
            "SPM", "Updated installation steps for cloud deployment",
            author="john.doe", team="spm",
        ),
        norm.normalize_confluence_page(
            "CONF-2002", "OXI Troubleshooting Runbook",
            "ICS", "Added new error codes from recent incidents",
            author="jane.smith", team="ics",
        ),

        # Teams
        norm.normalize_teams_message(
            "MSG-3001", "spm-alerts",
            "G3 RMS deploy completed. All health checks passing.",
            author="deploy-bot", team="spm",
        ),
        norm.normalize_teams_message(
            "MSG-3002", "general",
            "How do I configure rate upload for Marriott properties?",
            author="new-engineer", team="sdops", is_question=True,
        ),

        # Outlook
        norm.normalize_outlook_email(
            "OUT-4001", "Weekly SPM Performance Report",
            "Attached is the weekly performance summary for G3 RMS.",
            from_address="manager@ideas.com", team="spm",
        ),

        # SQL
        norm.normalize_sql_event(
            "SQL-6001", "SELECT * FROM rate_upload_log WHERE status = 'failed'",
            "g3_rms_prod", team="spm", rows_affected=47, duration_ms=230,
        ),

        # Smartsheet (generic)
        norm.normalize_generic(
            "SM-7001", SourceSystem.SMARTSHEET, "update",
            "Q1 Migration Timeline Updated",
            entity_id="sheet-migration", entity_type="document",
            team="sdops", evidence="Migration timeline shifted by 2 weeks",
        ),
    ]

    result = bus.ingest_batch(events)
    print(f"  Total:     {result.total}")
    print(f"  Inserted:  {result.inserted}")
    print(f"  Deduped:   {result.deduplicated}")
    print(f"  Rejected:  {result.rejected}")

    # ------------------------------------------------------------------
    # 2. Query by source
    # ------------------------------------------------------------------
    print("\n[2] Query by source system...\n")
    for src in SourceSystem:
        count = bus.repository.get_event_count(source=src.value)
        if count > 0:
            print(f"  {src.value:15s} -> {count} event(s)")

    # ------------------------------------------------------------------
    # 3. Query by team
    # ------------------------------------------------------------------
    print("\n[3] Query by team...\n")
    stats = bus.get_stats()
    for team, count in sorted(stats.by_team.items()):
        print(f"  {team:15s} -> {count} event(s)")

    # ------------------------------------------------------------------
    # 4. Demonstrate deduplication
    # ------------------------------------------------------------------
    print("\n[4] Deduplication test...\n")
    dup = norm.normalize_datadog_alert(
        "DD-9999", "G3 RMS API latency spike",  # Same title as DD-1001
        "P95 latency exceeded 5000ms on g3-api-01",
        priority="critical", team="spm",
    )
    inserted = bus.ingest(dup)
    print(f"  Ingested duplicate alert: inserted={inserted}")
    print(f"  Total deduplicated events: {bus.repository.get_deduplicated_count()}")

    # ------------------------------------------------------------------
    # 5. Full statistics
    # ------------------------------------------------------------------
    print("\n[5] Full statistics...\n")
    stats = bus.get_stats()
    print(f"  Total events:        {stats.total_events}")
    print(f"  Deduplicated:        {stats.deduplicated_count}")
    print(f"  By source:           {stats.by_source}")
    print(f"  By entity type:      {stats.by_type}")
    print(f"  By team:             {stats.by_team}")
    print(f"  By status:           {stats.by_status}")

    # ------------------------------------------------------------------
    # 6. Show sample event
    # ------------------------------------------------------------------
    print("\n[6] Sample event (first from query)...\n")
    sample = bus.query(limit=1)
    if sample:
        e = sample[0]
        print(f"  ID:         {e.event_id}")
        print(f"  Source:     {e.source.value}")
        print(f"  Entity:     {e.entity_type.value} / {e.entity_id}")
        print(f"  Title:      {e.title}")
        print(f"  Team:       {e.team}")
        print(f"  Evidence:   {e.evidence[:100]}")
        print(f"  Fingerprint:{e.fingerprint}")

    print("\n" + "=" * 60)
    print("  Demo complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
