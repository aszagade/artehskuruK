# KURUKSHETRA Foundation Capability Matrix

**Audit Date:** August 25, 2026
**Git HEAD:** `b72f896` (Mission 3.15 — XLSX noise cleanup promotion)
**Test Baseline:** 259/259 pass (107.65s)
**Working Tree:** 10 uncommitted files (Mission 3.8B work + benchmark scripts)

---

## Status Legend

| Status | Meaning |
|--------|---------|
| **IMPLEMENTED** | Code exists, functional, in production path |
| **VERIFIED** | Measured and proven against real data |
| **PARTIAL** | Partially implemented; has gaps |
| **EXPERIMENTAL** | Code exists but not in production path or not benchmarked |
| **DESIGNED** | Interface/contract exists but no real implementation |
| **MISSING** | Not implemented; no code found |
| **UNKNOWN** | Cannot determine from repository evidence alone |

---

## 1. INGESTION

| Capability | Status | Repository Evidence | Tests | Known Limitation |
|-----------|--------|-------------------|-------|-----------------|
| PDF extraction | **VERIFIED** | `extractors/text_extractor.py` — pdfplumber | `test_generic_ingestion.py` | Multi-column PDFs lose reading order |
| DOCX extraction | **VERIFIED** | `extractors/text_extractor.py` — python-docx | `test_generic_ingestion.py` | Only extracts paragraphs + table text |
| XLS extraction | **VERIFIED** | `extractors/text_extractor.py` — xlrd | `test_xls_extraction.py`, `test_xlsx_noise_cleanup.py` | Legacy OLE2 format only |
| XLSX extraction | **VERIFIED** | `extractors/text_extractor.py` — openpyxl | `test_xlsx_noise_cleanup.py` (8 tests) | No formula evaluation; NaN/Unnamed cleanup applied |
| CSV extraction | **IMPLEMENTED** | `extractors/text_extractor.py` — pandas | Generic test coverage | No header inference for headerless CSVs |
| TXT extraction | **IMPLEMENTED** | `extractors/text_extractor.py` — UTF-8 fallback | `test_generic_ingestion.py` | Encoding detection is best-effort |
| Markdown extraction | **IMPLEMENTED** | `extractors/text_extractor.py` — treated as text | `test_generic_ingestion.py` | Markdown structure not preserved |
| Source discovery | **VERIFIED** | `source_discovery/profiler.py`, `__main__.py` | `test_source_discovery.py` | Read-only; no automated triggers |
| Recursive sources | **VERIFIED** | `source_discovery/profiler.py` — recursive scan | `test_source_discovery.py` | Tested on 152K-file network share |
| Deduplication | **VERIFIED** | `services/registrar.py` — SHA-256 | `test_document_registrar.py` | Same-filename different-content detected |
| Incremental change detection | **MISSING** | — | — | No file modification time tracking |
| Versioning | **MISSING** | — | — | No document version history |
| Provenance | **VERIFIED** | `source_path` column in documents table | Ingestion tests | Original path preserved through pipeline |
| Structured spreadsheet handling | **PARTIAL** | NaN/Unnamed cleanup; no sheet/header/row semantic preservation | `test_xlsx_noise_cleanup.py` | Column headers and label-value pairs lost in workflow-style sheets |
| Canonical IngestionResult | **VERIFIED** | `pipeline/ingest.py` — IngestionResult dataclass | Integration tests | Returns structured stage-by-stage results |
| Semantic chunking | **VERIFIED** | `chunking/semantic.py` — SemanticSplitter | Ingestion tests | Sentence-based; no heading/section detection |
| Deterministic chunking | **IMPLEMENTED** | `chunking/splitter.py` — DeterministicSplitter | Unit tests | Fixed-size with overlap |
| Bulk ingestion | **IMPLEMENTED** | `pipeline/ingest.py` — `ingest_batch()` | Batch tests | One file at a time; no parallel processing |
| Knowledge Cleaner | **IMPLEMENTED** | `preprocessing/` module | Pipeline tests | Basic text normalization only |
| Content enricher | **PARTIAL** | `services/content_enricher.py` — IDeaS-specific patterns | Pipeline tests | Contains hardcoded product/team assumptions |
| Team classifier | **VERIFIED** | `services/team_classifier.py` + `agent/org_map.py` | `test_team_classifier.py` | Keyword-based; no semantic understanding |
| Freshness tracker | **IMPLEMENTED** | `services/freshness.py` | Pipeline tests | Date extraction from text; no file-mtime tracking |
| PDF-specific extractor | **IMPLEMENTED** | `extractors/pdf.py` — PDFExtractor class | Tests | Exists alongside TextExtractor |

