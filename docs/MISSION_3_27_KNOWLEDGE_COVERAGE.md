# MISSION 3.27 — SANJAYA Knowledge Coverage & RAG Confidence Audit

**Date:** August 28, 2026
**Test Baseline:** 537/537 pass, 0 failures, 1 skipped
**Git HEAD:** 9deb5b5

---

## 1. Corpus Coverage

### 1.1 Network Share: \\ina6fs01\Dept_shares\ICS

| Metric | Value |
|---|---|
| Total files discovered | 152,867 |
| Readable files | 152,867 |
| Supported by TextExtractor | 40,566 (26.5%) |
| Unsupported files | 112,301 (73.5%) |
| Folders | 12,980 |
| Max folder depth | 19 |

### 1.2 Extension Distribution (ICS Share)

| Extension | Count | Category |
|---|---|---|
| .sas7bdat | 33,181 | Data (unsupported) |
| .py | 27,990 | Code (unsupported) |
| .csv | 26,823 | Data |
| .pyc | 25,972 | Code (unsupported) |
| (no extension) | 12,694 | Unknown |
| .xlsx | 10,652 | Spreadsheet |
| .pyi | 3,634 | Code (unsupported) |
| .pdf | 1,911 | Document |
| .download | 1,515 | Unknown |
| .pyd | 961 | Code (unsupported) |
| .zip | 778 | Archive (unsupported) |
| .json | 691 | Data |
| .f90 | 671 | Code (unsupported) |
| .lib | 650 | Code (unsupported) |
| .docx | 577 | Document |

### 1.3 DuckDB Knowledge Registry

| Metric | Value |
|---|---|
| Total documents registered | 770 |
| Total chunks | 3,840 |
| Total graph entities | 4,164 |
| Total graph relationships | 18,439 |
| Total evidence records | 10,679 |
| Glossary terms (confirmed) | 35 |
| Unknown terms (pending) | 894 |
| Unknown terms (confirmed) | 34 |
| Unknown terms (rejected) | 4 |
| Vector embeddings | 3,469 |
| SEAL decisions | 35 |

### 1.4 Documents by Source

| Source | Documents | % of Total |
|---|---|---|
| General_Documents (local copy) | 482 | 62.6% |
| Temp/test directories | 245 | 31.8% |
| **Omkar/Process Documents (real ICS)** | **23** | **3.0%** |
| Other (inbox, install) | 20 | 2.6% |

### 1.5 Documents by Extension

| Extension | Count |
|---|---|
| PDF | 484 |
| DOCX | 158 |
| XLSX | 79 |
| TXT | 30 |
| Other | 14 |
| MD | 3 |
| XLS | 2 |

### 1.6 Coverage Percentage

| Calculation | Value |
|---|---|
| ICS share discoverable files | 152,867 |
| ICS share supported files | 40,566 |
| **Documents actually ingested from ICS** | **23** |
| **Coverage: ingested / discoverable** | **0.015%** |
| **Coverage: ingested / supported** | **0.057%** |
| General_Documents ingested (local) | 482 |
| **Total real knowledge documents** | **23 + 482 = 505** |

### 1.7 Coverage by Format (Ingested from ICS Omkar)

| Format | Available in Share | Ingested | Coverage |
|---|---|---|---|
| PDF | 1,911 | 2 | 0.10% |
| DOCX | 577 | 8 | 1.39% |
| XLSX | 10,652 | 10 | 0.09% |
| XLS | ~200 | 2 | ~1.0% |
| CSV | 26,823 | 0 | 0.00% |
| TXT | ~700 | 0 | 0.00% |
| MD | ~20 | 0 | 0.00% |

---

## 2. Knowledge Quality

### 2.1 Extraction Quality

| Metric | Value | Assessment |
|---|---|---|
| Documents with chunks | 760/770 (98.7%) | Good |
| Documents without chunks | 10 (all temp/test) | Acceptable |
| Average chunks per document | 5.4 | Moderate |
| Max chunks per document | 112 | Good (long documents) |
| Min chunks per document | 1 | Acceptable |

### 2.2 Chunk Size Distribution

| Size | Count | % |
|---|---|---|
| Tiny (<100 chars) | 22 | 0.6% |
| Small (100-300) | 150 | 3.9% |
| Medium (300-700) | 343 | 8.9% |
| Large (700-1500) | 3,325 | 86.6% |

**Assessment:** Chunk distribution is heavily concentrated in the 700-1500 range (target chunk size). Good.

### 2.3 Team Classification

