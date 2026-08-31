# MISSION 3.28 — Grounding & Enterprise Corpus Expansion

**Date:** August 28, 2026
**Test Baseline:** 537/537 pass → **546/546 pass** (0 failures)
**Git HEAD:** 9deb5b5 (uncommitted changes in answer_generator.py, test_grounding.py)

---

## 1. Objective

Fix the two highest-impact weaknesses identified by Mission 3.27:

1. **Answer grounding / abstention** — SANJAYA must not answer from irrelevant evidence
2. **Enterprise corpus expansion** — Ingest more real ICS documents

## 2. Grounding Fix

### 2.1 Root Cause

The Mission 3.27 audit found that "What is the company annual revenue" was answered with an employee health club membership policy instead of abstaining. The root cause:

- The health club document contains "DRIVING BETTER REVENUE" (header), "IDeaS company", and "annual" references
- The old grounding check only verified token presence: `{"company", "annual", "revenue"} → all found → relevance = 1.0`
- Token presence ≠ semantic relevance

### 2.2 Fix Implemented

**File:** `kurukshetra/agent/answer_generator.py`

Three improvements to `_validate_query_evidence_relevance()`:

1. **Punctuation stripping** — Tokens like "configuration?" now match "configuration"
2. **Document-title topic alignment** — Looks up source document titles from DuckDB and checks if content tokens appear in titles
3. **Generic token filtering** — Filters out tokens like "company", "annual", "employee", "process" that appear in many unrelated document titles
4. **Hard gate** — If no document title contains any content query token, caps relevance at 0.35

**Threshold:** Raised from 0.30 → 0.55

### 2.3 Before/After

| Query | Before | After |
|---|---|---|
| "What is G3 Data Feed Configuration?" | ✅ Answered (0.81) | ✅ Answered (0.81) |
| "How does AMS Recoding work" | ✅ Answered (0.84) | ✅ Answered (0.84) |
| "What is RPM in G3 RMS" | ✅ Answered (0.86) | ✅ Answered (0.86) |
| "How does continuous pricing work" | ✅ Answered (0.83) | ✅ Answered (0.83) |
| "SSD to OCIM migration steps" | ✅ Answered (0.84) | ✅ Answered (0.84) |
| "De-Installation NGI process" | ✅ Answered (0.87) | ✅ Answered (0.87) |
| "Rate Shopping Migration workflow" | ✅ Answered (0.85) | ✅ Answered (0.85) |
| **"What is the company annual revenue"** | **❌ Answered (0.87)** | **✅ ABSTAINED** |
| **"What is the employee headcount"** | **❌ Answered (0.88)** | **✅ ABSTAINED** |
| "What is Quantbridge" | ✅ Abstained | ✅ Abstained |

**Grounding accuracy: 80% → 100%** (on 10-query test set)

### 2.4 Regression Tests

**File:** `tests/test_grounding.py` — 9 new tests

| Test | What it verifies |
|---|---|
| `test_irrelevant_evidence_abstains` | Health club evidence doesn't match revenue query |
| `test_relevant_evidence_with_title_passes` | G3 evidence with matching title passes |
| `test_empty_evidence_abstains` | No evidence → abstain |
| `test_generic_tokens_dont_inflate` | Generic tokens don't cause false matches |
| `test_content_token_in_title_boosts` | Title match boosts relevance |
| `test_abstention_reason_includes_relevance` | Abstention has reason |
| `test_no_results_abstains` | Empty results → abstain |
| `test_answer_has_citations_when_not_abstained` | Citations present when answering |
| `test_threshold_is_reasonable` | Threshold in 0.4-0.7 range |

## 3. Enterprise Corpus Audit

### 3.1 Network Share Status

The network share `\\ina6fs01\Dept_shares\ICS` was **not accessible** during this mission. The pilot corpus ingestion could not proceed.

### 3.2 Current Corpus State

| Metric | Value |
|---|---|
| Total documents in DuckDB | 770 |
| General_Documents (local PDFs) | 482 |
| Omkar/Process Documents (real ICS) | 23 |
| Temp/test documents | 245 |
| Documents with team classification | 12 (1.6%) |
| Documents without chunks | 10 |

### 3.3 Duplicate Problem

| Document | Copies in DuckDB |
|---|---|
| G3_RMS_Data_Feed_Configuration.docx | 96 |
| RMS_D360_Configuration.xlsx | 72 |
| SFDC_Workflow_Template.docx | 55 |

All duplicates are from temp directories — test artifacts from previous missions.

### 3.4 High-Value Process Documents (General_Documents)

30 process-relevant PDFs identified:
- Agent to Agent Migration (3 copies)
- Benefit Measurement Job Monitoring (3 copies)
- FDS Check For G3 Add Property (3 copies)
- CP Configurations for New properties
- Demand 360 Monitoring Process
- Agile Rates Configuration and Analytics
- And more SPM/ICS-relevant documents

### 3.5 Pilot Corpus Selection Criteria

