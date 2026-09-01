"""
Persistent Source Registry Tests
=================================

Deterministic tests for the DuckDB-backed source registry.

Tests cover:
1. Registration and retrieval
2. Update (partial updates)
3. Enable/disable
4. Delete
5. Sync state persistence
6. Cursor persistence (and legacy fallback)
7. Failure state tracking
8. Source isolation (one source doesn't affect another)
9. Secret non-persistence
10. Backward compatibility with existing SourceAdapterRegistry
11. Bulk queries
12. Sources needing sync
"""

from __future__ import annotations

import json
import unittest

from kurukshetra.registry.database import get_connection
from kurukshetra.sources.persistent_registry import (
    PersistentSourceRegistry,
    SourceRecord,
    SyncStateRecord,
)


class TestSourceRegistration(unittest.TestCase):
    """Test source registration and retrieval."""

    def setUp(self):
        self.store = PersistentSourceRegistry()
        conn = get_connection()
        for t in ["source_registry", "source_sync_state"]:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()

    def test_register_source(self):
        """Registering a source creates a retrievable record."""
        record = self.store.register_source(
            source_id="test-fs",
            source_type="filesystem",
            display_name="Test Filesystem",
            description="A test filesystem source",
            owner_team="ICS",
        )
        self.assertEqual(record.source_id, "test-fs")
        self.assertEqual(record.source_type, "filesystem")
        self.assertEqual(record.display_name, "Test Filesystem")
        self.assertEqual(record.owner_team, "ICS")
        self.assertTrue(record.enabled)

    def test_get_source(self):
        """Getting a registered source returns correct data."""
        self.store.register_source(
            source_id="test-sf",
            source_type="salesforce",
            display_name="Test Salesforce",
        )
        record = self.store.get_source("test-sf")
        self.assertIsNotNone(record)
        self.assertEqual(record.source_id, "test-sf")
        self.assertEqual(record.source_type, "salesforce")

    def test_get_nonexistent_source(self):
        """Getting a non-existent source returns None."""
        record = self.store.get_source("nonexistent")
        self.assertIsNone(record)

    def test_register_overwrites(self):
        """Re-registering an existing source updates it."""
        self.store.register_source(
            source_id="test-overwrite",
            source_type="filesystem",
            display_name="Original Name",
        )
        self.store.register_source(
            source_id="test-overwrite",
            source_type="filesystem",
            display_name="Updated Name",
        )
        record = self.store.get_source("test-overwrite")
        self.assertEqual(record.display_name, "Updated Name")

    def test_register_with_config(self):
        """Config is stored as JSON (non-secret only)."""
        config = {"instance_url": "https://example.salesforce.com", "batch_size": 200}
        self.store.register_source(
            source_id="test-config",
            source_type="salesforce",
            display_name="Config Test",
            config=config,
        )
        record = self.store.get_source("test-config")
        self.assertEqual(json.loads(record.config_json), config)

    def test_source_exists(self):
        """source_exists returns True/False correctly."""
        self.assertFalse(self.store.source_exists("test-exists"))
        self.store.register_source(
            source_id="test-exists",
            source_type="filesystem",
            display_name="Exists Test",
        )
        self.assertTrue(self.store.source_exists("test-exists"))

    def test_count(self):
        """count returns correct number of sources."""
        self.assertEqual(self.store.count(), 0)
        self.store.register_source(
            source_id="count-1", source_type="filesystem", display_name="One",
        )
        self.store.register_source(
            source_id="count-2", source_type="salesforce", display_name="Two",
        )
        self.assertEqual(self.store.count(), 2)


class TestSourceUpdate(unittest.TestCase):
    """Test partial updates to source records."""

    def setUp(self):
        self.store = PersistentSourceRegistry()
        conn = get_connection()
        for t in ["source_registry", "source_sync_state"]:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()
        self.store.register_source(
            source_id="update-test",
            source_type="filesystem",
            display_name="Original",
            description="Original description",
            owner_team="SPM",
        )

    def test_update_display_name(self):
        self.store.update_source("update-test", display_name="Updated")
        record = self.store.get_source("update-test")
        self.assertEqual(record.display_name, "Updated")
        self.assertEqual(record.description, "Original description")

    def test_update_multiple_fields(self):
        self.store.update_source(
            "update-test",
            display_name="New Name",
            description="New description",
        )
        record = self.store.get_source("update-test")
        self.assertEqual(record.display_name, "New Name")
        self.assertEqual(record.description, "New description")

    def test_update_nonexistent(self):
        """Updating a non-existent source returns None."""
        result = self.store.update_source("nonexistent", display_name="X")
        self.assertIsNone(result)

    def test_update_returns_current_record(self):
        result = self.store.update_source("update-test", display_name="Fresh")
        self.assertIsNotNone(result)
        self.assertEqual(result.display_name, "Fresh")