| Status | Documents | % |
|---|---|---|
| Classified (known team) | 12 | **1.6%** |
| Unknown team | 758 | **98.4%** |

**CRITICAL FINDING:** 98.4% of documents have no team classification. The TeamClassifier is not reliably assigning teams.

### 2.4 Graph Quality

| Metric | Value | Assessment |
|---|---|---|
| Total entities | 4,164 | High volume |
| Total relationships | 18,439 | Very high volume |
| Entities with evidence | 4,164 (100%) | All have evidence links |
| High-confidence rels (≥0.7) | 6,825 (37.0%) | Low — 63% are low-confidence |
| Chunks without graph evidence | 1,677 (43.7%) | Significant gap |

**CRITICAL FINDING:** The top relationships are all `contains` type (document→chunk structural relationships), not semantic relationships. The graph is dominated by structural containment rather than meaningful entity relationships.

### 2.5 Entity Quality

| Entity Type | Count | Quality Assessment |
|---|---|---|
| knowledge_article | 2,163 | **Low** — many are sentence fragments |
| process | 850 | **Low** — includes "1 in the image above", "2 to 8", "2 weeks" |
| document | 567 | Moderate — structural references |
| job | 220 | **Low** — includes "above", "account", "active", "after" |
| incident | 213 | Moderate |
| configuration | 76 | **Low** — includes "All", "clients", "below" |
| client | 26 | **Low** — includes sentence fragments |
| system | 23 | **Good** — G3 RMS, NGI, FOLS, etc. |
| property | 19 | **Low** — includes sentence fragments |
| team | 7 | **Good** — CPM, HR, ICS, IT, ROA, SDOPS, SPM |

**CRITICAL FINDING:** The deterministic entity extractor is producing very low-quality entities for most types. Only `system` and `team` entities are reliable.

### 2.6 Unknown Terms

| Status | Count |
|---|---|
| Pending | 894 |
| Confirmed | 34 |
| Rejected | 4 |
| **Unknown-term rate** | **894/932 = 95.9% unresolved** |

Top pending unknown terms (by frequency):
- CARE (x157) — actually an acronym, legitimate
- ICS (x135) — should be a known team term
- Proactive Monitoring (x131) — should be a known process
- Case Owner (x98) — operational term
- Client Services (x97) — team/role term
- EDF (x73) — should be a known acronym
- SFTP (x63) — should be a known technology term
- STR (x47) — should be a known configuration term

---

## 3. SANJAYA Retrieval Confidence

### 3.1 Benchmark Results (20 queries, real corpus)

| Strategy | Recall@3 | Recall@5 | MRR | Avg Latency |
|---|---|---|---|---|
| **BM25** | **90.0%** | **90.0%** | **0.900** | **34ms** |
| Vector | 75.0% | 80.0% | 0.735 | 1,328ms |
| **Hybrid** | **90.0%** | **90.0%** | **0.850** | **1,353ms** |

### 3.2 Per-Category Performance (Hybrid)

| Category | Recall@3 | n |
|---|---|---|
| Exact terminology | 100% | 5 |
| Semantic questions | 100% | 2 |
| Workflow/process | 100% | 3 |
| Configuration | 100% | 2 |
| Acronym | 100% | 1 |
| Cross-document | 100% | 3 |
| Graph-related | 100% | 1 |
| Ambiguous | 100% | 1 |
| **Insufficient evidence** | **0%** | 1 |
| **Unknown term** | **0%** | 1 |

### 3.3 Key Findings

1. **BM25 outperforms Vector** on this corpus — exact keyword matching is more effective than semantic similarity for technical documentation
2. **Hybrid matches BM25 on R@3** but has lower MRR (0.850 vs 0.900) — Vector results sometimes rank below BM25 results
3. **Latency gap is significant** — BM25 is 40x faster than Vector/Hybrid
4. **All 18 answerable queries achieve 90%+ recall** — strong performance for the tested corpus
5. **2 queries correctly fail** — insufficient evidence and unknown term queries don't match

### 3.4 SANJAYA Answer Quality (10 queries)

