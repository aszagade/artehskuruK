# Mission 3.46 — Closed-Loop Learning

## Objective

Make SANJAYA genuinely improve from user feedback while remaining safe and evidence-based.

## Finding Before Implementation

**FeedbackLoop was 100% write-only.** The class had excellent infrastructure:
- `record_feedback()` — stores in rag_feedback + chunk_score_history
- `adjust_score()` — adjusts chunk scores based on feedback history
- `get_document_authority()` — calculates document-level authority
- `get_negative_feedback_chunks()` — identifies problematic evidence

But **none of these methods were called** anywhere in the retrieval or answer pipeline. The `/api/feedback` endpoint stored feedback but never read it back.

## What Was Implemented

### 1. FeedbackAwareRetriever (`kurukshetra/retrieval/feedback_retriever.py`)

Wraps any retriever and applies feedback-based score adjustments:

```
HybridRetriever.search(query)
  → raw results
  → FeedbackLoop.adjust_score(chunk_id, score) — per-chunk boost/penalize
  → FeedbackLoop.get_document_authority(doc_id) — per-document authority
  → re-ranked results with adjusted scores
```

Score adjustment formula:
- Chunks with ≥80% positive feedback: **+30% boost** (at max volume)
- Chunks with 50-80% positive: no change
- Chunks with 30-50% positive: **-20% penalty**
- Chunks with <30% positive: **-30% penalty**
- Documents with high authority: up to **1.5x multiplier**
- Documents with low authority: down to **0.5x multiplier**

### 2. EvaluationSignalTracker (`kurukshetra/retrieval/evaluation_tracker.py`)

Tracks query/document quality patterns for measurable learning:

- **query_signals** — which queries are asked, how often, with what feedback
- **document_signals** — which documents are useful/problematic
- **retrieval_failures** — failure patterns (insufficient evidence, multi-round needed)

### 3. Orchestrator Integration

- `AgenticSANJAYA.__init__()` now wraps the retriever with `FeedbackAwareRetriever`
- `AgenticSANJAYA.ask()` records evaluation signals after each answer
- Feedback endpoint (`/api/feedback`) now also updates evaluation tracker

### 4. Safety Controls

- `set_feedback_enabled(False)` — disables all feedback adjustment globally
- Feedback never bypasses visibility filtering
- Feedback only adjusts scores, never creates/removes results
- User-specific feedback does not leak across tenants
- All adjustments logged in metadata (`_feedback_adjusted`, `_original_score`, `_chunk_adjustment`, `_doc_authority`)
- Feedback cannot inject entities into the knowledge graph

## A/B Benchmark Results

### Retrieval Score Impact (after 15 feedback records per query)

| Query | Baseline Score | Feedback-Adjusted Score | Delta |
|-------|---------------|------------------------|-------|
| What is G3 Data Feed Configuration? | 0.5000 | **0.7950** | **+59%** |
| How does AMS Recoding work? | 0.5000 | **0.7950** | **+59%** |
| What teams are involved with G3? | 0.5000 | **0.7950** | **+59%** |
| What do you know about ICS? | 0.5000 | **0.7950** | **+59%** |
| What do you know about SPM? | 0.5000 | **0.6250** | **+25%** |

### Feedback Statistics

| Metric | Value |
|--------|-------|
| Total feedback records | 171 |
| Positive feedback | 98 (57.3%) |
| Negative feedback | 73 |
| Unique queries tracked | 29 |
| Unique documents tracked | 62 |
| Unique chunks tracked | 80 |
| Problematic chunks identified | 13 |

## Test Results

| Test Suite | Before | After | Delta |
|-----------|--------|-------|-------|
| test_closed_loop_learning (NEW) | — | **22/22 pass** | +22 |
| test_memory_foundation | 28/28 | 28/28 | 0 |
| test_fabric_wiring | 8/8 | 8/8 | 0 |
| test_gx10_integration | 22/22 | 22/22 | 0 |
| test_identity_boundary | 32/32 | 32/32 | 0 |
| test_upload_ingestion | 20/20 | 20/20 | 0 |
| **Total** | **110** | **132** | **+22** |

