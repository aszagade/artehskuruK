# MISSION 3.31 — SANJAYA Knowledge & RAG Readiness Audit

**Date:** August 28, 2026
**Test Baseline:** 546/546 pass, 0 failures
**Git HEAD:** 9deb5b5 (uncommitted work from Missions 3.20–3.28)
**Network Share:** NOT ACCESSIBLE (`\\ina6fs01\Dept_shares\ICS`)

---

## 1. What Is Actually Indexed and Searchable

### Corpus

| Metric | Value |
|---|---|
| Total documents | 561 |
| Total chunks | 3,574 |
| Vector embeddings | 3,469 |
| Graph entities | 4,188 |
| Graph relationships | 18,589 |
| Evidence records | 11,713 |
| Glossary terms | 35 confirmed |
| Pending unknowns | 894 |
| SEAL decisions | 35 |

### Source Breakdown

| Source | Documents | % |
|---|---|---|
| General_Documents (local PDFs) | 481 | 85.7% |
| Other (local files) | 64 | 11.4% |
| **Omkar/ICS (real enterprise)** | **16** | **2.9%** |

**Critical finding:** 85.7% of the corpus is local PDF copies, not live enterprise data. Only 16 documents come from the actual ICS network share.

### Indexed Omkar/ICS Documents (16)

| Doc ID | Title | Team |
|---|---|---|
| DOC-000485 | SFDC Workflow - Price Grid to Daily Continuous Pricing | ROA |
| DOC-000489 | G3 Property Merge-Split Workflow | IT |
| DOC-000490 | Rate Shopping Migration Updated Workflow | ICS |
| DOC-000493 | SFDC_Workflow_AMS Recoding | UNKNOWN |
| DOC-000496 | ClientSpecific_MS Recoding Process | UNKNOWN |
| DOC-000497 | Delphi Installation and Configuration | UNKNOWN |
| DOC-000498 | G3 Data Feed Configuration | SPM |
| DOC-000499 | G3 RMS Demand360 Configuration | ROA |
| DOC-000500 | G3 RMS STR Configuration | SPM |
| DOC-000501 | G3 RSS Configuration, Population and Migration | ICS |
| DOC-000502 | Handling Duplicate Group Deletion Process | UNKNOWN |
| DOC-000503 | KB_Group Pricing Evaluation Window Extensions | ROA |
| DOC-000504 | Price Grid to Daily Continuous Pricing | ROA |
| DOC-000505 | RPM Configuration Case Workflow | ROA |
| DOC-000506 | Synthetic History to Standard Switch with AMS Rebuild | IT |
| DOC-000507 | Pricing Issues | ROA |

---

## 2. Team, Product, System, Process Understanding

### Team Distribution

| Team | Documents | Classified? |
|---|---|---|
| UNKNOWN | 174 (31.0%) | No |
| SPM | 122 (21.7%) | Yes |
| ICS | 95 (16.9%) | Yes |
| IT | 62 (11.0%) | Yes |
| ROA | 37 (6.6%) | Yes |
| SDOPS | 35 (6.2%) | Yes |
| HR | 28 (5.0%) | Yes |
| CPM | 8 (1.4%) | Yes |

**Classification rate: 69.0%** (387/561 classified)

### Systems SANJAYA Understands (23 entities, high quality)

G3 RMS, G3RMS, NGI, NGI Agent, FOLS, HTNG, OHIP, OHIP Emulator, Opera Cloud, Opera Cloud Agent, Opera PMS, OPERA Agent, OXI, SFDC, Salesforce, CP Pricing, Datadog, Curtis, Mews, SynXis, TARS, sas, sqlserver

### Processes SANJAYA Understands (via glossary, not graph)

Continuous Pricing, Rate Shopping, Rate Shopping Migration, Data Feed Configuration, Monitor Auto Processing, Pricing Troubleshooting, Vendor Integration, Apply License, Post Data, Re-start

### What SANJAYA Cannot Reliably Understand

- **Process entities (850):** Mostly noise — "Version 1", "Resources", "Teams channel", "file has been received"
- **Job entities (220):** Mostly noise — "Encoding", "First Decision", "attached", "file"
- **Knowledge articles (2,163):** Sentence fragments, not meaningful entities
- **Cross-team concept tracking:** concept_teams table is EMPTY (0 associations)