---

## 2. RETRIEVAL

| Capability | Status | Repository Evidence | Tests | Known Limitation |
|-----------|--------|-------------------|-------|-----------------|
| BM25 | **VERIFIED** | `retrieval/database_bm25.py` — DatabaseBM25Retriever | `test_retrieval.py`, benchmark | DuckDB FTS; cached after first query |
| Vector | **VERIFIED** | `retrieval/vector.py` — VectorRetriever | `test_retrieval.py`, benchmark | Brute-force cosine; ~1.3s latency |
| Hybrid (BM25+Vector) | **VERIFIED** | `retrieval/hybrid.py` — HybridRetriever | `test_hybrid_normalization.py` (16 tests) | Normalized fusion at 0.5/0.5; best measured strategy (70% R@3) |
| Score normalization | **VERIFIED** | `retrieval/hybrid.py` — `_min_max_normalize()` | `test_hybrid_normalization.py` | Handles empty/single/equal-score edge cases |
| RRF (Reciprocal Rank Fusion) | **EXPERIMENTAL** | Benchmarked in `scripts/benchmark_hybrid.py` | No dedicated tests | Achieved 65% R@3; not promoted to production |
| Graph-assisted retrieval | **EXPERIMENTAL** | `retrieval/graph_retriever.py` — GraphAugmentedRetriever | `test_retrieval.py` | Vector + graph enrichment; 65% R@3 (same as Vector) |
| Parent/Child retrieval | **IMPLEMENTED** | `retrieval/parent_child.py` — ParentChildRetriever | Module exists; no dedicated benchmark | Groups sequential chunks as parents; not benchmarked against real corpus |
| Contextual retrieval | **IMPLEMENTED** | `retrieval/contextual.py` — ContextualRetriever | Module exists; no dedicated benchmark | Prepends document title to query; not benchmarked |
| HyDE | **IMPLEMENTED** | `retrieval/hyde.py` — HyDERetriever | Module exists | Template-based (no LLM); same as Vector in practice |
| MultiQuery | **IMPLEMENTED** | `retrieval/multi_query.py` — MultiQueryRetriever | Module exists | 12 variations per query; 325% slower than Vector |
| CrossVerifier | **IMPLEMENTED** | `retrieval/cross_verifier.py` — CrossVerifier | Module exists | Bayesian fusion across strategies; not benchmarked on real corpus |
| BGE Reranking | **IMPLEMENTED** | `reranking/bge_reranker.py` — BGEReranker | `test_reranking.py` | CrossEncoder (BAAI/bge-reranker-v2-m3); requires model download |
| Late interaction | **MISSING** | — | — | No ColBERT/multi-vector implementation |
| Query rewriting | **MISSING** | — | — | No query reformulation |
| Query decomposition | **MISSING** | — | — | No multi-part query handling |
| Metadata-aware retrieval | **MISSING** | — | — | No document metadata filtering during search |
| Retrieval-time visibility | **VERIFIED** | `retrieval/access_control.py` — VisibilityFilter | `test_access_control.py` (17 tests) | Filters PUBLIC < INTERNAL < CONFIDENTIAL < RESTRICTED |
| FilteredRetriever wrapper | **VERIFIED** | `retrieval/access_control.py` — FilteredRetriever | Access control tests | Over-fetches 3x to compensate for filtering |
| BM25 latency | **VERIFIED** | First query ~185ms; subsequent ~21ms | Benchmark | FTS index cached in memory |
| Vector latency | **VERIFIED** | ~1.3s (brute-force cosine) | Benchmark | No ANN index (FAISS/HNSW) |
| Hybrid latency | **VERIFIED** | ~1.3s (dominated by Vector) | Benchmark | Fusion overhead <1ms |

---

## 3. KNOWLEDGE