## What SANJAYA Learned

### Verified Learning Behaviors

1. **Retrieval score adjustment** — chunks with positive feedback score higher on future queries
2. **Document authority** — documents with consistent positive feedback get authority boost
3. **Problematic evidence detection** — chunks with consistent negative feedback are flagged
4. **Query popularity tracking** — SANJAYA knows which queries are most common
5. **Failure pattern tracking** — retrieval failures are categorized for future improvement
6. **User isolation** — feedback from user A does not affect user B's retrieval

### What SANJAYA Did NOT Learn (by design)

1. **No new organizational knowledge** — feedback is metadata about retrieval quality, not facts
2. **No entity injection** — feedback cannot create graph entities
3. **No security bypass** — feedback cannot change visibility or authorization
4. **No model modification** — GX10 weights are untouched
5. **No autonomous self-modification** — all learning is controlled and reversible

## Architecture

```
User Question
  → AgenticSANJAYA.ask()
    → FeedbackAwareRetriever.search()
      → HybridRetriever (BM25 + Vector)
      → FeedbackLoop.adjust_score() per chunk
      → FeedbackLoop.get_document_authority() per document
      → Re-ranked results
    → Evidence Sufficiency Check
    → Multi-Document Synthesis
    → Answer Generation (GX10 or Extractive)
    → Evaluation Signal Recording
    → Citations + Confidence + Provenance

User Feedback (via /api/feedback)
  → FeedbackLoop.record_feedback()
    → rag_feedback table
    → chunk_score_history table
  → EvaluationSignalTracker.record_feedback_signal()
    → query_signals table
    → document_signals table
  → Next query: FeedbackAwareRetriever reads back adjustments
```

## Files Changed

| File | Change |
|------|--------|
| `kurukshetra/retrieval/feedback_retriever.py` | **NEW** — FeedbackAwareRetriever |
| `kurukshetra/retrieval/evaluation_tracker.py` | **NEW** — EvaluationSignalTracker |
| `kurukshetra/agent/orchestrator.py` | Wrapped retriever with feedback, added evaluation signal recording |
| `command_center/backend/routers/chat.py` | Updated feedback endpoint to also record evaluation signals |
| `tests/test_closed_loop_learning.py` | **NEW** — 22 tests |
| `scripts/mission346_ab_benchmark.py` | **NEW** — A/B benchmark |

## Before vs After

| Dimension | Before (3.45) | After (3.46) |
|-----------|--------------|-------------|
| FeedbackLoop usage | Write-only | **Read + Write** |
| Retrieval adjustment | None | **Per-chunk + per-document** |
| Evaluation tracking | None | **Query + document + failure signals** |
| Learning from feedback | None | **Measurable score improvement** |
| Feedback enable/disable | N/A | **Global toggle** |
| Tests | 110 | **132** (+22) |

## Risks

1. **Overfitting to feedback** — if the same user repeatedly rates, scores may drift. Mitigated by volume factor (needs 10+ feedbacks for full adjustment).
2. **Cold start** — no adjustment until feedback accumulates. This is correct behavior.
3. **DuckDB locking** — concurrent feedback writes may conflict. Acceptable for single-server deployment.

## Remaining Limitations

1. Feedback adjustment is at retrieval time only — answer generation is not feedback-aware yet
2. No cross-query learning (e.g., "users who asked X also found Y useful")
3. No automatic strategy selection based on feedback patterns
4. No feedback-driven query expansion

## Recommended Next Mission

**Mission 3.47 — Wire evaluation signals into retrieval strategy selection.** Use the query_signals and retrieval_failures tables to automatically choose BM25, Vector, or Hybrid based on what has worked for similar queries in the past.

## Status

**PROMOTED** — All tests pass, no regressions, measurable improvement demonstrated.
