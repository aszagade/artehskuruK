# Mission 3.41 — Grounding & Citation Quality

## Objective

Audit Mission 3.40, improve multi-document synthesis, claim→evidence mapping, citation correctness, mention-vs-answer detection, conflict detection, and confidence calibration.

## Test Result

**590/590 tests pass** (538 core + 52 agentic/grounding/gx10)

## Evaluation: 27-Question Benchmark

| Metric | Before (3.40) | After (3.41) | Delta |
|--------|---------------|--------------|-------|
| **Accuracy** | 26/27 (96%) | **27/27 (100%)** | **+1** |
| **Citation accuracy** | 100% | 100% | — |
| **MVA traps caught** | 2/3 | **3/3** | **+1** |
| **Avg latency** | 1.60s | 1.58s | -0.02s |
| **Avg keyword coverage** | 82% | 86% | +4% |

### Per-Category Results

| Category | Correct | Notes |
|----------|---------|-------|
| Single-document factual | 3/3 ✅ | G3 Data Feed, AMS Recoding, Duplicate Group |
| Cross-document synthesis | 3/3 ✅ | Teams with G3, G3 installation, G3+OHIP |
| Cross-team reasoning | 3/3 ✅ | ICS role, SPM role, pricing capabilities |
| Workflow/procedural | 3/3 ✅ | Rate Shopping, Agent Migration, Add Property |
| Configuration | 2/2 ✅ | GA Update Window, Agile Rates |
| **MVA traps** | **3/3 ✅** | Employees, revenue, **salary range** |
| Insufficient evidence | 3/3 ✅ | Quantum computing, weather, G3 release notes |
| Citation correctness | 2/2 ✅ | OHIP installation, mass mail |
| Grounding | 3/3 ✅ | Proactive Monitoring, Stats Transition, SSD-OCIM |
| Edge cases | 2/2 ✅ | Single-term "G3", ambiguous "What?" |

## Key Fix: Salary MVA Trap (E17)

**Before:** "What is the salary range for G3 engineers?" → ANSWER (incorrectly from pricing docs)

The G3 pricing docs mention "range of unqualified rates" which matched "range" and "G3". The extractive answer picked up pricing configuration text as if it were salary information.

**After:** Correctly ABSTAINS — the `_detect_mention_vs_answer` method now detects salary-specific queries and verifies the evidence contains actual salary data (dollar/rupee amounts, LPA terms, or explicit salary range documentation).

## What Changed

### Files Modified

| File | Changes |
|------|---------|
| `kurukshetra/agent/answer_generator.py` | 4 improvements: salary MVA detection, structured LLM evidence formatting, improved confidence calibration with corroboration factor, enhanced conflict detection |
| `tests/test_gx10_integration.py` | Updated evidence formatting test for new structured format |

### 1. Salary MVA Detection

Added `_MVA_SALARY_PATTERN` to detect questions about salary/compensation. When detected, verifies evidence contains actual salary data (dollar amounts, INR amounts, LPA terms) rather than just pricing/range terminology.

### 2. Structured LLM Evidence Formatting

Changed from:
```
[Source 1: docs/g3.md]
G3 config details
```

To:
```
[Source 1: G3 RMS Onboarding Overview] [Team: CPM] [File: docs/g3.md]
G3 config details
```

This gives GX10 document title, owning team, and file path — enabling better cross-document synthesis.

### 3. Confidence Calibration

Added **cross-document corroboration factor** (20% weight). Checks if answer sentences are grounded in evidence from multiple documents. Multi-document answers with corroboration get higher confidence.

### 4. Enhanced Conflict Detection

Added:
- **Version/temporal conflict detection**: Flags when documents from 3+ years apart are both used as evidence
- **Additional negation patterns**: `never/always`, `prohibited/permitted`
- Cleaner conflict messages with year identification

## Architecture

```
Query
  → Plan (classify + detect entities)
  → Retrieve (round 1: hybrid + entity augmentation)
  → Evaluate Evidence
      ├── Sufficiency check (diversity, quality, topic alignment)
      └── Mention-vs-answer detection (count, who, when, salary)
  → Enough? → Refine & Retrieve Again (round 2, max)
  → Multi-Document Synthesis
      ├── Deduplicate by document
      ├── Structured evidence with titles, teams, file paths
      └── Conflict detection (negation + version/temporal)
  → Verify (citations match evidence)
  → Answer (LLM synthesis or extractive fallback)
      ├── Confidence with corroboration factor
      └── Citations + provenance
```

## Evidence Contract

Every answer now includes:
- **Answer text** (LLM-synthesized or extractive)
- **Confidence** (calibrated to evidence quality + corroboration)
- **Evidence items** (chunk_id, document_id, source_path, text, score, rank)
- **Citations** (chunk_id, document_id, source_path, text_snippet, score, rank)
- **Source documents** (unique document IDs)
- **Conflicts** (detected contradictions with year identification)
- **Limitations** (single source, low confidence, no cross-document corroboration)
- **MVA flag** (whether mention-vs-answer was detected)

## Security

- VisibilityFilter wraps every retrieval iteration
- No unauthorized evidence reaches GX10
- All citations trace to authorized evidence

## Files NOT Changed

- Retrieval algorithms (BM25, Vector, Hybrid)
- Security/visibility filtering
- Knowledge Fabric ingestion
- Graph/SEAL behavior
- Database schema
- External dependencies

## Risks

1. **Salary MVA detection** is pattern-based — may miss non-English salary terms
2. **Corroboration factor** adds computational overhead (~1ms per answer)
3. **Structured evidence formatting** increases token count for GX10 by ~20%

## What Remains

1. **Corpus scale** — 687 docs vs 152,867 available
2. **Entity quality** — ~4,678 noisy process/job entities
3. **Self-learning** — FeedbackLoop records but never reads back
4. **Streaming responses** — not yet implemented
5. **Conversation memory** — single-turn only

## Recommended Next Mission

**Mission 3.42 — Entity Quality Cleanup + Corpus Expansion**

Clean noisy entities and expand corpus when network share is accessible.