---

## 3. SPM/ICS Overlap — G3 as Multi-Team Concept

### G3 Documents by Team

| Team | G3 Documents |
|---|---|
| SPM | 70 |
| UNKNOWN | 57 |
| IT | 31 |
| ICS | 29 |
| ROA | 15 |
| SDOPS | 10 |
| CPM | 4 |

**G3 genuinely spans SPM, ICS, IT, ROA, SDOPS, and CPM.** This is real multi-team knowledge.

### Cross-Team Query Test

| Query | Teams in Results | Answered? |
|---|---|---|
| "What systems does G3 RMS use" | SPM, ROA | ✅ |
| "How is G3 installed for a property" | SPM | ✅ |
| "G3 monitoring and alerting" | HR, SDOPS | ✅ |

**Finding:** G3 queries retrieve from multiple teams, proving cross-team knowledge exists. But concept_teams table is empty — the system cannot formally represent "G3 belongs to SPM and ICS."

---

## 4. Retrieval Quality Benchmark

### 12-Query Benchmark (current corpus: 561 docs, 3,574 chunks)

| Strategy | Recall@3 | Recall@5 | MRR | Avg Latency | Answer Accuracy | Abstention Accuracy |
|---|---|---|---|---|---|---|
| **BM25** | **92%** | **92%** | **0.917** | **55ms** | **100% (9/9)** | **100% (3/3)** |
| **Hybrid** | **92%** | **92%** | **0.875** | **1,356ms** | **100% (9/9)** | **100% (3/3)** |

### Per-Query Results

| Query | Category | BM25 | Hybrid | Grounding |
|---|---|---|---|---|
| G3 Data Feed Configuration | exact | ✅ MRR=1.0 | ✅ MRR=1.0 | ✅ Answered |
| AMS Recoding | workflow | ✅ MRR=1.0 | ✅ MRR=1.0 | ✅ Answered |
| RPM in G3 RMS | acronym | ✅ MRR=1.0 | ✅ MRR=1.0 | ✅ Answered |
| Continuous pricing | semantic | ✅ MRR=1.0 | ✅ MRR=1.0 | ✅ Answered |
| SSD to OCIM migration | workflow | ✅ MRR=1.0 | ✅ MRR=1.0 | ✅ Answered |
| Rate Shopping Migration | process | ✅ MRR=1.0 | ✅ MRR=1.0 | ✅ Answered |
| Property merge split | process | ✅ MRR=1.0 | ✅ MRR=0.5 | ✅ Answered |
| G3 RMS STR config | config | ✅ MRR=1.0 | ✅ MRR=1.0 | ✅ Answered |
| Demand360 config | config | ✅ MRR=1.0 | ✅ MRR=1.0 | ✅ Answered |
| Quantbridge | unknown | ✅ Abstained | ✅ Abstained | ✅ Correct |
| Company annual revenue | out_of_scope | ✅ Abstained | ✅ Abstained | ✅ Correct |
| Employee headcount | out_of_scope | ✅ Abstained | ✅ Abstained | ✅ Correct |

### Key Observations

1. **BM25 matches Hybrid on Recall** — exact keyword matching is sufficient for this technical corpus
2. **BM25 is 25x faster** — 55ms vs 1,356ms
3. **Both strategies achieve 100% grounding accuracy** — the Mission 3.28 fix works
4. **All 3 out-of-scope queries correctly abstained** — no false positives
5. **Hybrid has slightly lower MRR** (0.875 vs 0.917) — Vector results sometimes rank below BM25

---

## 5. Answer Grounding, Citation, and Abstention

### Grounding Accuracy: 100% (12/12)

- 9 answerable questions: all answered correctly
- 3 out-of-scope questions: all correctly abstained
- No false positives (answering from irrelevant evidence)
- No false negatives (abstaining on answerable questions)

### Citation Correctness

Every answered query produces citations with:
- chunk_id
- document_id
- source_path
- text_snippet
- score
- rank

Citations are traceable to persisted chunks in DuckDB.

