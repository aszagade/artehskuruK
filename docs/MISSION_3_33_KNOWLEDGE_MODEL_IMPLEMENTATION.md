# Mission 3.33 — Knowledge Model Wiring

## Date
August 28, 2026

## Objective
Wire the existing `concept_teams` and `document_versions` tables into the actual ingestion pipeline, so that every document ingested through any entry point (API, watcher, CLI) gets proper version tracking and multi-team concept association.

## Problem Identified

The `KnowledgeFabric` had `_track_concepts()` and `document_versions` INSERT code in its `_handle_new_file()` and `_handle_changed()` methods, but these were only called through the `KnowledgeWatcher` path. The primary ingestion entry points — `/api/ingest` and `InboxWatcher` — called `IngestionPipeline.ingest()` directly, completely bypassing the Fabric. This meant:

- **concept_teams**: Always empty (0 records)
- **document_versions**: Always empty (0 records)  
- **document_state**: Always empty (0 records)

Additionally, `_track_concepts()` had two bugs:
1. `SELECT id FROM concept_teams` — but `concept_teams` has no `id` column (PK is `concept_name, team_id`)
2. `WHERE gem.document_id = ?` — but `graph_entity_meta` has no `document_id` column

Both bugs caused silent exceptions swallowed by `except Exception: pass`.

## Changes Made

### 1. `kurukshetra/knowledge/fabric.py`

**FabricIngestResult** — Added `title` and `stages` fields for API compatibility:
```python
title: str = ""
stages: dict = field(default_factory=dict)
```

**`_handle_new_file()`** — Populated `title` and `stages` in return value.

**`_handle_changed()`** — Populated `title` and `stages` in return value.

**`_track_concepts()`** — Fixed two bugs:
- `SELECT id FROM concept_teams` → `SELECT concept_name FROM concept_teams`
- `WHERE gem.document_id = ? OR ge.owner = ?` → `WHERE ge.owner = ?`

**`ingest_file(file_path)`** — New public method. Canonical entry point for file-based ingestion through the Fabric. Handles:
- File existence check
- SHA-256 deduplication (unchanged detection)
- Content change detection (version increment)
- New file full ingestion
- All fabric bookkeeping (document_state, document_versions, concept_teams)

**`backfill_existing_documents()`** — New method. Populates `document_state` and `document_versions` for documents that were ingested before the Fabric was wired in.

### 2. `command_center/backend/routers/documents.py`

**`/api/ingest` endpoint** — Now routes through `KnowledgeFabric.ingest_file()` instead of calling `IngestionPipeline.ingest()` directly. This ensures API-ingested documents get version tracking and concept-team association.

### 3. `kurukshetra/runtime/watcher.py`

**`InboxWatcher.ingest_one()`** — Now routes through `KnowledgeFabric.ingest_file()` with fallback to direct pipeline if Fabric is unavailable. Ensures watcher-ingested documents get full Fabric bookkeeping.

### 4. `tests/test_fabric_wiring.py` (NEW)

8 deterministic tests with per-test database isolation:

| Test | Verifies |
|------|----------|
| `test_document_state_created` | ingest_file creates document_state entry |
| `test_document_version_created` | ingest_file creates document_versions entry |
| `test_same_file_returns_none` | Deduplication detected |
| `test_changed_file_gets_new_version` | Version bump on content change |
| `test_missing_file_returns_error` | Graceful handling of missing files |
| `test_backfill_creates_entries` | Backfill populates missing state/versions |
| `test_concept_teams_after_ingest` | concept_teams populated from graph entities |
| `test_empty_file_ingested` | Empty files handled safely |

## Test Results

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Full suite | 546 | **554** | **+8** |
| Failures | 0 | **0** | 0 |
| New wiring tests | 0 | **8** | +8 |

## Before/After Knowledge State

| Metric | Before | After |
|--------|--------|-------|
| concept_teams records | 0 | Populated on each new ingestion |
| document_versions records | 0 | Populated on each new ingestion |
| document_state records | 0 | Populated on each new ingestion |
| /api/ingest → Fabric | ❌ Bypassed | ✅ Routed through Fabric |
| InboxWatcher → Fabric | ❌ Bypassed | ✅ Routed through Fabric |
| _track_concepts() | ❌ Silently failing | ✅ Working |

## Bugs Fixed

1. **concept_teams SELECT id** — Table has no `id` column; changed to `SELECT concept_name`
2. **graph_entity_meta.document_id** — Column doesn't exist; query now uses `ge.owner` only
3. **API bypass** — `/api/ingest` now routes through KnowledgeFabric
4. **Watcher bypass** — `InboxWatcher.ingest_one()` now routes through KnowledgeFabric

## Backward Compatibility

- All 546 existing tests remain passing
- No API contract changes (IngestResponse fields unchanged)
- No database schema changes
- No new dependencies
- Existing retrieval behavior unchanged
- Existing security behavior unchanged

## Not Changed

- Entity extraction quality (deferred to future mission)
- Retrieval algorithms
- SANJAYA reasoning
- Graph behavior
- SEAL behavior
- Connector architecture

## Git Status

Not committed. Awaiting approval.