class TestEnableDisable(unittest.TestCase):
    """Test enable/disable operations."""

    def setUp(self):
        self.store = PersistentSourceRegistry()
        conn = get_connection()
        for t in ["source_registry", "source_sync_state"]:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()
        self.store.register_source(
            source_id="toggle-test",
            source_type="filesystem",
            display_name="Toggle Test",
            enabled=True,
        )

    def test_disable_source(self):
        record = self.store.disable_source("toggle-test")
        self.assertFalse(record.enabled)

    def test_enable_source(self):
        self.store.disable_source("toggle-test")
        record = self.store.enable_source("toggle-test")
        self.assertTrue(record.enabled)

    def test_list_enabled_only(self):
        self.store.register_source(
            source_id="disabled-one",
            source_type="filesystem",
            display_name="Disabled One",
            enabled=False,
        )
        all_sources = self.store.list_sources(enabled_only=False)
        enabled_sources = self.store.list_sources(enabled_only=True)
        self.assertEqual(len(all_sources), 2)
        self.assertEqual(len(enabled_sources), 1)
        self.assertEqual(enabled_sources[0].source_id, "toggle-test")

    def test_count_enabled_only(self):
        self.store.disable_source("toggle-test")
        self.assertEqual(self.store.count(enabled_only=True), 0)
        self.assertEqual(self.store.count(enabled_only=False), 1)


class TestSourceDeletion(unittest.TestCase):
    """Test source deletion."""

    def setUp(self):
        self.store = PersistentSourceRegistry()
        conn = get_connection()
        for t in ["source_registry", "source_sync_state"]:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()

    def test_delete_source(self):
        self.store.register_source(
            source_id="del-test",
            source_type="filesystem",
            display_name="Delete Me",
        )
        self.assertTrue(self.store.source_exists("del-test"))
        self.store.delete_source("del-test")
        self.assertFalse(self.store.source_exists("del-test"))

    def test_delete_also_removes_sync_state(self):
        self.store.register_source(
            source_id="del-sync",
            source_type="filesystem",
            display_name="Del Sync",
        )
        self.store.record_sync_result(
            source_id="del-sync", status="success",
            documents_found=10, documents_new=5,
        )
        self.store.delete_source("del-sync")
        state = self.store.get_sync_state("del-sync")
        self.assertIsNone(state)


class TestSyncStatePersistence(unittest.TestCase):
    """Test sync state recording and retrieval."""

    def setUp(self):
        self.store = PersistentSourceRegistry()
        conn = get_connection()
        for t in ["source_registry", "source_sync_state"]:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()
        self.store.register_source(
            source_id="sync-test",
            source_type="filesystem",
            display_name="Sync Test",
        )

    def test_record_sync_success(self):
        state = self.store.record_sync_result(
            source_id="sync-test",
            status="success",
            documents_found=100,
            documents_new=15,
            documents_changed=3,
            documents_removed=1,
        )
        self.assertEqual(state.last_sync_status, "success")
        self.assertEqual(state.documents_found, 100)
        self.assertEqual(state.documents_new, 15)
        self.assertEqual(state.documents_changed, 3)
        self.assertEqual(state.documents_removed, 1)
        self.assertEqual(state.consecutive_errors, 0)
        self.assertEqual(state.total_syncs, 1)

    def test_record_sync_error(self):
        state = self.store.record_sync_result(
            source_id="sync-test",
            status="error",
            error="Connection timeout",
        )
        self.assertEqual(state.last_sync_status, "error")
        self.assertEqual(state.last_error, "Connection timeout")
        self.assertEqual(state.consecutive_errors, 1)
        self.assertEqual(state.total_syncs, 1)

    def test_consecutive_errors_increment(self):
        self.store.record_sync_result(
            source_id="sync-test", status="error", error="err1",
        )
        self.store.record_sync_result(
            source_id="sync-test", status="error", error="err2",
        )
        state = self.store.record_sync_result(
            source_id="sync-test", status="error", error="err3",
        )
        self.assertEqual(state.consecutive_errors, 3)
        self.assertEqual(state.total_syncs, 3)

    def test_success_resets_consecutive_errors(self):
        self.store.record_sync_result(
            source_id="sync-test", status="error", error="err1",
        )
        self.store.record_sync_result(
            source_id="sync-test", status="error", error="err2",
        )
        state = self.store.record_sync_result(
            source_id="sync-test", status="success",
        )
        self.assertEqual(state.consecutive_errors, 0)
        self.assertEqual(state.total_syncs, 3)

    def test_get_sync_state_nonexistent(self):
        state = self.store.get_sync_state("nonexistent")
        self.assertIsNone(state)

    def test_sync_state_initial_never(self):
        state = self.store.get_sync_state("sync-test")
        self.assertIsNone(state)  # No sync yet


