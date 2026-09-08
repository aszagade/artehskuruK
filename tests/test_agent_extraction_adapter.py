"""
Tests for AgentExtractionAdapter.

All tests use a mocked transport (no live SQL Server, no real DuckDB
fabric for cursor persistence) — deterministic, matching this repo's
existing test philosophy (see SKILLS.md "Write a deterministic test").
"""
from __future__ import annotations

import json

import pytest

from kurukshetra.sources.agent_extraction_adapter import (
    BACKFILL_DONE_MARKER,
    AgentExtractionAdapter,
)
from kurukshetra.sources.models import SourceType


def _care_config(**overrides):
    cfg = {
        "source_id": "care-email-extraction-test",
        "display_name": "Care Agent Email Extraction (test)",
        "server": "test-server",
        "database": "CareAgent",
        "team": "care",
        "team_owner": "Support",
        "default_visibility": "Internal",
        "tables": [
            {"name": "Care_Email_Extraction", "version_tag": "legacy", "cursor_column": None},
            {"name": "Care_Email_Extraction_V3", "version_tag": "v3", "cursor_column": "last_updated_at"},
        ],
    }
    cfg.update(overrides)
    return cfg


def _make_adapter(config=None, mute_cursor_save=True):
    adapter = AgentExtractionAdapter(config=config or _care_config())
    if mute_cursor_save:
        adapter._save_cursor = lambda value: None  # avoid touching a real fabric/DuckDB
    return adapter


# ── Config validation ───────────────────────────────────────────────

class TestConfigValidation:
    def test_missing_required_key_raises(self):
        cfg = _care_config()
        del cfg["team"]
        with pytest.raises(ValueError, match="team"):
            AgentExtractionAdapter(config=cfg)

    def test_valid_config_constructs(self):
        adapter = _make_adapter()
        assert adapter.config["source_id"] == "care-email-extraction-test"


# ── identify() / capabilities() / health() ──────────────────────────

class TestIdentityAndCapabilities:
    def test_identify_reflects_config(self):
        adapter = _make_adapter()
        identity = adapter.identify()
        assert identity.source_id == "care-email-extraction-test"
        assert identity.source_type == SourceType.SQL
        assert identity.owner_team == "Support"
        assert identity.config["team"] == "care"
        assert identity.config["tables"] == ["Care_Email_Extraction", "Care_Email_Extraction_V3"]

    def test_capabilities_declare_incremental_and_versioning(self):
        adapter = _make_adapter()
        caps = adapter.capabilities()
        assert caps.supports_incremental is True
        assert caps.supports_versioning is True
        assert caps.supports_deletion is False  # extraction tables never signal deletes

    def test_health_reflects_transport(self):
        adapter = _make_adapter()
        adapter.transport.health_check = lambda: True
        assert adapter.health().healthy is True
        adapter.transport.health_check = lambda: False
        assert adapter.health().healthy is False


# ── Row -> SourceDocument ────────────────────────────────────────────

class TestRowToDocument:
    def test_known_fields_render_in_order(self):
        adapter = _make_adapter()
        row = {
            "conversation_id": "CONV-1",
            "case_number": "CASE-100",
            "cleaned_subject": "G3 rate mismatch",
            "property_name": "Hotel Example",
            "issue_type": "Configuration",
            "issue_status": "Closed",
        }
        table_cfg = adapter.config["tables"][1]  # v3
        doc = adapter._row_to_document(row, table_cfg)
        assert doc is not None
        assert "Case Number: CASE-100" in doc.text_content
        assert doc.text_content.index("Case Number") < doc.text_content.index("Subject")
        assert doc.provenance.version_tag == "v3"
        assert doc.provenance.external_id == "CONV-1"
        assert doc.team_ids == ["care"]
        assert doc.visibility == "Internal"
        assert "CASE-100" in doc.detected_identifiers

    def test_unknown_fields_still_included(self):
        """Schema drift (a new column upstream) must never silently drop
        data — the whole point of the generic row->text design."""
        adapter = _make_adapter()
        row = {
            "conversation_id": "CONV-2",
            "case_number": "CASE-200",
            "brand_new_future_column": "some new value",
        }
        doc = adapter._row_to_document(row, adapter.config["tables"][1])
        assert "Brand New Future Column: some new value" in doc.text_content

    def test_row_without_conversation_id_is_skipped(self):
        adapter = _make_adapter()
        row = {"case_number": "CASE-300"}
        assert adapter._row_to_document(row, adapter.config["tables"][1]) is None

    def test_row_with_no_meaningful_content_is_skipped(self):
        adapter = _make_adapter()
        row = {"conversation_id": "CONV-4"}  # nothing else populated
        assert adapter._row_to_document(row, adapter.config["tables"][1]) is None

    def test_metadata_carries_the_full_original_row(self):
        adapter = _make_adapter()
        row = {"conversation_id": "CONV-5", "case_number": "CASE-500", "property_code": "P-1"}
        doc = adapter._row_to_document(row, adapter.config["tables"][1])
        assert doc.metadata == row