| Capability | Status | Repository Evidence | Tests | Known Limitation |
|-----------|--------|-------------------|-------|-----------------|
| Document registry | **VERIFIED** | `services/registrar.py` — DocumentRegistrar | `test_document_registrar.py` | Sequential DOC-NNNNNN IDs |
| Chunk persistence | **VERIFIED** | `registry/chunks.py` — ChunkRepository | Ingestion tests | Stored in DuckDB `chunks` table |
| Entities | **VERIFIED** | `graph/models.py` — Entity, EntityType | `test_graph.py` | 8 entity types: DOCUMENT, PROCESS, PERSON, SYSTEM, METRIC, CONFIGURATION, INCIDENT, KNOWLEDGE_ARTICLE |
| Relationships | **VERIFIED** | `graph/models.py` — Relationship, RelationType | `test_graph.py` | 9 relation types: RELATED_TO, DEPENDS_ON, CONTAINS, GENERATES, USES, MONITORS, CONFIGURES, TRIGGERS, RESOLVES |
| Evidence | **VERIFIED** | `graph/entity_types.py` — Evidence | Graph tests | Provenance tracking with source_document_id, source_chunk_id, confidence |
| Graph repository | **VERIFIED** | `graph/repository.py` — GraphRepository | `test_graph.py` | DuckDB persistence; 3,925 entities, 17,384 relationships after cleanup |
| Graph traversal | **IMPLEMENTED** | `graph/traversal.py` — GraphTraversalEngine | `test_graph_traversal.py` | Path finding, impact analysis, community detection |
| Graph extraction | **VERIFIED** | `graph/extractor.py` — SmartEntityExtractor | Integration tests | Deterministic pattern-based; misses unknown entities |
| Multi-team ownership | **PARTIAL** | `agent/org_map.py` — cross_team detection | `test_team_classifier.py` | Keyword-based; entity forced to single team in entity model |
| Glossary | **VERIFIED** | `services/glossary.py` — GlossaryManager | `test_glossary.py` | 35 confirmed terms; 873 pending unknowns |
| Unknown-term detection | **VERIFIED** | `services/glossary.py` — `detect_unknown_terms()` | `test_glossary.py` | Regex patterns: ALL CAPS, CamelCase, underscore/hyphen |
| Unknown-term resolution | **PARTIAL** | `services/glossary.py` — `confirm_term()`, `reject_term()` | `test_glossary.py` | Confirm/reject works; no aliases, no conflict handling, no multiple meanings |
| Noise filtering | **VERIFIED** | `services/glossary.py` — `_is_noise_term()` | `test_knowledge_hygiene.py` | Filters NaN, dates, sheet headers, common English |
| Aliases | **MISSING** | — | — | No alias representation |
| Conflict handling | **MISSING** | — | — | No conflicting evidence detection |
| Temporal/version knowledge | **MISSING** | — | — | No first_seen/last_seen/version tracking |
| Knowledge hygiene | **VERIFIED** | Mission 3.8B improvements | `test_knowledge_hygiene.py` | NaN, date patterns, spreadsheet artifacts filtered |
| Graph integrity | **VERIFIED** | Mission 3.13 cleanup | Graph tests | Orphan entities/relationships cleaned |
| Document visibility | **VERIFIED** | `documents.visibility` column | Access control tests | PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED |
| Content metadata | **PARTIAL** | `services/content_enricher.py` | Pipeline tests | IDeaS product/team detection hardcoded |

---

## 4. SEAL / LEARNING