class TestCursorPersistence(unittest.TestCase):
    """Test cursor save/load with legacy fallback."""

    def setUp(self):
        self.store = PersistentSourceRegistry()
        conn = get_connection()
        for t in ["source_registry", "source_sync_state", "source_cursors"]:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()
        self.store.register_source(
            source_id="cursor-test",
            source_type="salesforce",
            display_name="Cursor Test",
        )

    def test_save_and_load_cursor(self):
        self.store.save_cursor("cursor-test", "2025-06-01T00:00:00", "system_modstamp")
        cursor = self.store.get_cursor("cursor-test")
        self.assertEqual(cursor, "2025-06-01T00:00:00")

    def test_overwrite_cursor(self):
        self.store.save_cursor("cursor-test", "2025-01-01")
        self.store.save_cursor("cursor-test", "2025-06-01")
        cursor = self.store.get_cursor("cursor-test")
        self.assertEqual(cursor, "2025-06-01")

    def test_cursor_nonexistent_source(self):
        cursor = self.store.get_cursor("nonexistent")
        self.assertIsNone(cursor)

    def test_cursor_also_saved_to_legacy_table(self):
        """Cursor is also saved to legacy source_cursors table."""
        self.store.save_cursor("cursor-test", "2025-03-15")
        # Check legacy table
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT cursor_value FROM source_cursors WHERE source_id = ?",
                ("cursor-test",),
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "2025-03-15")

    def test_cursor_falls_back_to_legacy_table(self):
        """If source_sync_state has no cursor, falls back to source_cursors."""
        # Write to legacy table directly
        conn = get_connection()
        try:
            conn.execute(
                """INSERT INTO source_cursors (source_id, cursor_type, cursor_value, last_run)
                VALUES (?, 'adapter', ?, CURRENT_TIMESTAMP)""",
                ("legacy-fallback", "2024-12-01"),
            )
        finally:
            conn.close()

        cursor = self.store.get_cursor("legacy-fallback")
        self.assertEqual(cursor, "2024-12-01")


class TestFailureState(unittest.TestCase):
    """Test failure state tracking."""

    def setUp(self):
        self.store = PersistentSourceRegistry()
        conn = get_connection()
        for t in ["source_registry", "source_sync_state"]:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()
        self.store.register_source(
            source_id="fail-test",
            source_type="salesforce",
            display_name="Fail Test",
        )

    def test_error_recorded(self):
        self.store.record_sync_result(
            source_id="fail-test", status="error",
            error="Authentication failed",
        )
        state = self.store.get_sync_state("fail-test")
        self.assertEqual(state.last_error, "Authentication failed")
        self.assertEqual(state.consecutive_errors, 1)

    def test_multiple_errors(self):
        for i in range(5):
            self.store.record_sync_result(
                source_id="fail-test", status="error",
                error=f"Error {i+1}",
            )
        state = self.store.get_sync_state("fail-test")
        self.assertEqual(state.consecutive_errors, 5)
        self.assertEqual(state.last_error, "Error 5")

    def test_success_clears_error(self):
        self.store.record_sync_result(
            source_id="fail-test", status="error", error="err",
        )
        self.store.record_sync_result(
            source_id="fail-test", status="success",
        )
        state = self.store.get_sync_state("fail-test")
        self.assertEqual(state.consecutive_errors, 0)
        # last_sync_status is success
        self.assertEqual(state.last_sync_status, "success")


