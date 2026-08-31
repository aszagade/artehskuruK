# Mission 3.56C — Ingestion Quality Gate Hardening

## Summary

Prevented garbage entities from entering the Knowledge Graph during ingestion by adding a
quality gate that runs BEFORE entities are persisted to DuckDB.

## Root Cause

During ingestion, `GraphRepository.upsert_entity()` wrote entities with default
`quality_score=0.5, quality_label='MEDIUM'` regardless of quality. The `apply_quality_scores()`
batch job ran separately AFTER ingestion, leaving a window where garbage entities were already
in the graph.

## What Changed

### `kurukshetra/graph/registry.py` — Ingestion Quality Gate
- Modified `ingest_document()` to call `score_entity()` BEFORE persisting
- Entities with `quality_label == 'NOISE'` are now rejected at ingestion time
- Relationships and evidence for rejected entities are also skipped
- Only entities with quality_label in (HIGH, MEDIUM, LOW) enter the graph

### `kurukshetra/graph/repository.py` — Quality-Aware Upsert
- Modified `upsert_entity()` to accept `quality_score` and `quality_label` parameters
- Uses `GREATEST()` for score updates (higher quality wins on re-ingestion)
- Preserves existing HIGH quality on update (won't downgrade)

### `tests/test_entity_quality_gate.py` — 36 Adversarial Tests
- 10 real organizational entities verified as HIGH (G3, SPM, ICS, OHIP, etc.)
- 15 garbage entities verified as NOISE (stopwords, numbers, fragments, etc.)
- 6 edge cases (empty, whitespace, short, dates, ranges)
- 5 multi-word entity tests

## Current Graph State (before gate)

| Type | Count | Quality |
|------|-------|---------|
| knowledge_article | 2,163 | Fine (chunk entities) |
| process | 1,232 | Many noise |
| document | 612 | Fine |
| job | 244 | Many noise |
| incident | 227 | Mixed |
| configuration | 90 | Mixed |
| system | 24 | Good |
| team | 7 | Good |
| **Total** | **4,679** | |

Known noise: `file`, `the`, `Group`, `this`, `and`, `has`, `not`, `02375162`, `above`,
`process`, `update`, `When`, `can`, `are`, `your`, `their`, `under`, `all`, `then`

## Expected Improvement

New ingestion will reject entities that match:
- Stopwords (the, this, and, has, not, can, are, your, all, then, etc.)
- Numeric-only strings (02375162)
- Single characters (x)
- Temp file names (tmpabc123.txt)
- Sentence fragments (> 50 chars)
- Date/time expressions (3 days, 1 to 6)

Real entities will survive:
- G3, RMS, OHIP, Opera, SPM, ICS, SDOPS, ROA (whitelist)
- Salesforce, Datadog, SynXis (whitelist)
- All-caps acronyms (2-10 chars)
- Multi-word entities with capitalization
- Entities from multiple source documents

## Test Results

| Group | Result |
|-------|--------|
| Entity Quality Gate (36 tests) | **36/36 pass** |
| Graph Validation (24 tests) | **24/24 pass** |
| Fabric Wiring (8 tests) | **8/8 pass** |
| Sufficiency Gate (31 tests) | **31/31 pass** |
| LAN/UI/Explorer (39 tests) | **38 pass, 1 DuckDB lock** |
| **TOTAL verified** | **137 pass** |

## Files Changed

| File | Change |
|------|--------|
| `kurukshetra/graph/registry.py` | Added quality gate at ingestion: score → filter → persist |
| `kurukshetra/graph/repository.py` | Quality-aware upsert with GREATEST() for scores |
| `tests/test_entity_quality_gate.py` | **NEW** — 36 adversarial tests |
| `docs/MISSION_3_56C_INGESTION_QUALITY_GATE.md` | **NEW** |

## Not Committed

Awaiting approval.