| Capability | Status | Repository Evidence | Tests | Known Limitation |
|-----------|--------|-------------------|-------|-----------------|
| Unknown-term queue | **VERIFIED** | `seal/unknowns.py` — UnknownLoader | `test_seal.py` | Sorted by occurrence count; enriched with evidence |
| Human confirmation | **VERIFIED** | `services/glossary.py` — `confirm_term()` | `test_seal.py`, real interview | 35 terms confirmed |
| Human rejection | **VERIFIED** | `services/glossary.py` — `reject_term()` | `test_seal.py` | 6 terms rejected |
| Decision provenance | **VERIFIED** | `seal/decisions.py` — DecisionStore | `test_seal.py` | Stores who/when/why; decisions persisted in DuckDB |
| Reusable glossary | **VERIFIED** | `services/glossary.py` — glossary table | `test_glossary.py` | 35 confirmed terms available for future ingestion |
| Retrieval feedback | **EXPERIMENTAL** | `services/feedback.py` — FeedbackLoop | `test_feedback.py` | Stores feedback; score adjustment exists but not wired into production retrieval |
| Strategy learning | **MISSING** | — | — | No automatic strategy selection based on outcomes |
| Outcome learning | **MISSING** | — | — | No query → outcome → adjustment loop |
| Self-optimization | **MISSING** | — | — | No automatic parameter tuning |
| Self-verification | **EXPERIMENTAL** | `services/self_verifier.py` — SelfVerifier | Module exists | Generates verification questions; not run automatically |
| Pattern discovery | **EXPERIMENTAL** | `services/pattern_discovery.py` — PatternDiscovery | Module exists | Query clustering, emerging issues, knowledge gaps; no real data yet |
| Fabric evolution | **EXPERIMENTAL** | `services/fabric_evolution.py` — FabricEvolution | Module exists | A/B testing infrastructure; no experiments recorded |
| Self-recommender | **EXPERIMENTAL** | `services/self_recommender.py` — SelfRecommender | Module exists | Generates improvement recommendations; not automated |
| Improvement pipeline | **EXPERIMENTAL** | `services/improvement_pipeline.py` — ImprovementPipeline | Module exists | Proposal workflow with human approval; no proposals generated |

---

## 5. SANJAYA / AGENT

| Capability | Status | Repository Evidence | Tests | Known Limitation |
|-----------|--------|-------------------|-------|-----------------|
| Intent routing | **VERIFIED** | `agent/intent.py` — IntentClassifier | `test_sanjaya.py` | Keyword-based: Smartsheet > Datadog > SQL > Knowledge |
| Semantic intent | **IMPLEMENTED** | `agent/semantic_intent.py` — SemanticIntentClassifier | `test_sanjaya.py` | Embedding-free; uses keyword overlap + example similarity |
| Planning | **VERIFIED** | `agent/planner.py` — SANJAYAPlanner | `test_sanjaya.py` | Semantic → keyword fallback → team enrichment |
| OrgMap integration | **VERIFIED** | `agent/org_map.py` — OrgMap | `test_org_map.py` | 7 teams defined (SPM, ICS, SDOPS, CPM, HR, IT, ROA) |
| Evidence selection | **MISSING** | — | — | No retrieval integration in SANJAYA planner |
| Answer generation | **MISSING** | — | — | No answer assembly from retrieved chunks |
| Verification | **MISSING** | — | — | No answer verification step |
| Abstention | **MISSING** | — | — | No "I don't know" capability |
| Tool implementations | **DESIGNED** | `agent/models.py` — Tool enum | Interface only | SMARTSHEET, DATADOG, SQL, KNOWLEDGE tools defined but only KNOWLEDGE route works end-to-end |
| Human approval | **MISSING** | — | — | No approval gates |
| Action execution | **MISSING** | — | — | No tool execution framework |
| Conversation memory | **IMPLEMENTED** | `agent/memory.py` — ConversationMemory | `test_memory.py` | Follow-up detection; no persistence across sessions |
| Clarifier | **IMPLEMENTED** | `agent/clarifier.py` — Clarifier | `test_clarifier.py` | Generates clarification requests; not wired into main flow |
| Agent registry | **IMPLEMENTED** | `agent/registry.py` — AgentRegistry | `test_agent_registry.py` | Register, route, lifecycle; no real agents registered |
| Agent templates | **IMPLEMENTED** | `agent/templates.py` | `test_agent_templates.py` | Predefined templates for specialist agents |
| Multi-turn context | **PARTIAL** | `agent/planner.py` — `create_plan_with_context()` | Memory tests | Basic follow-up detection; no session persistence |

---

## 6. SECURITY