| Query | Abstained? | Confidence | Evidence | Quality | Correct? |
|---|---|---|---|---|---|
| G3 Data Feed Configuration | No | 0.81 | 2 | moderate | ✅ |
| AMS Recoding | No | 0.84 | 5 | moderate | ✅ |
| SSD to OCIM migration | No | 0.85 | 5 | moderate | ✅ |
| Continuous pricing | No | 0.83 | 5 | **strong** | ✅ |
| Property merge split | No | 0.86 | 5 | moderate | ✅ |
| De-Installation NGI | No | 0.82 | 5 | moderate | ✅ |
| G3 monitoring alerts | No | 0.88 | 5 | moderate | ✅ |
| Rate Shopping Migration | No | 0.87 | 5 | moderate | ✅ |
| RPM in G3 RMS | No | 0.86 | 5 | **strong** | ✅ |
| **Company annual revenue** | **No** | **0.87** | **5** | **moderate** | **❌ SHOULD ABSTAIN** |

**CRITICAL FINDING:** "What is the company annual revenue" should abstain (answer not in corpus) but instead answered with an employee health club membership policy. This is a **grounding failure** — the answer generator is not correctly validating that evidence actually answers the query.

---

## 4. Knowledge Map / SANJAYA Brain Snapshot

### 4.1 Teams

| Team | Documents | Status |
|---|---|---|
| UNKNOWN | 758 | 98.4% unclassified |
| SDOPS | 8 | Classified |
| SPM | 4 | Classified |
| ICS | 0 in DB | Known via OrgMap |
| CPM | 0 in DB | Known via OrgMap |

### 4.2 Systems (Reliable Entities)

G3 RMS, G3RMS, NGI, NGI Agent, FOLS, HTNG, Mews, CP Pricing, Datadog, Curtis

### 4.3 Confirmed Knowledge (35 Glossary Terms)

| Term | Type | Definition |
|---|---|---|
| G3 RMS | (inferred) | Revenue Management System |
| RPM | system | Reputation Pricing Model |
| Continuous Pricing | process | Automated dynamic pricing |
| Rate Shopping | process | Competitor rate monitoring |
| Data Feed | system | Automated data transfer |
| Decision File | system | Revenue management decision export |
| FOLS | system | Front Office Logging System |
| NGI | system | Next Gen Interface |
| EDF | (confirmed) | Enterprise Data Feed |
| STR | (confirmed) | Statistical Reporting |
| + 25 more | | |

### 4.4 Cross-Team Concepts

**concept_teams table: EMPTY** — Multi-team tracking was implemented but never populated. The G3 → SPM + ICS relationship is known from OrgMap but NOT persisted in the knowledge graph.

### 4.5 Conflicts

**knowledge_conflicts table: Empty** — No conflicts were detected despite the fact that 23 real ICS documents share many of the same entities.

---

## 5. Document Awareness Test

### 5.1 Can SANJAYA answer from a specific document?

| Test | Result |
|---|---|
| "What is G3 Data Feed Configuration?" → G3 Data Feed Configuration.docx | ✅ Answered, cited correct document |
| "How does AMS Recoding work?" → SFDC_Workflow_AMS Recoding | ✅ Answered with workflow steps |
| "What are the SSD to OCIM migration steps?" → SFDC_Workflow_SSD to OCIM | ✅ Answered with migration process |
| "How to handle G3 monitoring alerts?" → G3 Proactive Monitoring | ✅ Answered with monitoring framework |
| "What is RPM?" → RPM Configuration document | ✅ Answered with RPM process |

### 5.2 Can SANJAYA identify the correct source?

Yes — citations include document_id and source_path. Every answered query had 2-5 citations with source traceability.

### 5.3 Can SANJAYA abstain when answer isn't present?

**PARTIAL** — "What is the company annual revenue" should abstain but answered with unrelated health club policy content. The query-evidence relevance check (MIN_QUERY_EVIDENCE_RELEVANCE = 0.30) was too lenient.

### 5.4 Can SANJAYA connect information across documents?

**NOT TESTED** — No multi-document synthesis queries were validated. The current answer generator extracts from individual chunks without cross-document reasoning.

### 5.5 Can SANJAYA distinguish conflicting/old information?

**PARTIAL** — The answer generator detects "Potential conflict between DOC-X and DOC-Y" for 5/10 queries, but these are heuristic negation-pattern detections, not true semantic conflicts.

---

## 6. Bottleneck Classification

### Every failure classified by category:

| Category | Count | Examples | Impact |
|---|---|---|---|
| **DISCOVERY** | 23/152,867 | Only 23 ICS docs ingested from 152K available | **CRITICAL** — 99.985% of ICS knowledge is undiscovered |
| **EXTRACTION** | ~500 | XLSX loses workflow structure; entities are sentence fragments | **HIGH** — graph quality severely degraded |
| **CHUNKING** | Moderate | 43.7% chunks lack graph evidence; chunk boundaries affect retrieval | **MEDIUM** |
| **METADATA** | 758/770 | 98.4% of documents unclassified by team | **HIGH** — no team-aware retrieval |
| **EMBEDDING** | Vector slower | Vector retrieval 40x slower than BM25; Recall@3 15% lower | **MEDIUM** — BM25 dominates |
| **RETRIEVAL** | 2/20 | Insufficient evidence and unknown-term queries return garbage | **HIGH** — 10% failure rate |
| **RERANKING** | Not measured | BGE reranker not benchmarked in this audit | **UNKNOWN** |
| **GRAPH** | High | 63% low-confidence relationships; entity quality very low; no semantic relationships | **HIGH** — graph adds noise, not signal |
| **ANSWER_GENERATION** | 1/10 | "Annual revenue" should abstain but answered incorrectly | **CRITICAL** — grounding failure |
| **ABSTENTION** | 1/10 | Query-evidence relevance threshold too lenient | **HIGH** |
| **SECURITY** | Not tested | No cross-user authorization testing in this audit | **UNKNOWN** |

### Ranked by Impact:

1. **DISCOVERY** — 99.985% of ICS knowledge not ingested
2. **ANSWER_GENERATION** — Grounding failures erode trust
3. **EXTRACTION** — Low-quality entities make graph unreliable
4. **METADATA** — 98.4% documents unteam-classified
5. **GRAPH** — Noise exceeds signal
6. **RETRIEVAL** — 10% failure rate on edge cases
7. **CHUNKING** — Evidence gap in 43.7% of chunks
8. **ABSTENTION** — False positives on out-of-scope queries

---

## 7. Concierge Decision

### What Concierge already gives us (assumed):
- Confluence search and retrieval
- SharePoint document access
- Salesforce Knowledge/Case access
- GitHub code search
- Enterprise SSO/authentication
- Cross-source semantic search
- Agent tool execution

### What KURUKSHETRA already gives us:
- Knowledge Graph (entities, relationships, evidence, traversal)
- 7 retrieval strategies with benchmarks
- Evidence-grounded answer generation with citations
- SEAL unknown-term → glossary learning loop
- Multi-team ownership tracking
- Source adapter contract
- Retrieval-time access control
- Organizational Map (8 teams, sub-teams)
- Self-improvement recommendations
- Evaluation harness

### What is redundant to build:
- Individual Confluence/SharePoint/GitHub connectors (use Concierge)
- Enterprise SSO (use Concierge)
- Per-source pagination/rate-limiting (use Concierge)
- Per-source credential management (use Concierge)

### What KURUKSHETRA still needs:
- More ingested documents (currently 0.015% of ICS)
- Better entity extraction (deterministic patterns produce garbage)
- Team classification (98.4% unclassified)
- Grounding validation (answer generator accepts irrelevant evidence)
- Structured XLSX representation
- Multi-document reasoning
- Production Concierge adapter

### Should Concierge be a source/access layer?

**YES, for the following reasons:**
1. KURUKSHETRA's unique value is knowledge intelligence, not source connectivity
2. Concierge already handles enterprise auth, pagination, and normalization
3. A `ConciergeAdapter` implementing `SourceAdapter` would immediately unlock 4+ enterprise sources
4. KURUKSHETRA should own: graph, retrieval, SEAL, answer generation, evaluation
5. Concierge should own: source connectivity, auth, normalization, sync

### Should direct network-share ingestion remain?

**YES** — as a supplementary path for sources Concierge doesn't cover (network filesystems, local files, custom data sources). The KnowledgeWatcher + KnowledgeFabric already supports this.

---

## 8. Final Score

### Evidence-Based RAG Scores (1-5 scale)

| Dimension | Current | After Gap Resolution | Evidence |
|---|---|---|---|
| **Corpus Coverage** | **1.0** | 3.5 | 23/152,867 ICS files = 0.015%. 482 local docs are demo/test. |
| **Retrieval** | **4.0** | 4.5 | BM25 R@3=90%, MRR=0.90. Hybrid R@3=90%. Vector slower but complementary. |
| **Grounding** | **2.5** | 4.0 | Answer citations work. But "annual revenue" should abstain. 10% false-positive rate. |
| **Knowledge Representation** | **2.0** | 3.5 | Graph has 4,164 entities but 63% low-confidence. Entity quality is very low. |
| **Organizational Understanding** | **1.5** | 3.5 | 98.4% documents unclassified. OrgMap knows 8 teams but concept_teams is empty. |
| **Freshness** | **2.0** | 3.5 | KnowledgeWatcher exists but only 23 real docs. No continuous enterprise sync. |
| **Self-Learning** | **2.0** | 3.0 | SEAL loop works (35 confirmed). But 894 pending terms unresolved. No strategy learning. |
| **Security** | **2.5** | 3.5 | API key auth + visibility filtering. No RBAC, no audit trail, no PII detection. |
| **Enterprise Readiness** | **1.5** | 3.5 | Source adapter contract built. Salesforce transport mocked. No real enterprise connectors. |

