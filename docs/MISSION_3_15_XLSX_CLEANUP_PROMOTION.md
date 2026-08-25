# Mission 3.15 — XLSX Noise Cleanup Promotion

## 1. Objective

Promote Representation D (XLSX/XLS noise-only cleanup) to production, re-ingest the 23 ICS/Omkar documents, and verify no regressions.

## 2. Baseline

| Metric | Before |
|--------|-------:|
| Documents | 528 |
| Chunks | 3,434 |
| BM25 R@3 | 60% |
| BM25 R@5 | 65% |
| BM25 MRR | 0.610 |
| Hybrid R@3 | 70% |
| Hybrid R@5 | 75% |
| Hybrid MRR | 0.685 |
| Tests | 251/251 |

## 3. Exact Production Change

**File:** `kurukshetra/extractors/text_extractor.py`

**Changes:**
1. Added `import re` at module level
2. Added `_clean_excel_text()` static method: removes `Unnamed: \d+` and standalone `\bNaN\b` tokens
3. Modified `_extract_excel()`: drops all-NaN rows, applies `_clean_excel_text()`, skips empty sheets
4. Modified `_extract_xls()`: same changes as `_extract_excel()`

**No other files modified.**

## 4. Tests Added

**File:** `tests/test_xlsx_noise_cleanup.py` (8 tests)

| Test | Verifies |
|------|----------|
| `test_nan_removed_from_output` | NaN tokens removed from XLSX extraction |
| `test_unnamed_headers_removed` | Unnamed: N headers removed |
| `test_sheet_names_preserved` | Sheet names preserved in output |
| `test_meaningful_content_preserved` | Cell content preserved |
| `test_empty_sheet_handled_safely` | Empty sheets don't crash |
| `test_clean_spreadsheet_not_damaged` | Clean spreadsheets unaffected |
| `test_clean_excel_text_helper` | Regex cleanup logic correct |
| `test_xls_extraction_applies_same_cleanup` | XLS also cleaned |

## 5. Database Backup

- Backup: `kurukshetra_registry_pre_315_20260825_172531.duckdb`
- Size: 174,860 KB

## 6. Documents Re-ingested

23 ICS/Omkar Process Documents re-extracted and re-chunked with D extraction.

| Document | Chars Before | Chars After | Chunks Before | Chunks After |
|----------|-------------:|------------:|--------------:|-------------:|
| DOC-000485 | — | 13,831 | — | 17 |
| DOC-000486 | — | 19,444 | — | 23 |
| DOC-000487 | — | 3,106 | — | 4 |
| DOC-000488 | — | 13,609 | — | 16 |
| DOC-000489 | — | 63,927 | — | 76 |
| DOC-000490 | — | 36,616 | — | 43 |
| DOC-000491 | — | 8,923 | — | 11 |
| DOC-000492 | — | 12,119 | — | 15 |
| DOC-000493 | — | 47,615 | — | 56 |
| DOC-000494 | — | 25,112 | — | 30 |
| DOC-000495 | — | 6,554 | — | 8 |
| DOC-000496 | — | 5,227 | — | 6 |
| DOC-000497 | — | 2,272 | — | 3 |
| DOC-000498 | — | 4,998 | — | 6 |
| DOC-000499 | — | 3,921 | — | 5 |
| DOC-000500 | — | 3,263 | — | 4 |
| DOC-000501 | — | 4,303 | — | 5 |
| DOC-000502 | — | 2,571 | — | 3 |
| DOC-000503 | — | 1,358 | — | 2 |
| DOC-000504 | — | 4,890 | — | 6 |
| DOC-000505 | — | 3,226 | — | 4 |
| DOC-000506 | — | 4,877 | — | 6 |
| DOC-000507 | — | 8,635 | — | 10 |

## 7. Before/After Corpus Counts

| Metric | Before | After | Delta |
|--------|-------:|------:|------:|
| Documents | 528 | 528 | 0 |
| Chunks | 3,434 | 3,648 | +214 |

## 8. Retrieval Benchmark

| Strategy | R@3 Before | R@3 After | R@5 Before | R@5 After | MRR Before | MRR After |
|----------|----------:|---------:|----------:|---------:|----------:|---------:|
| BM25 | 60% | **80%** | 65% | **85%** | 0.610 | **0.693** |
| Vector | 65% | 65% | 70% | 70% | 0.627 | 0.627 |
| Hybrid | 70% | **80%** | 75% | **90%** | 0.685 | **0.687** |
| Graph-Aug | 65% | 65% | 65% | 65% | 0.583 | 0.583 |

## 9. Per-Query Results (Key Queries)

| Query | Before (BM25) | After (BM25) | Status |
|-------|---------------:|--------------:|--------|
| Q09 Property Merge-Split | r1 | **r1** | PRESERVED |
| Q12 SSD to OCIM | r1 | **r1** | PRESERVED |
| Q13 AMS Recoding | — | — | Unchanged |
| Q17 Proactive Monitoring | r8 | **r1** | **FIXED** |
| Q18 Stats to Inventory | — | **r1** | **FIXED** |
| Q10 Rate Shopping Migration | — | **r3** | **IMPROVED** |

## 10. Provenance Verification

All 23 ICS documents verified:
- `team_owner`: unchanged (UNKNOWN)
- `visibility`: unchanged (Internal)
- `sha256`: unchanged
- `source_path`: unchanged
- No duplicate documents created

## 11. Access-Control Verification

- VisibilityFilter tests: 17/17 pass
- No changes to access_control.py
- No changes to retrieval filtering behavior

## 12. Graph Integrity

- Graph entities: unchanged (re-ingestion only updates chunks, not graph)
- Graph relationships: unchanged
- Graph evidence: unchanged

## 13. Knowledge/SEAL Quality Impact

- No changes to SEAL behavior
- No changes to glossary
- Unknown terms may differ due to changed chunk content (noise removed)
- Graph extraction will produce different entities on next re-indexing (not done in this mission)

## 14. Risks

| Risk | Mitigation |
|------|-----------|
| Existing non-ICS chunks unchanged | Only ICS docs re-ingested |
| BM25 cache stale | Auto-refreshes on chunk count change |
| Vector embeddings outdated | Vectors not rebuilt (only chunks updated) |

## 15. Rollback Procedure

1. Restore from `kurukshetra_registry_pre_315_20260825_172531.duckdb`
2. Revert `text_extractor.py` to previous version
3. Re-run tests to confirm

## 16. Final Decision

**A. PROMOTED**

Evidence proves improvement without unacceptable regression:
- BM25 R@3: 60% → 80% (+20%)
- BM25 R@5: 65% → 85% (+20%)
- Hybrid R@3: 70% → 80% (+10%)
- Hybrid R@5: 75% → 90% (+15%)
- Q09 preserved
- Q12 preserved
- Q17 fixed
- Q18 fixed
- Q10 improved
- 259/259 tests pass
- Provenance intact
- Access control intact