| Capability | Status | Repository Evidence | Tests | Known Limitation |
|-----------|--------|-------------------|-------|-----------------|
| Retrieval-time visibility | **VERIFIED** | `retrieval/access_control.py` — VisibilityFilter | `test_access_control.py` (17 tests) | Filters chunks by document visibility level |
| Authentication | **MISSING** | — | — | No user authentication |
| User identity | **MISSING** | — | — | No identity model |
| Roles | **MISSING** | — | — | No RBAC |
| Team membership | **MISSING** | — | — | No user→team association |
| API authorization | **MISSING** | — | — | No middleware or token validation |
| Graph authorization | **MISSING** | — | — | No entity-level access control |
| SEAL authorization | **MISSING** | — | — | No access control on confirm/reject |
| Prompt injection protection | **MISSING** | — | — | No input sanitization for LLM prompts |
| PII/secret detection | **MISSING** | — | — | No content scanning for sensitive data |
| Audit logging | **MISSING** | — | — | No operation audit trail |
| Tool authorization | **MISSING** | — | — | No tool allowlists/denylists |
| Approval gates | **MISSING** | — | — | No human-in-the-loop for sensitive actions |
| Database encryption | **MISSING** | — | — | DuckDB stored in plaintext |

---

## 7. SOURCES / CONNECTORS

| Capability | Status | Repository Evidence | Tests | Known Limitation |
|-----------|--------|-------------------|-------|-----------------|
| Local file ingestion | **VERIFIED** | `pipeline/ingest.py` + `extractors/` | Full test suite | Supports PDF/DOCX/XLS/XLSX/CSV/TXT/MD |
| Network share (read-only) | **VERIFIED** | `\\ina6fs01\Dept_shares\ICS` tested | Runtime tests | Source discovery + dry-run validated |
| Source profiling | **VERIFIED** | `source_discovery/profiler.py` | `test_source_discovery.py` | 152K files profiled; metadata-only |
| Confluence connector | **DESIGNED** | `graph/connectors.py` — ConfluenceConnector stub | No tests | Abstract interface only; returns False/empty |
| Salesforce connector | **MISSING** | — | — | No connector interface |
| Datadog connector | **DESIGNED** | `graph/connectors.py` — DatadogConnector stub | No tests | Abstract interface only |
| Graph API/mail connector | **MISSING** | — | — | No connector |
| SQL connector | **DESIGNED** | `graph/connectors.py` — SQLConnector stub | No tests | Abstract interface only |
| Smartsheet connector | **MISSING** | — | — | Intent routing exists; no connector |
| Teams connector | **DESIGNED** | `graph/connectors.py` — TeamsConnector stub | No tests | Abstract interface only |
| Outlook connector | **MISSING** | — | — | No connector |
| SEAL connector | **DESIGNED** | `graph/connectors.py` — SEALConnector stub | No tests | Abstract interface only |
| Event Bus | **IMPLEMENTED** | `events/bus.py`, `events/models.py`, `events/normalizer.py`, `events/repository.py` | `test_events.py` | Deterministic event ingestion; no real enterprise events |

---

## 8. EVALUATION

| Capability | Status | Repository Evidence | Tests | Known Limitation |
|-----------|--------|-------------------|-------|-----------------|
| Evaluation harness | **IMPLEMENTED** | `evaluation/harness.py` — EvaluationHarness | `test_evaluation.py` | Supports gold-standard Q&A evaluation |
| Recall@K | **VERIFIED** | `scripts/benchmark_retrieval.py` | Manual benchmark | Measured R@3, R@5 across 20 questions |
| MRR | **VERIFIED** | `scripts/benchmark_retrieval.py` | Manual benchmark | MRR measured per strategy |
| Latency measurement | **VERIFIED** | `scripts/benchmark_retrieval.py` | Manual benchmark | End-to-end latency for all strategies |
| Regression testing | **VERIFIED** | 259 tests in `tests/` | Full suite | Pass/fail regression on every change |
| Strategy comparison | **VERIFIED** | `scripts/benchmark_retrieval.py`, `scripts/benchmark_hybrid.py` | Manual benchmark | BM25 vs Vector vs Hybrid vs Graph-Aug |
| Grounding/citation evaluation | **MISSING** | — | — | No automated citation accuracy measurement |
| Agent evaluation | **MISSING** | — | — | No SANJAYA quality benchmark |
| Security evaluation | **MISSING** | — | — | No security testing framework |
| Real-corpus benchmark | **VERIFIED** | 20-question ICS benchmark | `scripts/benchmark_retrieval.py` | Based on 23 real ICS documents |

---

## WHAT KURUKSHETRA CAN DO TODAY