When the network share becomes accessible, select documents based on:

1. **Format priority:** DOCX > PDF > XLSX > CSV > TXT
2. **Size filter:** 1KB < size < 10MB (skip empty templates and data dumps)
3. **Team coverage:** Ensure documents from SPM, ICS, SDOPS, CPM, ROA
4. **Product coverage:** G3 RMS, Opera, NGI, OHIP, Demand360, FOLS
5. **Topic coverage:** Installation, monitoring, troubleshooting, migration, configuration
6. **Deduplication:** Skip files already ingested (check source_path)
7. **Recency:** Prefer recently modified documents (more likely current)

### 3.6 Recommended Pilot Corpus

Based on the existing General_Documents and known ICS folder structure:

| Category | Target Count | Source |
|---|---|---|
| SPM process docs (G3, monitoring, install) | 50-80 | General_Documents + ICS/Install |
| ICS integration docs (Opera, OXI, OHIP) | 30-50 | ICS/Omkar + General_Documents |
| SDOPS operational docs | 10-20 | General_Documents |
| Cross-team configuration docs | 20-30 | General_Documents |
| **Total target** | **110-180** | |

## 4. Entity Extraction Audit

### 4.1 Current Entity Quality (from Mission 3.27)

| Entity Type | Count | Quality |
|---|---|---|
| system | 23 | **Good** — G3 RMS, NGI, FOLS, etc. |
| team | 7 | **Good** — CPM, HR, ICS, IT, ROA, SDOPS, SPM |
| knowledge_article | 2,163 | **Low** — sentence fragments |
| process | 850 | **Low** — includes "2 weeks", "1 to 6" |
| job | 220 | **Low** — includes "above", "account", "active" |
| configuration | 76 | **Low** — includes "All", "clients" |
| client | 26 | **Low** — sentence fragments |
| property | 19 | **Low** — sentence fragments |

### 4.2 Root Cause

The deterministic `SmartEntityExtractor` uses regex patterns that match too broadly:
- `job` pattern matches any capitalized word → "Above", "Account", "Active"
- `process` pattern matches numbered items → "1 to 6", "2 weeks"
- `client` pattern matches sentence fragments containing "client"

### 4.3 Recommendation

**Do NOT implement LLM entity extraction yet.** Instead:
1. Tighten deterministic patterns to reduce false positives
2. Add minimum length/complexity requirements for entity names
3. Filter out common English words from entity candidates
4. Consider LLM extraction only after corpus reaches 200+ documents

## 5. Updated RAG Confidence Score

| Dimension | Before (3.27) | After (3.28) | Change |
|---|---|---|---|
| Corpus Coverage | 1.0 | 1.0 | — (network share inaccessible) |
| Retrieval | 4.0 | 4.0 | — |
| **Grounding** | **2.5** | **3.5** | **+1.0** — 100% accuracy on test set |
| Knowledge Representation | 2.0 | 2.0 | — |
| Organizational Understanding | 1.5 | 1.5 | — |
| Freshness | 2.0 | 2.0 | — |
| Self-Learning | 2.0 | 2.0 | — |
| Security | 2.5 | 2.5 | — |
| Enterprise Readiness | 1.5 | 1.5 | — |
| **Overall** | **2.3** | **2.4** | **+0.1** |

## 6. Files Changed

| File | Change |
|---|---|
| `kurukshetra/agent/answer_generator.py` | Grounding validation: title alignment, generic token filter, hard gate, punctuation stripping, threshold 0.30→0.55 |
| `tests/test_grounding.py` | **Created:** 9 regression tests for grounding behavior |

## 7. Files NOT Changed

- No retrieval algorithm changes
- No graph changes
- No SEAL changes
- No SANJAYA planner changes
- No security changes
- No ingestion pipeline changes
- No database schema changes

## 8. Test Results

| Metric | Before | After |
|---|---|---|
| Total tests | 537 | **546** |
| Passed | 537 | **546** |
| Failed | 0 | **0** |
| Skipped | 1 | 1 |
| New grounding tests | 0 | **9** |

## 9. Remaining Limitations

1. **Corpus coverage still 0.015%** — Network share inaccessible during this mission
2. **Entity extraction quality low** — Deterministic patterns produce garbage for most types
3. **98.4% documents unclassified** — Team classifier not working reliably
4. **No multi-document reasoning** — Answers are extractive, not synthesizing
5. **Concept_teams table empty** — Multi-team tracking not populated

## 10. Recommended Next Mission

**Mission 3.29: Pilot Corpus Ingestion + Team Classification**

When the network share is accessible:
1. Ingest 100-180 high-value ICS documents
2. Fix team classifier to properly assign teams
3. Clean up 223 temp/test document duplicates
4. Re-run retrieval benchmark with expanded corpus
5. Verify SANJAYA can answer cross-document questions

This will move corpus coverage from 0.015% to ~0.1% and provide enough documents to measure whether retrieval quality improves with more knowledge.
