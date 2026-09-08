"""
KURUKSHETRA Runtime
===================

Start the demo runtime with:

    python -m kurukshetra.runtime

This starts:
  1. FastAPI backend on port 8000
  2. Inbox watcher polling every 5 seconds

Registered SQL agent-extraction sources (Care/ICS) are NOT auto-synced —
by design, registering a source only proves connectivity (health check);
it does not chunk/embed anything. Run scripts/sync_agent_extraction_sources.py
by hand (or via an external scheduler) whenever you actually want that
data pulled into the knowledge graph. See
kurukshetra/sources/agent_extraction_adapter.py's sync_registered_sources()
if you want to wire up automatic syncing later.

Place documents in knowledge/inbox/ to trigger ingestion.
"""

from __future__ import annotations

import sys
import time
import threading
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def run_watcher(poller_interval: float = 5.0) -> None:
    """Background thread: poll inbox and ingest new documents."""
    from kurukshetra.runtime.watcher import InboxWatcher

    watcher = InboxWatcher()
    print(f"[WATCHER] Watching knowledge/inbox/ (poll every {poller_interval}s)")

    while True:
        try:
            files = watcher.scan()
            if files:
                print(f"[WATCHER] Found {len(files)} new document(s)")
                for f in files:
                    print(f"[WATCHER] Ingesting: {f.name}")
                    result = watcher.ingest_one(f)
                    if result.error:
                        print(f"[WATCHER] FAILED: {result.error}")
                    else:
                        print(
                            f"[WATCHER] OK: {result.document_id} | "
                            f"{result.chunks_stored} chunks | "
                            f"{result.entities_extracted} entities | "
                            f"{result.relationships_extracted} relationships | "
                            f"{result.unknown_terms} unknown terms"
                        )
        except Exception as e:
            print(f"[WATCHER] Error: {e}")

        time.sleep(poller_interval)


def main() -> None:
    print("=" * 60)
    print("KURUKSHETRA Runtime")
    print("=" * 60)
    print()
    print("  Knowledge Inbox: knowledge/inbox/")
    print("  Processed:       knowledge/processed/")
    print("  Failed:          knowledge/failed/")
    print("  API:             http://localhost:8000")
    print("  Docs:            http://localhost:8000/docs")
    print()
    print("  Drop a document into knowledge/inbox/ to start.")
    print()

    # Start inbox watcher in background thread
    watcher_thread = threading.Thread(target=run_watcher, daemon=True)
    watcher_thread.start()

    # Start FastAPI server
    import uvicorn
    uvicorn.run(
        "command_center.backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
