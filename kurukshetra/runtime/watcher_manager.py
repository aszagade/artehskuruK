"""
Watcher Manager — Background Knowledge Watching
================================================

Manages the KnowledgeWatcher background polling thread.

- Starts/stops cleanly with the application
- Non-blocking polling (does not block API requests)
- Errors are logged, never kill the application
- Configurable polling interval
- Manual trigger support
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from kurukshetra.security.config import SecurityConfig

logger = logging.getLogger("kurukshetra.watcher")


class WatcherManager:
    """
    Manages the KnowledgeWatcher background polling thread.

    Usage:
        manager = WatcherManager(config)
        manager.start()  # Starts background polling
        manager.trigger()  # Manual on-demand scan
        manager.stop()  # Graceful shutdown
    """

    def __init__(self, config: SecurityConfig | None = None) -> None:
        self.config = config or SecurityConfig()
        self._watcher = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False
        self._last_scan_result = None
        self._scan_count = 0
        self._error_count = 0

    def start(self) -> None:
        """Start the background watcher thread."""
        if not self.config.watcher_enabled:
            logger.info("Knowledge watcher is disabled (KURUKSHETRA_WATCHER_ENABLED=false)")
            return

        if self._running:
            logger.warning("Knowledge watcher is already running")
            return

        self._stop_event.clear()
        self._running = True

        self._thread = threading.Thread(
            target=self._poll_loop,
            name="kurukshetra-watcher",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            f"Knowledge watcher started (interval={self.config.watcher_interval}s, "
            f"sources={self.config.watcher_sources})"
        )

    def stop(self) -> None:
        """Gracefully stop the watcher thread."""
        if not self._running:
            return

        self._stop_event.set()
        self._running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)

        if self._watcher:
            try:
                self._watcher.close()
            except Exception:
                pass
            self._watcher = None

        logger.info("Knowledge watcher stopped")

    def trigger(self) -> dict:
        """
        Manually trigger a scan-and-ingest cycle.

        Returns a summary of the scan result.
        """
        try:
            self._ensure_watcher()
            result = self._watcher.scan_and_ingest()
            self._last_scan_result = result
            self._scan_count += 1

            return {
                "status": "ok",
                "scan_count": self._scan_count,
                "new_documents": result.new_documents,
                "changed_documents": result.changed_documents,
                "removed_documents": result.removed_documents,
                "cache_refreshed": result.cache_refreshed,
                "total_time_ms": result.total_time_ms,
                "errors": result.errors,
            }
        except Exception as e:
            self._error_count += 1
            logger.error(f"Watcher trigger failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "scan_count": self._scan_count,
                "error_count": self._error_count,
            }

    def get_status(self) -> dict:
        """Get current watcher status."""
        return {
            "enabled": self.config.watcher_enabled,
            "running": self._running,
            "interval_seconds": self.config.watcher_interval,
            "sources": self.config.watcher_sources,
            "scan_count": self._scan_count,
            "error_count": self._error_count,
            "thread_alive": self._thread.is_alive() if self._thread else False,
        }

    def _poll_loop(self) -> None:
        """Background polling loop."""
        interval = self.config.watcher_interval

        # Wait for initial delay before first scan
        if not self._stop_event.wait(timeout=min(interval, 5.0)):
            self._do_scan()

        while not self._stop_event.is_set():
            try:
                self._stop_event.wait(timeout=interval)
                if self._stop_event.is_set():
                    break
                self._do_scan()
            except Exception as e:
                logger.error(f"Watcher poll error: {e}")
                self._error_count += 1
                # Continue polling despite errors
                self._stop_event.wait(timeout=interval)

    def _do_scan(self) -> None:
        """Execute a single scan cycle."""
        try:
            self._ensure_watcher()
            result = self._watcher.scan_and_ingest()
            self._last_scan_result = result
            self._scan_count += 1

            if result.new_documents > 0 or result.changed_documents > 0 or result.removed_documents > 0:
                logger.info(
                    f"Watcher scan #{self._scan_count}: "
                    f"new={result.new_documents}, changed={result.changed_documents}, "
                    f"removed={result.removed_documents} ({result.total_time_ms:.0f}ms)"
                )
        except Exception as e:
            self._error_count += 1
            logger.error(f"Watcher scan error: {e}")

    def _ensure_watcher(self) -> None:
        """Lazily create the KnowledgeWatcher."""
        if self._watcher is None:
            from kurukshetra.runtime.knowledge_watcher import KnowledgeWatcher
            self._watcher = KnowledgeWatcher(
                source_dirs=self.config.watcher_sources,
            )


# Global singleton
_manager: Optional[WatcherManager] = None


def get_watcher_manager() -> WatcherManager:
    """Get the global watcher manager instance."""
    global _manager
    if _manager is None:
        _manager = WatcherManager()
    return _manager
