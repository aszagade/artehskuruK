"""
Register Agent Extraction Sources
====================================

The config-only entry point for the Care/ICS agent-extraction knowledge
source (see kurukshetra/sources/agent_extraction_adapter.py).

To add another team's database (or a new table generation on an existing
one) LATER, do NOT write a new file — either:

  1. Add an entry to SOURCES below and re-run this script (idempotent:
     register_source() is an upsert, safe to re-run any time), or
  2. Call `PersistentSourceRegistry().register_source(...)` directly,
     e.g. from a notebook/REPL, with the same shape as an entry below.

Either way, kurukshetra/sources/agent_extraction_adapter.py and
scripts/sync_agent_extraction_sources.py need zero changes — they read
whatever is registered here at sync time.

Requires AGENT_DB_USER / AGENT_DB_PASSWORD in the environment before
sourcing data (not required just to register — registration stores no
secrets), and pyodbc + "ODBC Driver 18 for SQL Server" installed for the
sync step.

Usage:
    python scripts/register_agent_extraction_sources.py
"""
from __future__ import annotations

from kurukshetra.sources.persistent_registry import PersistentSourceRegistry

AGENT_DB_SERVER = "172.26.122.106"

# Each entry fully describes one team's source. Add a new dict here for a
# new team/database — nothing else in the codebase needs to change.
SOURCES: list[dict] = [
    {
        "source_id": "care-email-extraction",
        "display_name": "Care Agent Email Extraction",
        "description": (
            "Care team support-conversation metadata (case numbers, issue/"
            "error types, SLA, property) extracted by the Care email agent. "
            "Legacy table is a frozen historical snapshot; V3 is the active, "
            "incrementally-synced system of record."
        ),
        "owner_team": "Support",
        "default_visibility": "Internal",
        "config": {
            "server": AGENT_DB_SERVER,
            "database": "CareAgent",
            "team": "care",
            "tables": [
                {"name": "Care_Email_Extraction", "version_tag": "legacy", "cursor_column": None},
                {"name": "Care_Email_Extraction_V3", "version_tag": "v3", "cursor_column": "last_updated_at"},
            ],
        },
    },
    {
        "source_id": "ics-email-extraction",
        "display_name": "ICS Agent Email Extraction",
        "description": (
            "ICS team support-conversation metadata, same shape as Care. "
            "The legacy table (ICS_Email_Extraction) is currently empty — "
            "harmless no-op, not an error — V3 is the only real ICS source today."
        ),
        "owner_team": "SDOPS",
        "default_visibility": "Internal",
        "config": {
            "server": AGENT_DB_SERVER,
            "database": "ICSAgent",
            "team": "ics",
            "tables": [
                {"name": "ICS_Email_Extraction", "version_tag": "legacy", "cursor_column": None},
                {"name": "ICS_Email_Extraction_V3", "version_tag": "v3", "cursor_column": "last_updated_at"},
            ],
        },
    },
]


def main() -> None:
    registry = PersistentSourceRegistry()
    for source in SOURCES:
        record = registry.register_source(
            source_id=source["source_id"],
            source_type="sql_agent_extraction",
            display_name=source["display_name"],
            description=source["description"],
            owner_team=source["owner_team"],
            default_visibility=source["default_visibility"],
            config=source["config"],
        )
        print(f"Registered: {record.source_id} ({record.display_name})")

    print(f"\n{len(SOURCES)} source(s) registered. "
          f"Run scripts/sync_agent_extraction_sources.py to ingest.")


if __name__ == "__main__":
    main()