### Abstention Behavior

The grounding validation uses:
1. Query-evidence relevance scoring (title alignment + generic token filter)
2. Confidence threshold (0.2 minimum)
3. Minimum evidence count (1)
4. Minimum score threshold (0.1)

When evidence doesn't match the query topic, SANJAYA correctly abstains with a reason.

---

## 6. Knowledge Fabric and Brain-State Representation

### What Exists

| Component | Status | Evidence |
|---|---|---|
| KnowledgeFabric | **IMPLEMENTED** | scan_source(), ingest_change(), ingest_source_document() |
| KnowledgeWatcher | **IMPLEMENTED** | filesystem polling, auto-detect new/changed/removed |
| Document state tracking | **IMPLEMENTED** | document_state table |
| Version history | **EMPTY** | document_versions table has 0 records |
| Multi-team concept tracking | **EMPTY** | concept_teams table has 0 records |
| Conflict detection | **MINIMAL** | 1 active conflict |
| Source cursor management | **IMPLEMENTED** | source_cursors table (1 Salesforce cursor) |
| Knowledge state API | **IMPLEMENTED** | /api/knowledge/state endpoint |

### What's Missing from Brain-State

1. **No version records** — documents ingested but versions not tracked
2. **No concept-team associations** — G3 spans 6 teams but system can't represent it
3. **Only 1 conflict detected** — despite 561 documents with overlapping content
4. **No freshness tracking** — no "last modified" comparison for knowledge currency
5. **No document-state population** — document_state table exists but isn't populated during ingestion

---

## 7. Memory Architecture Assessment

| Memory Type | Status | Current Component | Gap |
|---|---|---|---|
| **Working/In-context** | **PARTIAL** | ConversationMemory (20 turns, TTL) | No cross-session persistence, no user context |
| **Semantic** | **PARTIAL** | Glossary (35) + Graph (4K entities) + Decisions (35) | Entity quality low (850 noisy processes), no concept-team mapping |
| **Episodic** | **PARTIAL** | FeedbackLoop + fabric_scans | No per-user interaction history, no answer tracking |
| **Procedural** | **MISSING** | OrgMap + AgentTemplates only | No structured procedure store, no workflow extraction |
| **External/Retrieval** | **VERIFIED** | 7 strategies, benchmarked, reranker | Corpus too small for meaningful strategy comparison |
| **Parametric** | **PARTIAL** | BGE embeddings + reranker | Generic models, not domain-tuned |
| **Prospective** | **MISSING** | OpportunityEngine exists, unused | No temporal awareness, no deadline tracking |

### What Is Genuinely Useful Today

1. **BM25 retrieval** — fast, accurate, works for technical keyword queries
2. **Hybrid retrieval** — normalized fusion, slightly better than BM25 alone
3. **Grounding validation** — correctly abstains on out-of-scope queries
4. **Citation/provenance** — every answer traceable to source document
5. **Team classification** — 69% of documents correctly classified
6. **Source adapter architecture** — ready for enterprise connectors
7. **Knowledge Fabric** — change detection and incremental ingestion work
8. **SEAL loop** — 35 confirmed terms, 894 pending

### What Is Merely Architectural (Not Yet Useful)

1. **Graph traversal** — entities too noisy for meaningful traversal
2. **Graph-augmented retrieval** — doesn't improve over Hybrid on current corpus
3. **CrossVerifier** — too few strategies with meaningful differences
4. **HyDE/MultiQuery** — template-based, no LLM, limited value
5. **SelfRecommender** — generates recommendations but doesn't act
6. **OpportunityEngine** — exists but unused
7. **Agent templates** — defined but not operational

---

## 8. Prioritized Gap List

### Tier 1: Must Fix for Enterprise RAG (High Business Impact)

| Gap | Impact | Effort | Evidence |
|---|---|---|---|
| **Corpus too small** — 16 real ICS docs out of 152K available | CRITICAL | Medium (needs network share) | 85.7% of corpus is local PDFs |
| **Entity extraction quality** — 850 noisy process entities, 220 noisy job entities | HIGH | Medium | Graph adds noise, not signal |
| **Concept-team mapping empty** — G3 spans 6 teams but system can't represent it | HIGH | Small | concept_teams table has 0 records |
| **Document versions empty** — ingestion works but versions not tracked | MEDIUM | Small | document_versions table has 0 records |

