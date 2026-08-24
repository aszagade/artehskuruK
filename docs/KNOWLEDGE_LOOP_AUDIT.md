# KURUKSHETRA Knowledge Loop Audit

**Date:** August 24, 2026
**Scope:** End-to-end audit of the knowledge learning system
**Status:** Baseline established

---

## 1. Current Architecture (Actually Implemented)

### Database State (Production DuckDB)

| Table | Rows | Purpose |
|-------|------|---------|
| documents | 483 | Registered document identities |
| chunks | 3,272 | Text chunks for RAG |
| vectors | 3,273 | Embedding vectors for semantic search |
| graph_entities | 4,742 | Knowledge graph nodes (12 types) |
| graph_relationships | 24,916 | Knowledge graph edges (8 types) |
| graph_evidence | 11,319 | Provenance for graph edges |
| graph_entity_meta | 2,578 | Extended metadata (team, confidence) |
| team_classifications | 234 | Document-to-team assignments |
| glossary | 0 | Confirmed terminology |
| unknown_terms | 0 | Pending unknown terms |
| seal_decisions | 0 | Human-verified answers |
| agents | 0 | Registered agents |
| agent_registry | 0 | Agent lifecycle records |
| enterprise_events | 10 | Events from connectors |
| event_fingerprints | 10 | Dedup fingerprints |
| opportunity_events | 22 | Opportunity Engine events |
| opportunity_store | 15 | Detected opportunities |
| rag_feedback | 0 | User feedback on queries |
| chunk_score_history | 0 | Feedback-derived scores |

### Module Map

```
kurukshetra/
  pipeline/         IngestionPipeline, GraphIndexer
  retrieval/        BM25, Vector, HyDE, MultiQuery, ParentChild, CrossVerifier
  graph/            SmartEntityExtractor, GraphRegistry, GraphRepository, TraversalEngine, Validator
  services/         GlossaryManager, FeedbackLoop, TeamClassifier, SelfRecommender, etc.
  seal/             UnknownLoader, DecisionStore, InterviewSession
  events/           EventBus, EventNormalizer, EventRepository
  opportunity/      OpportunityDetector, OpportunityRepository
  agent/            SANJAYAPlanner, AgentRegistry, OrgMap, ConversationMemory
  executors/        KnowledgeExecutor, DatadogExecutor, SQLExecutor, SmartsheetExecutor

command_center/backend/
  main.py           FastAPI init + 7 routers (25 endpoints)

tests/              65 tests (43 graph + 22 opportunity)
```

---

## 2. Document Trace: End-to-End

### Path (implemented)

```
File on disk
  |  [1] PDFExtractor.extract()
  v
Raw text
  |  [2] KnowledgeCleaner.clean()
  v
Clean text
  |  [3] DocumentRegistrar.register()
  v
Document row (DuckDB: documents)
  |  [4] TeamClassifier.classify_document()
  v
Team classification (DuckDB: team_classifications)
  |  [5] ContentEnricher.enrich()
  v
Content metadata
  |  [6] SemanticSplitter.split()
  v
Chunks (DuckDB: chunks)
  |  [7] GlossaryManager.detect_unknown_terms()
  v
Unknown terms (DuckDB: unknown_terms)
  |  [8] analyze_freshness()
  v
Freshness analysis
  |  [9] GraphRegistry.ingest_document()
  v
  |-- SmartEntityExtractor.extract_from_document()
  |     -> 12 entity types, 12 relationship types
  |     -> Evidence attached to every relationship
  |
  |-- _upsert_extended_entity() x N
  |     -> graph_entities + graph_entity_meta
  |
  |-- _upsert_extended_relationship() x N
  |     -> graph_relationships
  |
  |-- _persist_evidence() x N
  |     -> graph_evidence
  v
Knowledge Graph populated
```

### Where the chain STOPS

1. **Embedding generation**: NOT called during ingestion pipeline. Vectors exist (3,273) but the connection between chunk creation and embedding is done separately (via `vector_indexer.py`). The pipeline does NOT generate embeddings.

2. **Unknown term detection runs** but returns 0 terms in production. The `KNOWN_TERMS` set is too broad — it excludes common technical terms that should be learned. The `_store_unknown_terms` method uses `INSERT OR IGNORE` which silently succeeds but the `occurrence_count` update logic is inverted (subtracts 1 from the count).