1. **Ingest documents** in 7 formats (PDF, DOCX, XLS, XLSX, CSV, TXT, MD) through a single canonical pipeline.
2. **Persist knowledge** in DuckDB with full provenance (source path, SHA-256, team, visibility).
3. **Retrieve information** using BM25 (21ms), Vector (1.3s), or normalized Hybrid (1.3s; best measured at 70% R@3).
4. **Enforce access control** at retrieval time using PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED visibility levels.
5. **Extract entities and relationships** deterministically from document text into a knowledge graph (3,925 entities, 17,384 relationships).
6. **Detect unknown terms** during ingestion and queue them for human confirmation via SEAL.
7. **Maintain a glossary** of confirmed organizational terminology (35 confirmed terms).
8. **Classify documents** to organizational teams using keyword-based OrgMap (SPM, ICS, SDOPS, CPM, HR, IT, ROA).
9. **Profile network sources** read-only before ingestion (tested on 152K-file ICS share).
10. **Route queries** through SANJAYA intent classification to knowledge, Datadog, SQL, or Smartsheet tools.
11. **Run a demo runtime** with knowledge inbox, document detection, and ingestion status tracking.
12. **Evaluate retrieval quality** with a 20-question real-corpus benchmark and regression testing.
13. **Track verification questions** and detect knowledge decay over time (experimental).
14. **Record user feedback** and compute score adjustments for chunks (experimental).

## WHAT IT CANNOT YET DO

1. **Answer questions** — SANJAYA can route to knowledge retrieval but cannot assemble an answer from retrieved chunks.
2. **Cite sources** in answers — No grounding/citation pipeline exists.
3. **Abstain** when uncertain — No "I don't know" or confidence threshold mechanism.
4. **Authenticate users** — No authentication, identity, or role system.
5. **Authorize API access** — No middleware, tokens, or session management.
6. **Connect to enterprise systems** — All external connectors are stubs (Confluence, Datadog, Salesforce, SQL, Teams, Outlook, Smartsheet).
7. **Detect incremental changes** — No file modification tracking; re-ingestion relies on SHA-256 dedup.
8. **Handle document versions** — No temporal knowledge or version history.
9. **Detect conflicting evidence** — No mechanism to identify and surface contradictory information.
10. **Expand queries automatically** — No query rewriting, decomposition, or glossary-based expansion.
11. **Select retrieval strategies adaptively** — No automatic strategy selection based on query type.
12. **Protect against prompt injection** — No input sanitization for LLM-facing paths.
13. **Audit operations** — No audit log for who queried/ingested/confirmed what.
14. **Extract spreadsheet structure** — NaN cleanup exists but column headers and label-value semantics are lost in workflow-style XLSX.
15. **Learn from outcomes** — Feedback storage exists but is not wired into retrieval scoring.

## TOP 10 VERIFIED GAPS

| # | Gap | Impact | Evidence |
|---|-----|--------|----------|
| 1 | **No answer generation** | SANJAYA cannot provide answers from retrieved knowledge | No answer assembly code in agent/ |
| 2 | **No authentication/authorization** | Cannot secure API or restrict knowledge access | No auth middleware, no user model |
| 3 | **No enterprise connectors** | Real-time data from Datadog/Salesforce/Teams unavailable | Only stubs in `graph/connectors.py` |
| 4 | **No query expansion** | 35% of benchmark queries fail due to terminology mismatch | Missed queries: Q01, Q10, Q13, Q17, Q18 |
| 5 | **No incremental change detection** | Modified documents on network share not detected | No file-watcher or mtime tracking |
| 6 | **No conflict detection** | Contradictory information silently coexists | No cross-document consistency check |
| 7 | **No audit logging** | Cannot trace who did what to knowledge | No audit table or logging middleware |
| 8 | **No document versioning** | Same document in multiple versions treated as separate | No version identity tracking |
| 9 | **Spreadsheet representation loss** | Workflow-style XLSX loses headers and structure | Mission 3.14/3.15 showed NaN cleanup is insufficient |
| 10 | **No answer grounding** | Even if answers existed, no citation pipeline | No chunk→answer→citation mapping |

## TOP 5 NEXT MILESTONES