# ── discover() — the cursor/backfill logic ──────────────────────────

class TestDiscover:
    def test_yields_documents_from_all_configured_tables(self):
        adapter = _make_adapter()

        def fake_fetch(table, cursor_column=None, since_value=None, batch_size=500):
            return iter([{"conversation_id": f"{table}-1", "case_number": "C1"}])

        adapter.transport.fetch_rows = fake_fetch
        docs = list(adapter.discover())
        sources = {d.provenance.source_collection for d in docs}
        assert sources == {"Care_Email_Extraction", "Care_Email_Extraction_V3"}

    def test_legacy_table_backfilled_once_then_skipped(self):
        adapter = _make_adapter()
        calls = []

        def fake_fetch(table, cursor_column=None, since_value=None, batch_size=500):
            calls.append(table)
            return iter([{"conversation_id": f"{table}-1", "case_number": "C1"}])

        adapter.transport.fetch_rows = fake_fetch

        # First run: cursor state says legacy is already backfilled.
        cursor = json.dumps({"Care_Email_Extraction": BACKFILL_DONE_MARKER})
        list(adapter.discover(cursor=cursor))

        assert "Care_Email_Extraction" not in calls
        assert "Care_Email_Extraction_V3" in calls

    def test_incremental_table_uses_and_advances_cursor(self):
        adapter = _make_adapter()
        captured = {}

        def fake_fetch(table, cursor_column=None, since_value=None, batch_size=500):
            captured[table] = since_value
            if table == "Care_Email_Extraction_V3":
                return iter([
                    {"conversation_id": "C-1", "case_number": "X", "last_updated_at": "2026-01-01T00:00:00"},
                    {"conversation_id": "C-2", "case_number": "Y", "last_updated_at": "2026-01-02T00:00:00"},
                ])
            return iter([])

        adapter.transport.fetch_rows = fake_fetch
        saved = {}
        adapter._save_cursor = lambda value: saved.setdefault("value", value)

        cursor = json.dumps({"Care_Email_Extraction": BACKFILL_DONE_MARKER, "Care_Email_Extraction_V3": "2025-12-01T00:00:00"})
        list(adapter.discover(cursor=cursor))

        assert captured["Care_Email_Extraction_V3"] == "2025-12-01T00:00:00"
        new_state = json.loads(saved["value"])
        assert new_state["Care_Email_Extraction_V3"] == "2026-01-02T00:00:00"  # advanced to latest row

    def test_cursor_advances_correctly_even_with_out_of_order_rows(self):
        """Regression guard: a first/full-run scan (since_value=None) is
        deliberately unordered at the SQL level (see
        agent_extraction_transport.py's fetch_rows — avoids an expensive
        full-table sort on a large unfiltered scan). The adapter must
        still compute the true max cursor value via comparison, not just
        take whatever value arrived last in whatever order the DB returned
        rows."""
        adapter = _make_adapter()

        def fake_fetch(table, cursor_column=None, since_value=None, batch_size=500):
            if table == "Care_Email_Extraction_V3":
                # Deliberately NOT in ascending order.
                return iter([
                    {"conversation_id": "C-1", "case_number": "X", "last_updated_at": "2026-03-01T00:00:00"},
                    {"conversation_id": "C-2", "case_number": "Y", "last_updated_at": "2026-01-01T00:00:00"},
                    {"conversation_id": "C-3", "case_number": "Z", "last_updated_at": "2026-02-01T00:00:00"},
                ])
            return iter([])

        adapter.transport.fetch_rows = fake_fetch
        saved = {}
        adapter._save_cursor = lambda value: saved.setdefault("value", value)

        cursor = json.dumps({"Care_Email_Extraction": BACKFILL_DONE_MARKER})
        list(adapter.discover(cursor=cursor))

        new_state = json.loads(saved["value"])
        assert new_state["Care_Email_Extraction_V3"] == "2026-03-01T00:00:00"  # the true max, not the last-seen

    def test_one_failing_table_does_not_break_the_other(self):
        adapter = _make_adapter()

        def fake_fetch(table, cursor_column=None, since_value=None, batch_size=500):
            if table == "Care_Email_Extraction":
                raise ConnectionError("simulated failure")
            return iter([{"conversation_id": "OK-1", "case_number": "C1"}])

        adapter.transport.fetch_rows = fake_fetch
        docs = list(adapter.discover())
        assert len(docs) == 1
        assert docs[0].provenance.source_collection == "Care_Email_Extraction_V3"


# ── Registry-driven loading ──────────────────────────────────────────

