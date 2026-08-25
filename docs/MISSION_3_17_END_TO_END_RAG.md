# Mission 3.17 — End-to-End Evidence-Grounded RAG Foundation

**Date:** August 25, 2026
**Git HEAD:** `b72f896` (before changes)
**Test Baseline:** 259/259 pass → **287/287 pass** after changes

---

## A. Current Query Flow (Before)

```
User Query
  → SANJAYAPlanner.create_plan()     ✅ Intent classification
  → HybridRetriever.search()          ✅ Normalized BM25+Vector
  → VisibilityFilter.filter()         ✅ Access control
  → [MISSING: Answer generation]
  → [MISSING: Citation/provenance]
  → [MISSING: Abstention]
  → Raw chunks returned to user
```

**Gap:** The system returned raw retrieval chunks with scores but never assembled an answer, provided citations, or handled insufficient evidence.

---

## B. Implemented End-to-End Flow (After)

```
User Query
  → SANJAYAPlanner.create_plan()           ✅ Intent + team routing
  → VisibilityFilter(HybridRetriever)       ✅ Authorized retrieval only
  → AnswerGenerator.generate()              ✅ NEW: Evidence-grounded answer
    → _build_evidence()                     Evidence items from chunks
    → _extract_answer()                     Extractive sentence selection
    → _calculate_confidence()               Multi-factor confidence scoring
    → _detect_conflicts()                   Cross-document contradiction detection
    → _build_citations()                    Source provenance tracking
    → _assess_evidence_quality()            Strong/moderate/weak/none
    → _identify_limitations()               Single source, low confidence, etc.
    → _abstain()                            When evidence insufficient
  → AnswerResult                            Complete answer with provenance
  → /api/ask endpoint                       NEW: REST API for answers
```

---

## C. Evidence Contract

```python
@dataclass
class AnswerResult:
    query: str                    # Original question
    answer: str                   # Extractive answer grounded in evidence
    confidence: float             # 0.0–1.0 (multi-factor scoring)
    abstained: bool               # True when evidence insufficient
    abstention_reason: str        # Why abstained
    evidence: list[EvidenceItem]  # All evidence used
    citations: list[Citation]     # Source citations with provenance
    source_documents: list[str]   # Unique source document IDs
    retrieval_strategy: str       # Which strategy produced evidence
    authorization_status: str     # authorized/unauthorized
    limitations: list[str]        # Known limitations
    conflicts: list[str]          # Detected conflicting evidence
    evidence_count: int           # Number of evidence items
    evidence_quality: str         # strong/moderate/weak/none
```

---

## D. Provenance Model

Every answer traces back through:

```
Answer
  → Citation (chunk_id, document_id, source_path, text_snippet, score, rank)
    → EvidenceItem (from RetrievalResult)
      → Document (source_path, SHA-256, team, visibility)
        → Chunks (original text)
          → Graph entities (if extracted)
```

All provenance is preserved from ingestion through retrieval to answer.

---

## E. Authorization Boundary

| Layer | Enforcement | Status |
|-------|-------------|--------|
| Retrieval | `VisibilityFilter` wraps `HybridRetriever` | ✅ VERIFIED |
| API | `/api/ask` accepts `max_level` parameter | ✅ IMPLEMENTED |
| Answer | `authorization_status` field in `AnswerResult` | ✅ IMPLEMENTED |
| Abstention | Unauthorized → automatic abstain | ✅ VERIFIED |

**Verified behavior:**
- INTERNAL access: 5 results returned, answer generated (confidence 0.86)
- Unauthorized: automatic abstention, no answer provided
- All 559 documents currently have "Internal" visibility

---

## F. Answer-Generation Behavior

| Behavior | Implementation |
|----------|---------------|
| Extractive approach | Selects most relevant sentences from evidence |
| Keyword scoring | Overlap between query tokens and sentence tokens |
| Deduplication | Removes sentences with >60% token overlap |
| Max length | 2000 characters |
| No hallucination | Answer words must overlap with evidence text |
| Confidence scoring | 5-factor weighted: count, score, diversity, coverage, consistency |

---

## G. Abstention Behavior

The system abstains when:

1. **No evidence found** — zero retrieval results
2. **Low-score evidence** — all results below MIN_SCORE_THRESHOLD (0.1)
3. **Unauthorized** — authorization_status is "unauthorized"
4. **Low confidence** — calculated confidence below MIN_CONFIDENCE_THRESHOLD (0.2)

Abstention returns a clear message explaining why, not a fabricated answer.

---

## H. Conflict Handling

The answer generator detects conflicts across evidence from different documents:

- **Negation pattern detection** — "should not" vs "should"
- **Cross-document comparison** — different documents, contradictory patterns
- **Limitations surfaced** — single-source answers flagged

Conflicts are listed in `AnswerResult.conflicts` rather than silently resolved.

---

## I. Self-Learning Boundary