3. **SEAL pipeline**: `UnknownLoader` reads from `unknown_terms` (empty), `DecisionStore` writes to `seal_decisions` (empty). The SEAL interview loop has never been run.

4. **Glossary**: 0 confirmed entries. `confirm_term()` writes to both `glossary` and `unknown_terms` status, but no terms have been confirmed.

---

## 3. Event Trace: End-to-End

### Path (implemented)

```
External source (Datadog/Salesforce/etc.)
  |  [1] Connector calls EventBus.ingest() or .ingest_raw()
  v
EventNormalizer.normalize_<system>()
  |  [2] Maps raw data to canonical Event model
  v
EventBus.ingest()
  |  [3] Computes fingerprint (SHA-256)
  |  [4] EventRepository.insert_event()
  |      -> DuckDB: enterprise_events + event_fingerprints
  v
Event persisted (10 events)
```

### Where the chain STOPS

1. **Event → Graph**: NOT connected. Enterprise events are stored in `enterprise_events` but are never cross-referenced with `graph_entities`. A Datadog alert for "G3 RMS step failure" does NOT create or update a graph INCIDENT entity.

2. **Event → Opportunity Engine**: NOT connected at runtime. The `OpportunityDetector` reads from its own `opportunity_events` table (22 events), NOT from `enterprise_events` (10 events). These are two separate event stores.

3. **Event → SANJAYA**: NOT connected. SANJAYA has no access to real-time events.

4. **Connector → Event Bus**: No real connectors exist. The `DatadogExecutor`, `SQLExecutor`, `SmartsheetExecutor` in `executors/` are stubs that return placeholder data.

---

## 4. Graph Multi-Team Ownership Audit

### Principle
A system like G3 RMS may be:
- USED_BY multiple teams (SPM, ICS, ROA)
- MONITORED_BY another team (SDOPS)
- OPERATED_BY a third team
- OWNED_BY UNKNOWN until evidence establishes ownership

### Current Violation

**Every entity is assigned to exactly ONE team** in `graph_entity_meta.team_id`.

Evidence from the production database:
- Zero systems have more than 1 team in `graph_entity_meta`
- The `SmartEntityExtractor` receives a single `team_id` parameter (from `OrgMap.classify_document()`) and assigns it to ALL entities extracted from that document
- Document entity → OWNED_BY → single TEAM entity
- System entities inherit the document's team via `_make_entity(team_id=...)`

### Impact

When SPM documents mention "G3 RMS" AND ICS documents mention "G3 RMS":
- SPM document creates `SYS-G3-RMS` with `team_id=spm`
- ICS document's `SYS-G3-RMS` is **deduplicated** (same ID), so the ICS team association is **lost**
- The graph claims G3 RMS is only owned by SPM

### Root Cause

`SmartEntityExtractor._make_entity()` assigns `team_id` from the document's classification. When the same entity ID is deduplicated, the new evidence replaces old metadata via `ON CONFLICT ... DO UPDATE SET team_id = COALESCE(excluded.team_id, existing_team_id)`. Since `excluded.team_id` is always non-null (from the document), the last document processed wins.

### Smallest Safe Correction

**Option A (minimal)**: Change the upsert to accumulate team_ids as a list:
```sql
-- Instead of overwriting team_id, append to a JSON array
-- Requires schema change to graph_entity_meta.team_ids JSON array
```

**Option B (no schema change)**: Stop assigning team_id to extracted entities (systems, processes, etc.). Only assign team_id to the DOCUMENT entity. Let SYSTEM entities be team-neutral. Relationships carry the team context:
- `DOC-xxx` → `TEAM-spm` (OWNED_BY)
- `DOC-xxx` → `SYS-G3-RMS` (USES)
- `DOC-yyy` → `TEAM-ics` (OWNED_BY)
- `DOC-yyy` → `SYS-G3-RMS` (USES)
- Result: G3 RMS has NO exclusive team owner. Its team associations come from which documents reference it and which teams own those documents.

**Recommended: Option B** — no schema change, just remove `team_id` from non-document entity creation.

---

## 5. Bugs & Design Gaps

### Bugs

| # | Module | Issue | Severity |
|---|--------|-------|----------|
| 1 | `GlossaryManager._store_unknown_terms()` | `occurrence_count - 1` update is wrong — always adds 0 when term is new | Low |
| 2 | `GraphIndexer` | Did not complete full 483-doc indexing (timed out at ~312) | Medium |
| 3 | `SmartEntityExtractor` | Forces single-team ownership on shared entities | High |
| 4 | `OpportunityDetector` | Reads from `opportunity_events`, not `enterprise_events` — two separate stores | High |
| 5 | `EventBus` | Events never flow into graph or opportunity engine | High |