| Priority | Milestone | Rationale |
|----------|-----------|-----------|
| 1 | **Answer generation + citation** | Without this, retrieval is useless to end users |
| 2 | **Authentication + authorization** | Required before any real enterprise deployment |
| 3 | **First real connector** (network share auto-ingestion) | Proves the connector architecture with real data |
| 4 | **Query expansion via glossary** | Leverage 35 confirmed terms to improve the 35% miss rate |
| 5 | **Incremental change detection** | Enables automatic knowledge refresh from network sources |

## DEFERRED / DO NOT BUILD YET

| Item | Reason |
|------|--------|
| Late-interaction retrieval (ColBERT) | Corpus too small (3,419 chunks); no measurable benefit expected |
| Adaptive entity discovery / LLM extraction | Deterministic extraction covers current needs; wait for larger corpus |
| GraphRAG | Graph-augmented retrieval showed same performance as Vector alone |
| Production connectors (Salesforce, Datadog, Teams, SQL) | Need answer generation + auth before connecting real systems |
| Full self-learning loop | Feedback storage exists but no outcome measurement to learn from |
| Multi-tenant isolation | Single-user local deployment; premature for current scale |
| Distributed/embedded vector DB (FAISS/HNSW) | 1.3s latency acceptable at current corpus size |
| Message brokers / event streaming | Polling sufficient for local demo runtime |
| Production frontend | API + polling sufficient for current development |
| Knowledge fabric auto-evolution | Infrastructure exists but no real experiments to evolve from |

## CURRENT ENTERPRISE RAG MATURITY

**Internal Engineering Assessment: Level 2 — Working Prototype**

| Dimension | Score | Notes |
|-----------|:-----:|-------|
| Ingestion | 7/10 | 7 formats; no versioning; no incremental; spreadsheet partial |
| Retrieval | 6/10 | 4 strategies measured; best at 70% R@3; no query expansion |
| Knowledge | 5/10 | Graph + glossary exist; no conflict/temporal/alias support |
| Learning | 3/10 | SEAL confirm/reject works; no feedback loop; no self-optimization |
| Agent | 2/10 | Intent routing works; no answer generation; no tool execution |
| Security | 1/10 | Visibility filtering only; no auth/audit/encryption |
| Connectors | 1/10 | Stubs only; no real enterprise integration |
| Evaluation | 5/10 | 20-question benchmark; regression tests; no agent/security eval |

**Overall: 259 passing tests; 7 format extractors; 4 retrieval strategies; 1 real enterprise corpus (23 ICS documents); 1 verified security control; 0 production answers delivered.**

---

## ARCHITECTURE REFERENCE

```
Source (file/share/API)
  → TextExtractor (PDF/DOCX/XLS/XLSX/CSV/TXT/MD)
  → KnowledgeCleaner
  → DocumentRegistrar (SHA-256 dedup, provenance)
  → TeamClassifier (OrgMap keyword matching)
  → ContentEnricher (IDeaS-specific product detection)
  → Splitter (Deterministic or Semantic)
  → ChunkRepository (DuckDB)
  → [optional] VectorIndexer (BGE embeddings)
  → GlossaryManager (unknown-term detection)
  → GraphRegistry (SmartEntityExtractor → GraphRepository)
  → FreshnessTracker
  → IngestionResult

Retrieval:
  BM25 (21ms) ─────┐
                    ├→ HybridRetriever (normalized 0.5/0.5, 1.3s)
  Vector (1.3s) ───┘
  Graph-Augmented (experimental)
  Parent/Child (experimental)
  HyDE (experimental)
  MultiQuery (experimental)
  CrossVerifier (experimental)
  BGE Reranker (experimental)
  → VisibilityFilter (PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED)
  → Results

Agent (SANJAYA):
  IntentClassifier (keyword + semantic)
  → OrgMap team routing
  → Plan(intent, tool, confidence)
  → [MISSING: retrieval integration]
  → [MISSING: answer generation]
  → [MISSING: tool execution]

SEAL:
  UnknownLoader (pending terms + evidence)
  → GlossaryManager.confirm_term() / reject_term()
  → DecisionStore (provenance)
  → Glossary (reusable knowledge)

Security:
  VisibilityFilter (only implemented control)
  → [MISSING: authentication]
  → [MISSING: authorization]
  → [MISSING: audit logging]
```

---

*Generated from repository evidence at commit `b72f896`. No code was modified during this audit.*