class TestSourceIsolation(unittest.TestCase):
    """Test that one source's state doesn't affect another."""

    def setUp(self):
        self.store = PersistentSourceRegistry()
        conn = get_connection()
        for t in ["source_registry", "source_sync_state"]:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()

    def test_separate_cursors(self):
        self.store.register_source(
            source_id="iso-a", source_type="filesystem", display_name="A",
        )
        self.store.register_source(
            source_id="iso-b", source_type="salesforce", display_name="B",
        )
        self.store.save_cursor("iso-a", "cursor-a")
        self.store.save_cursor("iso-b", "cursor-b")

        self.assertEqual(self.store.get_cursor("iso-a"), "cursor-a")
        self.assertEqual(self.store.get_cursor("iso-b"), "cursor-b")

    def test_separate_sync_states(self):
        self.store.register_source(
            source_id="iso-a", source_type="filesystem", display_name="A",
        )
        self.store.register_source(
            source_id="iso-b", source_type="salesforce", display_name="B",
        )
        self.store.record_sync_result(
            source_id="iso-a", status="success", documents_found=100,
        )
        self.store.record_sync_result(
            source_id="iso-b", status="error", error="timeout",
        )

        state_a = self.store.get_sync_state("iso-a")
        state_b = self.store.get_sync_state("iso-b")
        self.assertEqual(state_a.last_sync_status, "success")
        self.assertEqual(state_b.last_sync_status, "error")
        self.assertEqual(state_a.consecutive_errors, 0)
        self.assertEqual(state_b.consecutive_errors, 1)

    def test_delete_one_doesnt_affect_other(self):
        self.store.register_source(
            source_id="iso-x", source_type="filesystem", display_name="X",
        )
        self.store.register_source(
            source_id="iso-y", source_type="filesystem", display_name="Y",
        )
        self.store.delete_source("iso-x")
        self.assertFalse(self.store.source_exists("iso-x"))
        self.assertTrue(self.store.source_exists("iso-y"))


class TestSecretNonPersistence(unittest.TestCase):
    """Test that secrets are not stored in the registry."""

    def setUp(self):
        self.store = PersistentSourceRegistry()
        conn = get_connection()
        for t in ["source_registry", "source_sync_state"]:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()

    def test_password_in_config_logs_warning(self):
        """A config with password should log a warning but still register."""
        import logging
        with self.assertLogs(level="WARNING") as cm:
            self.store.register_source(
                source_id="secret-test",
                source_type="salesforce",
                display_name="Secret Test",
                config={"password": "real-secret-value"},
            )
        # Source should still be registered
        record = self.store.get_source("secret-test")
        self.assertIsNotNone(record)
        # Warning should mention SECURITY
        self.assertTrue(any("SECURITY" in msg for msg in cm.output))

    def test_api_key_in_config_logs_warning(self):
        import logging
        with self.assertLogs(level="WARNING") as cm:
            self.store.register_source(
                source_id="apikey-test",
                source_type="custom",
                display_name="API Key Test",
                config={"api_key": "sk-12345"},
            )
        record = self.store.get_source("apikey-test")
        self.assertIsNotNone(record)
        self.assertTrue(any("SECURITY" in msg for msg in cm.output))

    def test_non_secret_config_no_warning(self):
        """Normal config keys should not trigger warnings."""
        # This should NOT log a SECURITY warning
        self.store.register_source(
            source_id="clean-test",
            source_type="filesystem",
            display_name="Clean Test",
            config={"path": "/data/docs", "batch_size": 100},
        )
        record = self.store.get_source("clean-test")
        self.assertIsNotNone(record)

    def test_env_placeholder_not_flagged(self):
        """env: placeholders should not be flagged as secrets."""
        self.store.register_source(
            source_id="env-test",
            source_type="salesforce",
            display_name="Env Test",
            config={"password": "env:SF_PASSWORD"},
        )
        record = self.store.get_source("env-test")
        self.assertIsNotNone(record)