### Design Gaps

| # | Gap | Impact | Fix Complexity |
|---|-----|--------|---------------|
| 1 | No embedding generation in ingestion pipeline | RAG retrieval quality unknown | Low — call embedding service after chunking |
| 2 | SEAL has never been run | Glossary is empty, no human learning loop | Low — just needs one run |
| 3 | No real enterprise connectors | Event Bus is architecturally complete but has no data | Medium — needs connector implementations |
| 4 | Agent Registry is empty | No agents registered, SANJAYA is the only agent | Low — register SANJAYA |
| 5 | CrossVerifier not wired into HybridRetriever | Only BM25+Vector used at query time | Low — add strategy dispatch |
| 6 | RAG feedback loop has 0 entries | SelfRecommender has no signal to analyze | Low — needs usage |

---

## 6. Minimal Corrections Required

### Critical (must fix for valid knowledge loop)

1. **Wire Event Bus → Opportunity Engine**: Make `OpportunityDetector` read from `enterprise_events` (or merge the two tables).

2. **Fix multi-team entity ownership**: Stop assigning `team_id` to non-document entities. Let team associations derive from document→entity relationships.

### Important (should fix before Phase 3)

3. **Complete graph indexing**: Run `graph_indexer` to completion for all 483 documents.

4. **Wire CrossVerifier into HybridRetriever**: Enable multi-strategy retrieval.

5. **Run SEAL once**: Generate initial glossary entries from existing unknown terms.

### Nice-to-have

6. Register SANJAYA in the Agent Registry.
7. Add embedding generation to the ingestion pipeline.
8. Wire events into SANJAYA for real-time awareness.

---

## 7. Connector Readiness

### Event Bus as the common layer

The `EventBus` + `EventNormalizer` already support 7 source systems:

| System | Normalizer Method | Status |
|--------|------------------|--------|
| Datadog | `normalize_datadog()` | Ready |
| Salesforce | `normalize_salesforce()` | Ready |
| Confluence | `normalize_confluence()` | Ready |
| Teams | `normalize_teams()` | Ready |
| Outlook | `normalize_outlook()` | Ready |
| SQL | `normalize_sql()` | Ready |
| Smartsheet | `normalize_smartsheet()` | Ready |
| Internal | `normalize_generic()` | Ready (fallback) |

Each normalizer maps raw data → canonical `Event` model → `EventBus.ingest()`.

### What's missing for each connector

| Connector | Missing |
|-----------|---------|
| Datadog | HTTP client, auth config, polling/webhook |
| Salesforce | OAuth2, SOQL query builder |
| Confluence | REST client, space/page mapper |
| Teams | Graph API auth, message parser |
| Outlook | Exchange API, mailbox config |
| SQL | Connection pool, schema inspector |
| Smartsheet | API client, sheet mapper |

### The Event → Opportunity gap

Currently: `enterprise_events` (Event Bus) ≠ `opportunity_events` (Opportunity Engine)

These are separate tables with separate schemas. The fix is to make `OpportunityDetector.run()` accept events from the `enterprise_events` table, or pipe events from `EventBus` into `OpportunityRepository` automatically.

---

## 8. Agent Readiness

### Current agent infrastructure

```python
# AgentRegistration dataclass already has:
agent_id, name, description, role, status, domain, team_owner,
capabilities, knowledge_scope, version, parent_agent
```

The `AgentRegistry` already supports:
- Registration with capabilities and knowledge scope
- Lifecycle management (created → training → active → deprecated)
- Query routing to active agents by domain

### Future contract (already modeled)

```python
@dataclass
class AgentRegistration:
    agent_id: str          # unique identifier
    name: str              # human-readable name
    description: str       # what the agent does
    role: AgentRole        # planner|specialist|monitor|learner|retriever
    status: AgentStatus    # created|training|active|paused|deprecated
    domain: str            # e.g., "spm", "installation"
    team_owner: str        # organizational team
    capabilities: list[AgentCapability]  # what it can do
    knowledge_scope: list[str]  # document types it can access
    version: str           # semver
    parent_agent: str      # SANJAYA for all workers
```

### Smallest extension needed

The `agent_registry` table already has all required columns. A developer could register an independent agent with:

```python
from kurukshetra.agent.registry import AgentRegistry, AgentRole, AgentCapability

registry = AgentRegistry()
registry.register(
    agent_id="spm-installer",
    name="SPM Installation Agent",
    description="Handles property installation procedures",
    role=AgentRole.SPECIALIST,
    domain="spm-installation",
    team_owner="spm",
    capabilities=[AgentCapability(name="property-installation", ...)],
    knowledge_scope=["installation", "property-setup"],
    parent_agent="sanjaya",
)
registry.update_status("spm-installer", AgentStatus.ACTIVE)
```

No new code needed for agent registration — just use the existing API.

---

## 9. Knowledge Loop Diagram

```
                    +-----------------+
                    |  External Data  |
                    | (future: 7 src) |
                    +--------+--------+
                             |
                             v
                    +--------+--------+
                    |   Event Bus     |  <-- Common ingestion layer
                    | (enterprise_    |      Deduplicates, normalizes
                    |  events)        |
                    +--+-----+-----+--+
                       |     |     |
            +----------+     |     +----------+
            v                v                v
    +-------+-------+ +-----+------+ +------+------+
    |  Graph Update  | | Opportunity| | SANJAYA     |
    | (entities from | | Engine     | | (real-time) |
    |  events)       | | (patterns) | +------+------+
    +-------+-------+ +-----+------+        |
            |                |               |
            v                v               v
    +-------+----------------+---------------+------+
    |              Knowledge Graph                    |
    |  (4,742 entities, 24,916 relationships)        |
    |  + Evidence (11,319 records)                    |
    |  + Teams (7 represented)                        |
    +-------------------------+----------------------+
                              |
            +-----------------+-----------------+
            |                                   |
            v                                   v
    +-------+-------+               +-----------+-----------+
    | RAG Retrieval  |               |  SANJAYA Answering   |
    | BM25 + Vector  |               |  Evidence-backed     |
    | + Reranker     |               |  Multi-team aware    |
    +-------+-------+               +-----------+-----------+
            |                                   |
            v                                   v
    +-------+-------+               +-----------+-----------+
    | User Feedback  |               | SEAL Learning         |
    | (rag_feedback) |               | Unknowns → Glossary   |
    +-------+-------+               +-----------+-----------+
            |                                   |
            v                                   v
    +-------+-------+               +-----------+-----------+
    | Score Adjust   |               | Human Decisions       |
    | SelfRecommender|               | (seal_decisions)      |
    +----------------+               +-----------------------+
```

### What IS connected (implemented)

1. **Document → Registration → Chunking → Graph** (IngestionPipeline)
2. **Document → Team Classification** (TeamClassifier + OrgMap)
3. **Document → Unknown Term Detection** (GlossaryManager)
4. **Graph: Entity extraction + Evidence + Deduplication** (SmartEntityExtractor)
5. **Graph: Traversal, Pathfinding, Impact, Communities** (TraversalEngine)
6. **RAG: BM25 + Vector + Reranker** (HybridRetriever + BGEReranker)
7. **Event normalization for 7 systems** (EventNormalizer)
8. **Opportunity detection from events** (OpportunityDetector)
9. **Feedback → Score adjustment** (FeedbackLoop)
10. **SEAL: Load unknowns → Show evidence → Store decisions** (InterviewSession)

### What is DISCONNECTED

1. **Event Bus → Graph** — Events don't update entities
2. **Event Bus → Opportunity Engine** — Separate tables
3. **Event Bus → SANJAYA** — SANJAYA can't see real-time events
4. **Embedding generation → Ingestion Pipeline** — Vectors exist but aren't generated during ingest
5. **CrossVerifier → HybridRetriever** — CrossVerifier exists but isn't used at query time
6. **Glossary → RAG** — Confirmed terms don't boost retrieval
7. **SEAL decisions → Graph** — Confirmed definitions don't enrich entities
8. **Unknown terms → SEAL** — No terms detected (KNOWN_TERMS too broad)
9. **Multi-team ownership** — Graph forces single-team on shared entities

---

## 10. Recommended Next Milestone

**Mission 3.0A: Close the Knowledge Loop**

Priority order:
1. Fix Event Bus → Opportunity Engine connection (merge event stores)
2. Fix multi-team entity ownership (team-neutral entities)
3. Wire CrossVerifier into HybridRetriever
4. Run SEAL to populate initial glossary
5. Complete graph indexing for all 483 documents

This establishes a working baseline before adding the React Command Center UI.
