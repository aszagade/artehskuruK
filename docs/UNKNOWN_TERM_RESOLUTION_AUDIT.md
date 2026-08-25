# Unknown Term Detection & Resolution Audit

## Current Architecture (as of Mission 3.8B)

### Detection Flow

```
Document Ingestion
  -> TextExtractor (PDF/TXT/MD/DOCX/XLSX/XLS/CSV)
  -> GlossaryManager.detect_unknown_terms(text, doc_id)
     -> Pattern 1: ALL CAPS acronyms (3+ chars)
     -> Pattern 2: Capitalized multi-word terms
     -> Pattern 3: Terms with underscores/hyphens
  -> _is_noise_term() filter
  -> KNOWN_TERMS filter
  -> unknown_terms table (INSERT OR IGNORE)
  -> 0 if term already exists
```

### Resolution Flow (SEAL)

```
UnknownLoader.load_pending()
  -> Enriches each term with:
     -> Document references (chunk LIKE search)
     -> Graph entity matches
     -> Glossary similar terms
  -> Returns UnknownTermWithEvidence list

InterviewSession.run()
  -> Shows one term at a time with evidence
  -> User actions:
     -> [enter definition] = confirm
     -> [s] = skip (rejects, appears next time)
     -> [a] = ambiguous (kept as pending)
     -> [q] = quit
  -> On confirm:
     -> GlossaryManager.confirm_term() -> glossary table
     -> DecisionStore.record() -> seal_decisions table
```

### What Already Exists

| Capability | Status | Location |
|-----------|--------|----------|
| Unknown term detection | **Working** | `glossary.py` |
| Noise filtering | **Working** (new) | `glossary.py:_is_noise_term()` |
| Known term filtering | **Working** (new) | `glossary.py:KNOWN_TERMS` |
| Document evidence enrichment | **Working** | `seal/unknowns.py` |
| Graph entity evidence | **Working** | `seal/unknowns.py` |
| Glossary similar terms | **Working** | `seal/unknowns.py` |
| Interactive interview | **Working** | `seal/interview.py` |
| Decision persistence | **Working** | `seal/decisions.py` |
| Glossary persistence | **Working** | `glossary.py` |
| Skip/reject | **Working** | `glossary.py:reject_term()` |
| Status tracking | **Partial** | `pending/confirmed/rejected` only |

### What Is Missing

| Gap | Impact | Recommended |
|-----|--------|-------------|
| No `superseded` status | Cannot track historical corrections | Add to seal_decisions |
| No alias support | Same term with different names not linked | Future mission |
| No multi-meaning support | "RMS" could mean different things in different contexts | Future mission |
| Resolution doesn't update graph entities | Confirmed term stays in glossary only | Future mission |
| No cross-document frequency for resolution | Can't see how many docs mention a term | Already tracked in occurrence_count |
| No confidence scoring for candidates | All terms treated equally | Future mission |

### Evidence from Real ICS Corpus

909 unknown terms were detected from 23 ICS documents:

| Category | Count | Status |
|----------|-------|--------|
| Known acronym leaked | 13 | **Fixed** — added to KNOWN_TERMS |
| Field names (XLSX headers) | 33 | **Fixed** — added to KNOWN_TERMS |
| Common English words | 5 | **Fixed** — added to KNOWN_TERMS |
| Multi-line garbage | 208 | **Fixed** — _is_noise_term() filter |
| Date patterns | ~20 | **Fixed** — _is_noise_term() filter |
| Real unknown terms | ~630 | Correct — these are genuine unknowns |

### Decision: UNKNOWN TERM RESOLUTION

**Status: Small improvement justified (DONE)**

The existing SEAL resolution pipeline is architecturally complete for its current scope:
- Detection works
- Evidence enrichment works
- Interactive interview works
- Decision persistence works
- Glossary updates work

The small improvements implemented:
1. Added 40+ known IDeaS terms to KNOWN_TERMS (prevents false unknowns)
2. Added noise filtering for spreadsheet artifacts, date patterns, multi-line garbage
3. Added 8 deterministic regression tests

The remaining gaps (aliases, multi-meaning, superseded status, graph updates) require the future Adaptive Entity Discovery system and should NOT be implemented now.

---

## Hierarchical Chunking Audit

### Current State

| Component | Status |
|-----------|--------|
| `DeterministicSplitter` | **Used** — flat 1000-char chunks with 150 overlap |
| `SemanticSplitter` | **Exists but unused** — section-aware chunking |
| `SemanticChunk` model | **Exists** — has heading, parent_heading, chunk_type, confidence |
| Chunks DB schema | **Flat only** — no section metadata columns |

### SemanticSplitter vs DeterministicSplitter Comparison

Tested on real ICS DOCX documents:

**G3 Data Feed Configuration.docx (4,998 chars):**
| Metric | Flat | Semantic |
|--------|------|----------|
| Chunk count | 6 | 11 |
| Section context | None | "Once IP whitelisting is confirmed", "After the client is added on EDF" |
| Chunk quality | Random text at 1000-char boundary | Self-contained sections |

**G3 RMS Demand360 Configuration.docx (3,921 chars):**
| Metric | Flat | Semantic |
|--------|------|----------|
| Chunk count | 5 | 6 |
| Section context | None | "This process applies when:", "Update the case with:", "Navigate to:" |
| Chunk quality | Random text at 1000-char boundary | Self-contained procedures |

### Key Finding

SemanticSplitter produces meaningfully better chunks for DOCX documents. However:

1. The semantic metadata (heading, type, parent) is **NOT persisted** in the DuckDB chunks table
2. The chunks table schema is flat: `chunk_id, document_id, chunk_index, text, start_offset, end_offset`
3. Even if SemanticSplitter were enabled, the heading context would be lost

### Decision: HIERARCHICAL CHUNKING

**Status: Prototype only — not justified for production yet**

Evidence-based reasoning:

1. **DOCX documents** would benefit from semantic chunking (section headings improve retrieval context)
2. **XLSX documents** (which are 40% of the ICS corpus) produce spreadsheet text that doesn't have clean sections — semantic chunking doesn't help
3. **The chunks table schema doesn't support section metadata** — adding columns would require a migration
4. **The current BM25 retrieval works** at 20-200ms with 60% recall on the real corpus
5. **The highest-impact next step** is hybrid retrieval (BM25 + Vector), not chunking changes

### What Would Be Needed for Production Semantic Chunking

1. Add `section_heading`, `parent_heading`, `chunk_type` columns to chunks table
2. Modify `ChunkRepository.insert()` to persist semantic metadata
3. Modify `DeterministicSplitter` fallback to produce compatible chunks
4. Update BM25 retriever to include heading context in search
5. Migration script for existing chunks

This is a **future mission** (3.9+), not part of 3.8B.