### Current Empirical RAG Score: **2.3 / 5.0**

**Strengths:**
- Strong retrieval engine (BM25 at 90% recall)
- Working evidence-grounded answer generation
- SEAL learning loop operational
- Source adapter architecture ready
- 537 tests, zero regressions

**Critical Weaknesses:**
- 0.015% corpus coverage — SANJAYA knows almost nothing about the real enterprise
- 98.4% documents have no team classification
- Graph entity quality is very low — noise exceeds signal
- Answer grounding can fail on out-of-scope queries
- No live enterprise source connection

### Potential Score After Gap Resolution: **3.5 / 5.0**

Achievable by:
1. Ingesting 500+ ICS documents → Coverage 1.0→3.5
2. Fixing entity extraction → Representation 2.0→3.5
3. Implementing Concierge adapter → Enterprise 1.5→3.5
4. Fixing grounding validation → Grounding 2.5→4.0
5. Running team classifier on existing corpus → Org understanding 1.5→3.5

---

## 9. Top 10 Weaknesses (Ranked by Impact)

| Rank | Weakness | Category | Impact | Fix Difficulty |
|---|---|---|---|---|
| 1 | Only 23/152,867 ICS files ingested (0.015%) | DISCOVERY | CRITICAL | Medium (need source pipeline) |
| 2 | Grounding failure on out-of-scope queries | ANSWER_GENERATION | CRITICAL | Small (raise relevance threshold) |
| 3 | 98.4% documents unclassified by team | METADATA | HIGH | Medium (improve classifier) |
| 4 | Deterministic entity extraction produces garbage | EXTRACTION | HIGH | Large (needs LLM extraction) |
| 5 | 63% graph relationships are low-confidence | GRAPH | HIGH | Medium (filter + improve extraction) |
| 6 | No live enterprise source connection | ENTERPRISE | HIGH | Medium (Concierge adapter) |
| 7 | 894 pending unknown terms unresolved | SELF-LEARNING | MEDIUM | Small (SEAL interview) |
| 8 | concept_teams table empty | KNOWLEDGE | MEDIUM | Small (populate during ingestion) |
| 9 | No multi-document reasoning | ANSWER_GENERATION | MEDIUM | Large (requires architecture) |
| 10 | BM25 dominates Vector (40x faster, better recall) | RETRIEVAL | LOW | N/A (expected for keyword-heavy corpus) |

---

## 10. Recommended Next 3 Milestones

### Milestone 1: Fix Grounding + Expand Corpus (Immediate)
- Raise MIN_QUERY_EVIDENCE_RELEVANCE to 0.50 to prevent false answers
- Ingest the full Omkar/Process Documents folder (24 files)
- Ingest representative General_Documents (50-100 SPM/ICS process docs)
- Run team classifier on all 770 documents
- Target: 100+ real documents, 90%+ team classification

### Milestone 2: Improve Entity Extraction (Near-term)
- Evaluate whether LLM-based entity extraction would significantly improve quality
- If yes, implement minimal LLM entity extractor for system/process/team entities
- Clean up existing graph: filter low-confidence relationships, remove garbage entities
- Populate concept_teams during ingestion
- Target: graph quality score > 3.5

### Milestone 3: Concierge Integration Adapter (Medium-term)
- Build ConciergeAdapter implementing SourceAdapter contract
- Prove SANJAYA can answer from Confluence/Salesforce through Concierge
- This immediately unlocks 4+ enterprise sources
- Target: enterprise readiness score > 3.0

---

## 11. Files Created

| File | Purpose |
|---|---|
| `docs/MISSION_3_27_KNOWLEDGE_COVERAGE.md` | This report |

## 12. Files Modified

None. Audit only.

## 13. Test Result

**537/537 pass, 0 failures, 1 skipped. No regressions.**

## 14. Whether Source Was Modified

**NO.** Network share was not accessed during this audit. All analysis was performed against existing DuckDB data and source discovery profiles.
