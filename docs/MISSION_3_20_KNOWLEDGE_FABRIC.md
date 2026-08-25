# Mission 3.20 — Continuous Knowledge Fabric / SANJAYA Brain

## What Was Built

A continuous knowledge maintenance layer that automatically detects new/changed documents, ingests them incrementally, tracks multi-team concepts, detects conflicts, and exposes a machine-readable knowledge state for SANJAYA.

## Architecture

```
Source Directory
  → KnowledgeFabric.scan_source()
  → Change Detection (SHA-256 fingerprinting)
  → FabricIngestResult
  → IngestionPipeline (existing)
  → Document State Tracking
  → Version History
  → Multi-Team Concept Tracking
  → Conflict Detection
  → Knowledge State API
```

## Components

### KnowledgeFabric (`kurukshetra/knowledge/fabric.py`)

Core service providing:

1. **Source Scanning**: Recursive directory scanning with SHA-256 fingerprinting
2. **Change Detection**: NEW_FILE, CONTENT_CHANGED, UNCHANGED, REMOVED
3. **Incremental Ingestion**: Full pipeline for new files, re-ingestion for changed files
4. **Multi-Team Concepts**: Tracks which teams are associated with each entity
5. **Conflict Detection**: Identifies team mismatches across sources
6. **Knowledge State**: Machine-readable state for SANJAYA Brain

### Database Tables

| Table | Purpose |
|-------|---------|
| `document_state` | Tracks document lifecycle (new/indexed/changed/removed) |
| `document_versions` | Version history with SHA-256 and chunk counts |
| `concept_teams` | Multi-team associations for entities |
| `knowledge_conflicts` | Detected knowledge conflicts |
| `fabric_scans` | Scan history for audit trail |

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/knowledge/state` | GET | Machine-readable knowledge state |
| `/api/knowledge/scan` | POST | Scan a source directory |
| `/api/knowledge/concept/{name}/teams` | GET | Multi-team associations |
| `/api/knowledge/history/{doc_id}` | GET | Version history |
| `/api/knowledge/conflicts` | GET | Active conflicts |

## Verified Capabilities

### Before Mission 3.20
- 357/357 tests passing
- No change detection
- No version tracking
- No multi-team concept support
- No knowledge state API
- No conflict detection

### After Mission 3.20
- 386/386 tests passing (+29 new tests)
- SHA-256 fingerprinting for change detection
- Document lifecycle tracking (new/indexed/changed/removed)
- Version history with semantic versioning
- Multi-team concept associations
- Team mismatch conflict detection
- Machine-readable knowledge state API
- Scan history audit trail

## Test Results

| Category | Tests | Status |
|----------|-------|--------|
| Document state enums | 2 | ✅ |
| Change detection | 2 | ✅ |
| Conflict types | 1 | ✅ |
| Version bumping | 4 | ✅ |
| Table creation | 5 | ✅ |
| Source scanning | 5 | ✅ |
| Incremental ingestion | 3 | ✅ |
| Multi-team concepts | 3 | ✅ |
| Conflict detection | 2 | ✅ |
| Knowledge state | 2 | ✅ |
| Document history | 1 | ✅ |
| End-to-end flow | 1 | ✅ |
| **Total** | **29** | **All pass** |

## End-to-End Verification

The following flow was verified:

1. **Scan** source directory → detects 2 new files
2. **Ingest** new files → documents registered, chunks stored, graph built
3. **Scan again** → 2 unchanged files
4. **Modify** a file → detects 1 content change
5. **Ingest change** → document re-indexed, version bumped
6. **Check state** → knowledge state reflects all changes
7. **Check history** → version history shows both versions
8. **Multi-team** → G3 RMS associated with both SPM and ICS
9. **Conflict** → team mismatch detected when entity has multiple owners

## Files Created

| File | Purpose |
|------|---------|
| `kurukshetra/knowledge/__init__.py` | Module exports |
| `kurukshetra/knowledge/fabric.py` | KnowledgeFabric service |
| `command_center/backend/routers/knowledge.py` | Knowledge State API |
| `tests/test_knowledge_fabric.py` | 29 deterministic tests |
| `docs/MISSION_3_20_KNOWLEDGE_FABRIC.md` | This document |

## Files Modified

| File | Change |
|------|--------|
| `command_center/backend/main.py` | Added knowledge router |

## What Is NOT Implemented

- Automatic periodic scanning (requires scheduler)
- Production connector integration (Salesforce, Confluence, etc.)
- LLM-based entity extraction
- Adaptive entity discovery
- Graph-augmented answer generation
- Feedback loop integration
- UI visualization

## Next Steps

1. **Wire scan into runtime watcher** — Auto-scan on file changes
2. **Add periodic scanning** — Cron/scheduler for enterprise sources
3. **Integrate with SANJAYA** — Use knowledge state for query routing
4. **Conflict resolution UI** — Human confirmation of team mismatches
5. **Production connectors** — Salesforce, Confluence, Datadog
