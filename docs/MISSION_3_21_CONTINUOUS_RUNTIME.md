# Mission 3.21 — Continuous Runtime Refresh + SANJAYA Verification

## What Was Automated

The continuous runtime refresh layer that detects new/changed/removed documents, ingests them incrementally, refreshes retrieval caches, and makes knowledge available to SANJAYA without application restart.

## Complete Flow (Verified)

```
Source Directory Change
  → KnowledgeWatcher.scan_and_ingest()
  → KnowledgeFabric.scan_source() (SHA-256 fingerprinting)
  → Change Detection (NEW/CHANGED/REMOVED)
  → IngestionPipeline (extract → clean → register → classify → chunk → graph)
  → Document State Tracking (document_state table)
  → Version History (document_versions table)
  → BM25 Cache Refresh (DatabaseBM25Retriever.invalidate())
  → SANJAYA can immediately answer queries about new knowledge
  → /api/knowledge/state reflects live changes
```

## Components

### KnowledgeWatcher (`kurukshetra/runtime/knowledge_watcher.py`)

Continuous runtime watcher that:
1. Scans source directories for changes
2. Integrates with KnowledgeFabric for change detection
3. Uses existing InboxWatcher for file management
4. Invalidates BM25/Vector caches after ingestion
5. Tracks ingestion lifecycle via StatusTracker

### Key Methods

| Method | Purpose |
|--------|---------|
| `scan_and_ingest()` | Full cycle: scan → detect → ingest → refresh |
| `scan_only()` | Dry-run scan without ingestion |
| `get_knowledge_state()` | Current knowledge state |

## Verified Capabilities

### 1. New Document Detection
- SHA-256 fingerprinting identifies new files
- Full ingestion through canonical pipeline
- Document state tracked as "indexed"

### 2. Duplicate Prevention
- SHA-256 deduplication prevents re-ingestion
- Second scan shows 0 new files

### 3. Content Change Detection
- Modified files detected via SHA-256 change
- Re-ingestion updates chunks and graph
- Version number bumped (1.0.0 → 1.0.1)

### 4. Removal Detection
- Deleted files detected by state comparison
- Document state updated to "removed"

### 5. Version History
- Each ingestion creates a version record
- Changed documents get new version
- Previous versions marked as non-current

### 6. Cache Refresh
- BM25 index invalidated after changes
- Next query rebuilds index with new chunks

### 7. Knowledge State
- /api/knowledge/state reflects live changes
- Documents by state tracked
- Teams and concepts tracked

## Test Results

| Category | Tests | Status |
|----------|-------|--------|
| Watcher scan | 3 | ✅ |
| Change detection | 3 | ✅ |
| Multi-team concepts | 1 | ✅ |
| Version tracking | 2 | ✅ |
| Retrieval exclusion | 1 | ✅ |
| Knowledge state | 2 | ✅ |
| Cache refresh | 2 | ✅ |
| End-to-end lifecycle | 1 | ✅ |
| **Total** | **15** | **All pass** |

## Before → After

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Tests | 386 | **401** | **+15** |
| KnowledgeWatcher | MISSING | **IMPLEMENTED** | New |
| Continuous refresh | MISSING | **IMPLEMENTED** | New |
| Cache invalidation | MISSING | **IMPLEMENTED** | New |
| Version lifecycle | MISSING | **VERIFIED** | End-to-end |

## Files Created

| File | Purpose |
|------|---------|
| `kurukshetra/runtime/knowledge_watcher.py` | KnowledgeWatcher service |
| `tests/test_knowledge_lifecycle.py` | 15 deterministic lifecycle tests |
| `docs/MISSION_3_21_CONTINUOUS_RUNTIME.md` | This document |

## End-to-End Live Test Evidence

The following flow was verified in tests:

1. **New file detected** → `scan_and_ingest()` returns `new_documents=1`
2. **Document ingested** → chunks stored, graph built, state="indexed"
3. **Duplicate prevented** → second scan returns `new_documents=0`
4. **Content changed** → `changed_documents=1`, version bumped
5. **File removed** → `removed_documents=1`, state="removed"
6. **Cache refreshed** → BM25 invalidated, next query uses new data
7. **Knowledge state** → reflects all changes immediately

## Remaining Limitations

1. **No periodic scanning** — Requires manual `scan_and_ingest()` call
2. **No file system events** — Uses polling, not inotify/FSEvents
3. **No concurrent ingestion** — Single-threaded processing
4. **No rollback** — Cannot undo ingestion
5. **No production connectors** — Salesforce, Confluence, etc. not connected

## Recommended Next Milestone

**Wire KnowledgeWatcher into the FastAPI startup** so it runs automatically on server start and can be triggered via API endpoint for on-demand scanning.