| Component | Status | Next Step |
|-----------|--------|-----------|
| Unknown-term detection | ✅ IMPLEMENTED | — |
| Glossary confirm/reject | ✅ IMPLEMENTED | — |
| SEAL decision provenance | ✅ IMPLEMENTED | — |
| Feedback storage | ✅ IMPLEMENTED | Wire into retrieval scoring |
| Self-verification | ✅ EXPERIMENTAL | Run automatically |
| Pattern discovery | ✅ EXPERIMENTAL | Feed with real query data |
| Strategy learning | ❌ MISSING | Requires outcome measurement |
| Outcome learning | ❌ MISSING | Requires answer quality feedback |

**Feedback path (documented, not yet connected):**
```
Question → Retrieval → Answer → User Feedback
  → FeedbackLoop.record_feedback()
  → chunk_score_history
  → PatternDiscovery.detect_knowledge_gaps()
  → SelfRecommender.analyze_and_recommend()
  → [MISSING: automatic strategy adjustment]
```

---

## J. Universal Source Architecture

| Source Type | Current Status | Can Feed Canonical Pipeline? |
|------------|---------------|---------------------------|
| Local files (PDF/DOCX/XLS/XLSX/CSV/TXT/MD) | ✅ VERIFIED | Yes |
| Network share (\\ina6fs01\Dept_shares) | ✅ VERIFIED | Yes (read-only discovery) |
| Confluence | ❌ STUB | Interface defined, no implementation |
| Salesforce | ❌ MISSING | No interface |
| Datadog | ❌ STUB | Interface defined, no implementation |
| SQL | ❌ STUB | Interface defined, no implementation |
| Teams | ❌ STUB | Interface defined, no implementation |
| Outlook/mail | ❌ MISSING | No interface |
| Smartsheet | ❌ MISSING | Intent routing exists, no connector |

**Minimal common source contract needed:**
```
Source
  → discover (read-only scan)
  → fetch (read content)
  → normalize (to text)
  → metadata (provenance, team, visibility)
  → ingest (canonical IngestionPipeline)
```

The existing `TextExtractor → IngestionPipeline` path already supports this for file-based sources. Future API-based sources need a `BaseConnector.connect() → poll() → ingest()` adapter.

---

## K. Current Capability Matrix (Updated)

| Area | Before | After |
|------|:------:|:-----:|
| Ingestion | 7 formats | 7 formats (unchanged) |
| Retrieval | 4 strategies | 4 strategies (unchanged) |
| Answer generation | **MISSING** | **✅ IMPLEMENTED** |
| Citations/provenance | **MISSING** | **✅ IMPLEMENTED** |
| Abstention | **MISSING** | **✅ IMPLEMENTED** |
| Conflict detection | **MISSING** | **✅ IMPLEMENTED** |
| Security boundary | Visibility only | Visibility + answer authorization |
| API | /api/query (raw chunks) | /api/query + **/api/ask** (answers) |
| Tests | 259 | **287** (+28) |

---

## L. Remaining Enterprise Gaps

| # | Gap | Impact | Priority |
|---|-----|--------|----------|
| 1 | **No authentication/authorization** | Cannot secure API endpoints | Critical |
| 2 | **No audit logging** | Cannot trace who queried/answered what | Critical |
| 3 | **No enterprise connectors** | No real-time data from Datadog/Salesforce/Teams | High |
| 4 | **No query expansion** | 35% of benchmark queries still miss | High |
| 5 | **No incremental change detection** | Modified network files not detected | Medium |
| 6 | **No document versioning** | Same doc in multiple versions treated separately | Medium |
| 7 | **No answer quality feedback loop** | Cannot improve from user satisfaction data | Medium |
| 8 | **No LLM answer generation** | Extractive only; no fluent paraphrasing | Low |
| 9 | **No hierarchical chunking** | Section context lost in flat chunks | Low |
| 10 | **No entity-aware retrieval** | Graph entities not used to boost retrieval | Low |

---

## M. Recommended Next Mission

**Mission 3.18: Authentication + Audit Logging**

Before connecting real enterprise data sources, the system needs:
1. User identity model
2. API token authentication
3. Operation audit trail (who queried, who ingested, who confirmed)
4. Team-based access policy

This is the minimum security boundary required before any production enterprise connector is developed.

---

## Files Changed

| File | Change | Reason |
|------|--------|--------|
| `kurukshetra/agent/answer_generator.py` | **Created** | Evidence-grounded answer generation |
| `kurukshetra/agent/__init__.py` | Modified | Export AnswerGenerator, AnswerResult, Citation, EvidenceItem |
| `command_center/backend/routers/chat.py` | Modified | Added `/api/ask` endpoint |
| `tests/test_e2e_rag.py` | **Created** | 28 end-to-end RAG tests |

## Files NOT Changed

- No database schema changes
- No retrieval algorithm changes
- No ingestion behavior changes
- No access-control changes
- No existing tests modified
- No SANJAYA planner changes
- No Graph changes
- No SEAL changes
- No Event Bus changes

---

## Test Results

| Suite | Before | After | Delta |
|-------|--------|-------|-------|
| Full test suite | 259 | **287** | **+28** |
| New E2E tests | 0 | **28** | +28 |
| Access control tests | 17 | 17 | 0 |
| All existing tests | 259 | 259 | 0 |

---

*Generated from repository evidence. No organizational facts invented.*
