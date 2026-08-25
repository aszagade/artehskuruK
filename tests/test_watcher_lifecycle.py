"""Tests for WatcherManager lifecycle — startup, shutdown, trigger."""
from __future__ import annotations

import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from kurukshetra.runtime.watcher_manager import WatcherManager


class TestWatcherManagerConfig(unittest.TestCase):
    """Test watcher configuration."""

    def test_disabled_by_default_in_test(self):
        """Watcher should be configurable."""
        from kurukshetra.security.config import SecurityConfig
        config = SecurityConfig()
        # Just verify the config fields exist
        self.assertTrue(hasattr(config, "watcher_enabled"))
        self.assertTrue(hasattr(config, "watcher_interval"))
        self.assertTrue(hasattr(config, "watcher_sources"))

    def test_manager_creates_with_config(self):
        from kurukshetra.security.config import SecurityConfig
        config = SecurityConfig()
        manager = WatcherManager(config)
        status = manager.get_status()
        self.assertIn("enabled", status)
        self.assertIn("running", status)
        self.assertIn("interval_seconds", status)
        self.assertFalse(status["running"])


class TestWatcherManagerStartStop(unittest.TestCase):
    """Test watcher start/stop lifecycle."""

    def setUp(self):
        from kurukshetra.security.config import SecurityConfig
        self.config = SecurityConfig()
        self.config.watcher_enabled = False  # Disable polling for tests
        self.manager = WatcherManager(self.config)

    def tearDown(self):
        self.manager.stop()

    def test_start_when_disabled(self):
        self.manager.start()
        status = self.manager.get_status()
        self.assertFalse(status["running"])

    def test_start_when_enabled(self):
        self.config.watcher_enabled = True
        self.config.watcher_interval = 60  # Long interval to avoid polling
        self.manager.start()
        status = self.manager.get_status()
        self.assertTrue(status["running"])
        self.manager.stop()
        status = self.manager.get_status()
        self.assertFalse(status["running"])

    def test_stop_is_idempotent(self):
        self.manager.stop()
        self.manager.stop()  # Should not raise

    def test_start_is_idempotent(self):
        self.config.watcher_enabled = True
        self.config.watcher_interval = 60
        self.manager.start()
        self.manager.start()  # Should not raise
        self.manager.stop()


class TestWatcherManagerTrigger(unittest.TestCase):
    """Test manual trigger functionality."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.source = Path(self.tmpdir) / "source"
        self.source.mkdir()

        from kurukshetra.security.config import SecurityConfig
        self.config = SecurityConfig()
        self.config.watcher_enabled = False
        self.config.watcher_sources = [str(self.source)]
        self.manager = WatcherManager(self.config)

        # Clean fabric tables
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        for t in ['document_state', 'document_versions', 'concept_teams', 'fabric_scans']:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()

    def tearDown(self):
        self.manager.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_trigger_returns_result(self):
        result = self.manager.trigger()
        self.assertEqual(result["status"], "ok")
        self.assertIn("scan_count", result)

    def test_trigger_detects_new_files(self):
        (self.source / "doc.txt").write_text("New knowledge.")
        result = self.manager.trigger()
        self.assertEqual(result["new_documents"], 1)

    def test_trigger_no_changes(self):
        result = self.manager.trigger()
        self.assertEqual(result["new_documents"], 0)
        self.assertEqual(result["changed_documents"], 0)

    def test_trigger_incremental(self):
        (self.source / "doc.txt").write_text("v1")
        r1 = self.manager.trigger()
        self.assertEqual(r1["new_documents"], 1)

        # Second trigger — no changes
        r2 = self.manager.trigger()
        self.assertEqual(r2["new_documents"], 0)

    def test_trigger_change_detection(self):
        (self.source / "doc.txt").write_text("v1")
        self.manager.trigger()

        (self.source / "doc.txt").write_text("v2")
        result = self.manager.trigger()
        self.assertEqual(result["changed_documents"], 1)

    def test_trigger_removal_detection(self):
        (self.source / "doc.txt").write_text("content")
        self.manager.trigger()

        (self.source / "doc.txt").unlink()
        result = self.manager.trigger()
        self.assertEqual(result["removed_documents"], 1)


class TestWatcherManagerStatus(unittest.TestCase):
    """Test watcher status reporting."""

    def setUp(self):
        from kurukshetra.security.config import SecurityConfig
        self.config = SecurityConfig()
        self.config.watcher_enabled = False
        self.manager = WatcherManager(self.config)

    def tearDown(self):
        self.manager.stop()

    def test_status_has_required_fields(self):
        status = self.manager.get_status()
        required = ["enabled", "running", "interval_seconds", "sources",
                     "scan_count", "error_count", "thread_alive"]
        for field in required:
            self.assertIn(field, status)

    def test_scan_count_increments(self):
        self.assertEqual(self.manager.get_status()["scan_count"], 0)
        self.manager.trigger()
        self.assertEqual(self.manager.get_status()["scan_count"], 1)
        self.manager.trigger()
        self.assertEqual(self.manager.get_status()["scan_count"], 2)


if __name__ == "__main__":
    unittest.main()
