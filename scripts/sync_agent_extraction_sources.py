"""
Sync Agent Extraction Sources
================================

Generic runner: syncs every enabled `sql_agent_extraction` source
registered via scripts/register_agent_extraction_sources.py through the
normal Knowledge Fabric ingestion path (chunking, graph entity/relationship
extraction, SEAL unknown-term detection — same pipeline every other
source, and the 2D/3D knowledge graph, already goes through).

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

    from kurukshetra.runtime.knowledge_watcher import KnowledgeWatcher
    from kurukshetra.sources.agent_extraction_adapter import load_registered_adapters
    from kurukshetra.sources.persistent_registry import PersistentSourceRegistry

    adapters = load_registered_adapters()
    if args.source_id:
        adapters = [a for a in adapters if a.config["source_id"] == args.source_id]
        if not adapters:
            logger.error("No enabled sql_agent_extraction source registered with id %r", args.source_id)
            return 1

    if not adapters:
        logger.warning(
            "No sql_agent_extraction sources registered. "
            "Run scripts/register_agent_extraction_sources.py first."
        )
        return 0

    registry = PersistentSourceRegistry()
    watcher = KnowledgeWatcher()
    exit_code = 0
    try:
        for adapter in adapters:
            source_id = adapter.config["source_id"]
            health = adapter.health()
            if not health.healthy:
                logger.error("Skipping %s — health check failed: %s", source_id, health.last_error)
                registry.record_sync_result(source_id=source_id, status="error", error=health.last_error)
                exit_code = 1
                continue

            logger.info("Syncing %s ...", source_id)
            result = watcher.sync_adapter(adapter)
            status = "error" if result["errors"] else "success"
            registry.record_sync_result(
                source_id=source_id,
                status=status,
                documents_found=result["new_documents"] + result["updated_documents"] + result["skipped"],
                documents_new=result["new_documents"],
                documents_changed=result["updated_documents"],
                documents_removed=result["deleted_documents"],
                error="; ".join(result["errors"])[:2000] if result["errors"] else "",
            )
            logger.info(
                "  %s: %d new, %d updated, %d skipped, %d deleted, %d error(s) (%.0fms)",
                source_id, result["new_documents"], result["updated_documents"],
                result["skipped"], result["deleted_documents"], len(result["errors"]),
                result["total_time_ms"],
            )
            if result["errors"]:
                exit_code = 1
                for err in result["errors"][:10]:
                    logger.error("  error: %s", err)
    finally:
        watcher.close()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