class TestLoadRegisteredAdapters:
    def test_merges_identity_fields_with_config_json(self, monkeypatch):
        from kurukshetra.sources import agent_extraction_adapter as mod

        class FakeRecord:
            source_id = "ics-email-extraction-test"
            source_type = "sql_agent_extraction"
            display_name = "ICS Agent Email Extraction (test)"
            description = ""
            owner_team = "SDOPS"
            default_visibility = "Internal"

            def to_dict(self):
                return {
                    "config": {
                        "server": "test-server",
                        "database": "ICSAgent",
                        "team": "ics",
                        "tables": [
                            {"name": "ICS_Email_Extraction_V3", "version_tag": "v3", "cursor_column": "last_updated_at"},
                        ],
                    }
                }

        class FakeRegistry:
            def list_sources(self, enabled_only=True):
                return [FakeRecord()]

        monkeypatch.setattr(
            "kurukshetra.sources.persistent_registry.PersistentSourceRegistry",
            FakeRegistry,
        )

        adapters = mod.load_registered_adapters()
        assert len(adapters) == 1
        identity = adapters[0].identify()
        assert identity.source_id == "ics-email-extraction-test"
        assert identity.owner_team == "SDOPS"
        assert identity.config["team"] == "ics"

    def test_ignores_other_source_types(self, monkeypatch):
        from kurukshetra.sources import agent_extraction_adapter as mod

        class FakeRecord:
            source_id = "some-salesforce-source"
            source_type = "salesforce"

        class FakeRegistry:
            def list_sources(self, enabled_only=True):
                return [FakeRecord()]

        monkeypatch.setattr(
            "kurukshetra.sources.persistent_registry.PersistentSourceRegistry",
            FakeRegistry,
        )

        assert mod.load_registered_adapters() == []


class TestSyncRegisteredSources:
    """sync_registered_sources() — the shared periodic-sync entry point
    used by both scripts/sync_agent_extraction_sources.py and the
    runtime's background thread (kurukshetra/runtime/__main__.py)."""

    def test_skips_when_credentials_missing(self, monkeypatch):
        from kurukshetra.sources import agent_extraction_adapter as mod

        monkeypatch.delenv("AGENT_DB_USER", raising=False)
        monkeypatch.delenv("AGENT_DB_PASSWORD", raising=False)

        assert mod.sync_registered_sources() == []

    def test_syncs_each_healthy_adapter_and_records_result(self, monkeypatch):
        from kurukshetra.sources import agent_extraction_adapter as mod

        monkeypatch.setenv("AGENT_DB_USER", "test-user")
        monkeypatch.setenv("AGENT_DB_PASSWORD", "test-pass")

        adapter = AgentExtractionAdapter(config=_care_config(source_id="sync-test-src"))
        adapter.transport.health_check = lambda: True
        monkeypatch.setattr(mod, "load_registered_adapters", lambda: [adapter])

        recorded = []

        class FakeRegistry:
            def record_sync_result(self, **kwargs):
                recorded.append(kwargs)

        monkeypatch.setattr(
            "kurukshetra.sources.persistent_registry.PersistentSourceRegistry",
            FakeRegistry,
        )

        class FakeWatcher:
            def sync_adapter(self, adapter):
                return {
                    "source_id": adapter.config["source_id"],
                    "new_documents": 3, "updated_documents": 1,
                    "deleted_documents": 0, "skipped": 2, "errors": [],
                    "total_time_ms": 12.5,
                }

            def close(self):
                pass

        monkeypatch.setattr(
            "kurukshetra.runtime.knowledge_watcher.KnowledgeWatcher",
            FakeWatcher,
        )

        results = mod.sync_registered_sources()

        assert len(results) == 1
        assert results[0]["source_id"] == "sync-test-src"
        assert results[0]["new_documents"] == 3
        assert len(recorded) == 1
        assert recorded[0]["source_id"] == "sync-test-src"
        assert recorded[0]["status"] == "success"
        assert recorded[0]["documents_new"] == 3

    def test_unhealthy_adapter_recorded_as_error_and_skipped(self, monkeypatch):
        from kurukshetra.sources import agent_extraction_adapter as mod

        monkeypatch.setenv("AGENT_DB_USER", "test-user")
        monkeypatch.setenv("AGENT_DB_PASSWORD", "test-pass")

        adapter = AgentExtractionAdapter(config=_care_config(source_id="unhealthy-src"))
        adapter.transport.health_check = lambda: False
        monkeypatch.setattr(mod, "load_registered_adapters", lambda: [adapter])

        recorded = []

        class FakeRegistry:
            def record_sync_result(self, **kwargs):
                recorded.append(kwargs)

        monkeypatch.setattr(
            "kurukshetra.sources.persistent_registry.PersistentSourceRegistry",
            FakeRegistry,
        )

        class FakeWatcher:
            def sync_adapter(self, adapter):
                raise AssertionError("sync_adapter should not be called for an unhealthy source")

            def close(self):
                pass

        monkeypatch.setattr(
            "kurukshetra.runtime.knowledge_watcher.KnowledgeWatcher",
            FakeWatcher,
        )

        results = mod.sync_registered_sources()

        assert len(results) == 1
        assert results[0]["errors"]
        assert recorded[0]["status"] == "error"
