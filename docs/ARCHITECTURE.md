# KURUKSHETRA Architecture

Enterprise Intelligence Platform for IDeaS Service Delivery.

---

## 1. Folder Structure

```
kurukshetra/
  core.py                    -- Legacy system models (Pydantic)
  agent/                     -- SANJAYA planner + agent swarm
    planner.py               -- SANJAYAPlanner (intent, routing, memory)
    models.py                -- Tool, Plan dataclasses
    memory.py                -- ConversationMemory, ConversationContext
    semantic_intent.py        -- SemanticIntentClassifier
    clarifier.py             -- Clarifier, ClarificationRequest
    registry.py              -- AgentRegistry, AgentRegistration
    templates.py             -- Domain-specific agent templates
    org_map.py               -- OrgMap (enterprise hierarchy config)
  retrieval/                 -- RAG retrieval strategies
    base.py                  -- BaseRetriever ABC
    bm25.py                  -- BM25Retriever (keyword)
    vector.py                -- VectorRetriever (semantic)
    database_bm25.py         -- DatabaseBM25Retriever (DuckDB)
    hybrid.py                -- HybridRetriever (BM25 + Vector fusion)
    hyde.py                  -- HyDERetriever
    multi_query.py           -- MultiQueryRetriever
    parent_child.py          -- ParentChildRetriever
    contextual.py            -- ContextualRetriever
    cross_verifier.py        -- CrossVerifier (5-strategy Bayesian)
    models.py                -- RetrievalResult
    graph_retriever.py       -- GraphAugmentedRetriever
  reranking/                 -- Reranking strategies
  embeddings/                -- Embedding generation (BGE)
  chunking/                  -- Text splitting
    splitter.py              -- DeterministicSplitter
    semantic.py              -- SemanticSplitter
    models.py                -- Chunk
  graph/                     -- Knowledge Graph Intelligence
    models.py                -- Entity, Relationship, EntityType, RelationType
    repository.py            -- GraphRepository (DuckDB)
    entity_types.py          -- Extended types, Evidence
    extractor.py             -- SmartEntityExtractor
    traversal.py             -- GraphTraversalEngine (BFS, pathfinding)
    registry.py              -- GraphRegistry (unified facade)
    connectors.py            -- Future connector stubs
  registry/                  -- DuckDB persistence
    database.py              -- get_connection()
    schema.py                -- Table definitions
    documents.py             -- DocumentRegistrar
    chunks.py                -- Chunk storage
    entities.py              -- Entity registry
  services/                  -- Supporting services
    registrar.py             -- DocumentRegistrar
    metadata.py              -- MetadataEnricher
    content_enricher.py      -- ContentEnricher
    freshness.py             -- FreshnessTracker
    feedback.py              -- FeedbackLoop
    glossary.py              -- GlossaryManager
    self_verifier.py         -- SelfVerifier
    self_recommender.py      -- SelfRecommender
    pattern_discovery.py     -- PatternDiscovery
    improvement_pipeline.py  -- ImprovementPipeline
    fabric_evolution.py      -- FabricEvolution
    team_classifier.py       -- TeamClassifier
  seal/                      -- Self-Evolving Adaptive Learning
    decisions.py             -- DecisionStore
    unknowns.py              -- UnknownLoader
    interview.py             -- InterviewSession
  opportunity/               -- Enterprise Opportunity Engine
    models.py                -- Event, Opportunity, DetectionResult
    repository.py            -- OpportunityRepository (DuckDB)
    detector.py              -- OpportunityDetector (7 rules)
    demo.py                  -- CLI demo
  pipeline/                  -- Ingestion pipelines
    ingest.py                -- IngestionPipeline (9-step)
    graph_indexer.py         -- Graph population bridge
    indexer.py               -- KnowledgeIndexer
  extractors/                -- PDF extraction
  preprocessing/             -- Text cleaning
  evaluation/                -- Test harness
  executors/                 -- Action executors
    knowledge.py             -- KnowledgeExecutor
  identity/                  -- Identity models
tests/
  test_graph.py              -- 43 graph tests
  test_opportunity.py        -- 22 opportunity tests
scripts/
  validate_graph.py          -- CLI graph validator
command_center/
  backend/main.py            -- FastAPI backend (40+ endpoints)
  frontend/                  -- Dashboard
sanjaya_developer.py         -- SEAL interview CLI
```

---

## 2. Module Responsibilities

| Module | Responsibility | Ownership Rule |
|--------|---------------|----------------|
| **SANJAYA (agent/)** | Orchestrates all queries. Classifies intent, routes to teams, manages conversation memory. | SANJAYA orchestrates. Never does retrieval itself. |
| **Retrieval (retrieval/)** | 5 strategies + cross-verifier. BM25, Vector, HyDE, Multi-Query, Parent-Child. | RAG retrieves. Never stores. |
| **Knowledge Graph (graph/)** | Entity extraction, relationship mapping, traversal, pathfinding, impact analysis. | Graph remembers. Never retrieves for SANJAYA directly. |
| **Registry (registry/)** | DuckDB persistence. Documents, chunks, entities, glossary, unknown terms. | Registry stores. Never processes. |
| **Services (services/)** | Content enrichment, freshness, feedback, glossary, team classification. | Services enrich. Never store raw data. |
| **SEAL (seal/)** | Human-in-the-loop learning. Interview sessions, decision storage. | SEAL learns. Never executes. |
| **Opportunity (opportunity/)** | Deterministic pattern analysis. Discovers automation/monitoring/documentation gaps. | Opportunity proposes. Never executes. |
| **Pipeline (pipeline/)** | Orchestrates ingestion flow. Extract -> Clean -> Register -> Classify -> Chunk -> Graph. | Pipeline processes. Never stores directly. |
| **Executors (executors/)** | Perform actions on external systems (future). | Executors act. Never learn. |

