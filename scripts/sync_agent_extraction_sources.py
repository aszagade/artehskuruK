"""
Sync Agent Extraction Sources
================================

CLI wrapper around kurukshetra.sources.agent_extraction_adapter.sync_registered_sources()
— syncs every enabled `sql_agent_extraction` source registered via
scripts/register_agent_extraction_sources.py through the normal Knowledge
Fabric ingestion path (chunking, graph entity/relationship extraction, SEAL
unknown-term detection — same pipeline every other source, and the 2D/3D
knowledge graph, already goes through).

The sync logic itself lives in sync_registered_sources() so it's reusable
by anything that wants to trigger a sync — this script is the manual/
on-demand entry point. There is currently NO automatic scheduler for it:
`python -m kurukshetra.runtime` does not call sync_registered_sources()
anywhere. Run this by hand, or wire it into an OS-level scheduled task
(cron / Windows Task Scheduler) if you want it to run periodically.

This file does NOT change when a new team/database is added — it reads
whatever `load_registered_adapters()` finds in the persistent registry.
Add a source in scripts/register_agent_extraction_sources.py; this script
picks it up automatically on the next run.

Requires AGENT_DB_USER / AGENT_DB_PASSWORD in the environment.

Usage:
    python scripts/sync_agent_extraction_sources.py
    python scripts/sync_agent_extraction_sources.py --source-id care-email-extraction

Suitable for a scheduled task (cron / Windows Task Scheduler) — each run
only processes new/changed rows past the previous run's cursor, except
each source's one-time legacy backfill, which runs exactly once ever.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sync_agent_extraction_sources")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-id", default=None,
        help="Sync only this source_id (default: all registered sql_agent_extraction sources).",
    )
    args = parser.parse_args()

    if not os.environ.get("AGENT_DB_USER") or not os.environ.get("AGENT_DB_PASSWORD"):
        logger.error(
            "AGENT_DB_USER and AGENT_DB_PASSWORD must be set in the environment. "
            "Credentials are never read from the source registry or any file."
        )
        return 1

    from kurukshetra.sources.agent_extraction_adapter import (
        load_registered_adapters,
        sync_registered_sources,
    )

    if args.source_id:
        known = {a.config["source_id"] for a in load_registered_adapters()}
        if args.source_id not in known:
            logger.error("No enabled sql_agent_extraction source registered with id %r", args.source_id)
            return 1
    elif not load_registered_adapters():
        logger.warning(
            "No sql_agent_extraction sources registered. "
            "Run scripts/register_agent_extraction_sources.py first."
        )
        return 0

    results = sync_registered_sources(source_id=args.source_id)

    exit_code = 0
    for result in results:
        if result.get("errors"):
            exit_code = 1
            for err in result["errors"][:10]:
                logger.error("  error: %s", err)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