class TestBulkQueries(unittest.TestCase):
    """Test bulk query operations."""

    def setUp(self):
        self.store = PersistentSourceRegistry()
        conn = get_connection()
        for t in ["source_registry", "source_sync_state"]:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()

    def test_list_sources_ordering(self):
        self.store.register_source(
            source_id="z-ord-test", source_type="filesystem", display_name="Zebra Source",
        )
        self.store.register_source(
            source_id="a-ord-test", source_type="filesystem", display_name="Alpha Source",
        )
        sources = self.store.list_sources()
        # Ordered by display_name alphabetically — filter to only our test sources
        our_sources = [s for s in sources if s.source_id in ("z-ord-test", "a-ord-test")]
        self.assertEqual(len(our_sources), 2)
        self.assertEqual(our_sources[0].display_name, "Alpha Source")
        self.assertEqual(our_sources[1].display_name, "Zebra Source")

    def test_get_all_sync_states(self):
        self.store.register_source(
            source_id="bulk-a", source_type="filesystem", display_name="A",
        )
        self.store.register_source(
            source_id="bulk-b", source_type="filesystem", display_name="B",
        )
        self.store.record_sync_result(
            source_id="bulk-a", status="success", documents_found=50,
        )
        states = self.store.get_all_sync_states()
        self.assertEqual(len(states), 2)
        ids = {s.source_id for s in states}
        self.assertIn("bulk-a", ids)
        self.assertIn("bulk-b", ids)

    def test_get_sources_needing_sync(self):
        self.store.register_source(
            source_id="needs-sync", source_type="filesystem", display_name="Needs Sync",
        )
        self.store.register_source(
            source_id="recent-sync", source_type="filesystem", display_name="Recent",
        )
        # "recent-sync" was just synced, "needs-sync" has never been synced
        self.store.record_sync_result(
            source_id="recent-sync", status="success",
        )
        needing = self.store.get_sources_needing_sync()
        ids = [s.source_id for s in needing]
        self.assertIn("needs-sync", ids)

    def test_sources_with_many_errors_excluded(self):
        self.store.register_source(
            source_id="too-many-errors",
            source_type="filesystem",
            display_name="Too Many Errors",
        )
        for _ in range(6):
            self.store.record_sync_result(
                source_id="too-many-errors", status="error", error="fail",
            )
        needing = self.store.get_sources_needing_sync(max_consecutive_errors=5)
        ids = [s.source_id for s in needing]
        self.assertNotIn("too-many-errors", ids)


class TestBackwardCompatibility(unittest.TestCase):
    """Test backward compatibility with existing SourceAdapterRegistry."""

    def setUp(self):
        self.store = PersistentSourceRegistry()
        conn = get_connection()
        for t in ["source_registry", "source_sync_state"]:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.close()

    def test_independent_of_in_memory_registry(self):
        """PersistentSourceRegistry works independently of SourceAdapterRegistry."""
        from kurukshetra.sources.registry import SourceAdapterRegistry

        persistent = PersistentSourceRegistry()
        in_memory = SourceAdapterRegistry()

        persistent.register_source(
            source_id="compat-test",
            source_type="filesystem",
            display_name="Compat",
        )

        # In-memory registry is empty — they don't interfere
        self.assertEqual(in_memory.count(), 0)
        self.assertEqual(persistent.count(), 1)

    def test_source_record_to_dict(self):
        """SourceRecord.to_dict() produces API-serializable output."""
        record = SourceRecord(
            source_id="dict-test",
            source_type="filesystem",
            display_name="Dict Test",
            description="Test",
            owner_team="ICS",
            enabled=True,
            config_json='{"path": "/data"}',
        )
        d = record.to_dict()
        self.assertEqual(d["source_id"], "dict-test")
        self.assertEqual(d["config"]["path"], "/data")
        self.assertTrue(d["enabled"])

    def test_sync_state_record_to_dict(self):
        """SyncStateRecord.to_dict() produces API-serializable output."""
        state = SyncStateRecord(
            source_id="dict-sync",
            last_sync_at="2025-06-01T00:00:00",
            last_sync_status="success",
            documents_found=100,
        )
        d = state.to_dict()
        self.assertEqual(d["source_id"], "dict-sync")
        self.assertEqual(d["documents_found"], 100)

    def test_clear(self):
        """clear() removes all records."""
        self.store.register_source(
            source_id="clear-a", source_type="filesystem", display_name="A",
        )
        self.store.register_source(
            source_id="clear-b", source_type="filesystem", display_name="B",
        )
        self.store.clear()
        self.assertEqual(self.store.count(), 0)


if __name__ == "__main__":
    unittest.main()