---

## 3. Data Flow: Document to SANJAYA

```
PDF/Document
    |
    v
[Extract] PDFExtractor
    |
    v
[Clean] KnowledgeCleaner
    |
    v
[Register] DocumentRegistrar -> documents table
    |
    v
[Classify Team] TeamClassifier -> OrgMap (SPM, ICS, SDOPS, CPM, HR, IT, ROA)
    |
    v
[Classify Content] ContentEnricher -> product, type, owner
    |
    v
[Chunk] SemanticSplitter / DeterministicSplitter -> chunks table
    |
    v
[Embed] BGE embeddings -> vector index
    |
    v
[Detect Terms] GlossaryManager -> unknown_terms table
    |
    v
[Freshness] FreshnessTracker -> staleness analysis
    |
    v
[Build Graph] GraphRegistry.ingest_document() -> graph_entities, graph_relationships, graph_evidence
    |
    v
User Query
    |
    v
[SANJAYA] Intent Classification -> Team Routing
    |
    v
[Hybrid Retrieval] BM25 + Vector (0.4/0.6) -> top 10
    |
    v
[Cross-Verification] 5 strategies -> Bayesian fusion -> confidence score
    |
    v
[Response] with evidence, confidence, team attribution
```

---

## 4. What is Deterministic vs Future AI

| Component | Current | Future |
|-----------|---------|--------|
| Text extraction | PDF parser (deterministic) | Same |
| Text cleaning | Regex + rules (deterministic) | Same |
| Chunking | Semantic similarity (deterministic) | Same |
| Embedding | BGE model (ML) | Same |
| BM25 retrieval | Term frequency (deterministic) | Same |
| Vector retrieval | Cosine similarity (ML) | Same |
| HyDE | Hypothetical doc generation (LLM) | Same |
| Multi-Query | Query expansion (LLM) | Same |
| Cross-verification | Bayesian fusion (deterministic) | Same |
| Entity extraction | Regex patterns (deterministic) | NER / LLM extraction |
| Relationship mapping | Pattern matching (deterministic) | LLM-based relationship inference |
| Graph traversal | BFS (deterministic) | Same |
| Impact analysis | BFS + scoring (deterministic) | Same |
| Team classification | Keyword matching (deterministic) | LLM classification |
| Content enrichment | Keyword + rules (deterministic) | LLM-based classification |
| Opportunity detection | Counting + thresholds (deterministic) | Same |
| SEAL interview | Human provides answers (human) | LLM-assisted suggestions |
| SANJAYA routing | Keyword intent (deterministic) | LLM intent classification |

---

## 5. Extension Points (Future Connectors)

| Connector | Interface | Data In -> Entity Types | Status |
|-----------|-----------|------------------------|--------|
| **Confluence** | `BaseConnector` ABC | Pages -> DOCUMENT, @mentions -> PERSON | Abstract stub |
| **Datadog** | `BaseConnector` ABC | Alerts -> INCIDENT, monitors -> PROCESS | Abstract stub |
| **SQL** | `BaseConnector` ABC | Tables -> SYSTEM, columns -> CONFIGURATION | Abstract stub |
| **Teams** | `BaseConnector` ABC | Files -> DOCUMENT, threads -> PROCESS | Abstract stub |
| **SEAL** | `BaseConnector` ABC | Feedback -> evidence updates | Abstract stub |

Each connector implements:
- `connect()` -> establish API connection
- `poll()` -> check for new data
- `ingest()` -> convert to entities/relationships -> feed into GraphRegistry
- `disconnect()` -> cleanup

---

## 6. Key Design Decisions

1. **Documents are immutable.** Knowledge is versioned. Conflicting documents create evidence-backed claims, never overwrite.

2. **OrgMap is configuration, not code.** Teams, sub-teams, keywords, and relationships live in `org_map.py` as structured data. Adding a team requires zero code changes.

3. **Evidence is mandatory.** Every graph relationship carries at least one Evidence record with source document, text fragment, confidence, and human_confirmed flag.

4. **Deterministic by default.** Every service uses rule-based algorithms. LLM integration is optional and isolated behind clear interfaces.

5. **Human-in-the-loop.** SEAL never auto-accepts. The Opportunity Engine never auto-executes. SANJAYA never acts without explicit user request.

6. **Single DuckDB.** One database file stores everything: documents, chunks, entities, relationships, evidence, glossary, decisions, opportunities. Simple, portable, zero-config.