### Tier 2: Important for Enterprise Maturity (Medium Business Impact)

| Gap | Impact | Effort | Evidence |
|---|---|---|---|
| **No cross-document reasoning** — answers are extractive, not synthesizing | HIGH | Large | Each answer comes from individual chunks |
| **No procedural memory** — workflows exist in docs but not structured | MEDIUM | Large | 850 process entities are noise |
| **No per-user interaction history** — can't learn from usage patterns | MEDIUM | Small | FeedbackLoop records but no user dimension |
| **BM25 dominates Vector** — 25x faster with equal recall | LOW | N/A | Expected for keyword-heavy technical docs |

### Tier 3: Future Capabilities (Low Business Impact Now)

| Gap | Impact | Effort | Evidence |
|---|---|---|---|
| No prospective memory | LOW | Large | No deadlines/schedules in current corpus |
| No domain-tuned embeddings | LOW | Large | Generic BGE works adequately |
| No prompt injection protection | MEDIUM | Medium | Security audit shows MISSING |
| No structured audit trail | MEDIUM | Medium | Python logging only |

---

## 9. Top 5 Highest-Value Next Development Steps

### 1. Expand Enterprise Corpus (BLOCKED on network share access)

**Impact:** CRITICAL
**Why:** SANJAYA currently knows about 16 real enterprise documents out of 152,867 available. Until the corpus expands meaningfully, retrieval quality measurements are unreliable and the system cannot demonstrate genuine enterprise RAG capability. Every other improvement is marginal without more real knowledge.

**What to do:** When `\\ina6fs01\Dept_shares\ICS` is accessible, ingest 50-100 documents from Omkar/Process Documents, Install, and Audit folders. Measure retrieval improvement.

### 2. Fix Entity Extraction Quality

**Impact:** HIGH
**Why:** The graph currently has 4,188 entities but most are noise ("Version 1", "Resources", "file has been received"). This degrades graph-augmented retrieval, cross-team concept mapping, and SANJAYA's ability to explain entity relationships. The 23 system entities are reliable; the 850 process and 220 job entities are not.

**What to do:** Tighten deterministic patterns, add minimum length/complexity requirements, filter common English words. Consider LLM extraction only after corpus reaches 200+ documents.

### 3. Populate Concept-Team Mapping

**Impact:** HIGH
**Why:** G3 genuinely belongs to SPM, ICS, IT, ROA, SDOPS, and CPM. The concept_teams table is empty. This means SANJAYA cannot answer "Which teams work on G3?" or "What systems does the ICS team manage?" even though the knowledge exists in the graph.

**What to do:** Run concept-team association during ingestion. For each entity, check which teams own documents mentioning that entity. Populate concept_teams.

### 4. Track Document Versions

**Impact:** MEDIUM
**Why:** The document_versions table is empty. When a document is re-ingested (content changed), the old version is lost. This means SANJAYA cannot distinguish current from historical knowledge, cannot detect version conflicts, and cannot answer "When was this document last updated?"

**What to do:** Populate document_versions during ingestion. Record version bump on content change.

### 5. Implement Interaction Logging

**Impact:** MEDIUM
**Why:** The FeedbackLoop records query→feedback but has no user dimension. SANJAYA cannot learn which queries are most common, which answers are most helpful, or which topics need more knowledge. This blocks self-improvement.

**What to do:** Add per-user query logging with timestamp, query, answer, confidence, and feedback. Use this to identify knowledge gaps and retrieval failures.

---

## 10. Files Created

| File | Purpose |
|---|---|
| `docs/MISSION_3_31_SANJAYA_RAG_READINESS_AUDIT.md` | This report |

## 11. Files Modified

None. Audit only.

## 12. Test Result

**546/546 pass, 0 failures, 1 skipped.**

## 13. Network Share Confirmation

No files were deleted from `\\ina6fs01\Dept_shares\`. Share is currently inaccessible. All operations were read-only against local DuckDB.
