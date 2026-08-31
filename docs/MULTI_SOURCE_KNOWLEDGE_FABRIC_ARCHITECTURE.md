# Multi-Source Knowledge Fabric Architecture
## SANJAYA/Kurukshetra — Architecture Audit & Design

**Date:** August 31, 2026
**Status:** READ-ONLY AUDIT — No code changes
**Author:** Buffy (Codebuff agent)

---

## EXECUTIVE SUMMARY

SANJAYA already has a **well-designed but partially wired** multi-source architecture. The foundation is stronger than expected:

- A generic `SourceAdapter` contract exists with `SourceDocument`, `SourceIdentity`, `DocumentProvenance`, `SourceCursor`, `SourceCapability`, and `SourceHealth`
- A `SourceAdapterRegistry` manages adapter lifecycle
- A production `SalesforceAdapter` implements the full contract with incremental sync, retry, pagination, and deletion detection
- `KnowledgeFabric` bridges adapters to the canonical ingestion pipeline via `ingest_source_document()`
- Cursor management for incremental sync is persisted in DuckDB
- Entity quality gating, claim verification, evidence sufficiency, and visibility filtering are operational

**Key gaps are not missing abstractions — they are missing wiring, missing adapters, and missing source-level authority tracking.**

---

## 1. CURRENT CAPABILITY MATRIX

### 1.1 Source Adapter Foundation (`kurukshetra/sources/`)

| Capability | Status | Evidence |
|-----------|--------|----------|
| SourceAdapter ABC | IMPLEMENTED + VERIFIED | `sources/adapter.py` — abstract `identify()`, `discover()`, `health()` |
| SourceDocument model | IMPLEMENTED + VERIFIED | `sources/models.py` — full provenance, team, visibility, metadata |
| DocumentProvenance | IMPLEMENTED + VERIFIED | `sources/models.py` — source_id, external_id, content_hash, version_tag, trust_level |
| SourceCursor | IMPLEMENTED + VERIFIED | `sources/models.py` — cursor_type, cursor_value, items_processed |
| SourceCapability | IMPLEMENTED + VERIFIED | `sources/models.py` — discovery, incremental, deletion, versioning, teams, visibility |
| SourceHealth | IMPLEMENTED + VERIFIED | `sources/models.py` — healthy, last_error, documents_total/fresh/stale |
| SourceIdentity | IMPLEMENTED + VERIFIED | `sources/models.py` — source_id, source_type, display_name, owner_team, config |
| SourceType enum | IMPLEMENTED | filesystem, network_share, salesforce, confluence, datadog, sql, teams, outlook, github, custom |
| SourceAdapterRegistry | IMPLEMENTED + VERIFIED | `sources/registry.py` — register, unregister, health_all, list_sources |
| SalesforceAdapter | IMPLEMENTED + VERIFIED | Production adapter with retry, pagination, incremental sync, deletion detection |

### 1.2 Knowledge Fabric (`kurukshetra/knowledge/fabric.py`)

| Capability | Status | Evidence |
|-----------|--------|----------|
| Document state tracking | IMPLEMENTED + VERIFIED | `document_state` table — NEW/REGISTERED/INDEXED/CHANGED/REMOVED/CONFLICT/STALE |
| SHA-256 change detection | IMPLEMENTED + VERIFIED | `scan_source()` computes SHA-256 per file |
| Incremental ingestion | IMPLEMENTED + VERIFIED | `ingest_change()` handles NEW/CHANGED/REMOVED |
| Version tracking | IMPLEMENTED + VERIFIED | `document_versions` table with version bumping |
| Multi-team concept tracking | IMPLEMENTED + PARTIAL | `concept_teams` table — populated but limited evidence backing |
| Conflict detection | IMPLEMENTED + PARTIAL | `knowledge_conflicts` table — TEAM_MISMATCH only, no content contradiction |
| Source adapter bridge | IMPLEMENTED + VERIFIED | `ingest_source_document()` bridges SourceDocument to pipeline |
| Source cursor management | IMPLEMENTED + VERIFIED | `load_source_cursor()` / `save_source_cursor()` |
| Fabric scan history | IMPLEMENTED | `fabric_scans` table tracks scan metadata |
| Deletion handling | IMPLEMENTED + VERIFIED | `_handle_removed()` deletes chunks, marks state REMOVED |

### 1.3 Graph (`kurukshetra/graph/`)

| Capability | Status | Evidence |
|-----------|--------|----------|
| Entity storage | IMPLEMENTED + VERIFIED | `graph_entities` table with quality_score |
| Relationship storage | IMPLEMENTED + VERIFIED | `graph_relationships` table |
| Entity quality scoring | IMPLEMENTED + VERIFIED | Mission 3.56C quality gate at ingestion |
| Evidence tracking | IMPLEMENTED + VERIFIED | `graph_evidence` table |
| Graph traversal | IMPLEMENTED + VERIFIED | `get_neighbors()` returns relationships |

### 1.4 Agent/Orchestration (`kurukshetra/agent/`)

| Capability | Status | Evidence |
|-----------|--------|----------|
| Agentic orchestrator | IMPLEMENTED + VERIFIED | Bounded iterative retrieval (max 2 rounds) |
| Evidence sufficiency gate | IMPLEMENTED + VERIFIED | V2 with semantic match, topic coverage |
| Evidence claim verifier | IMPLEMENTED + VERIFIED | DIRECT/INFERRED/UNSUPPORTED classification |
| Answer generator (GX10) | IMPLEMENTED + VERIFIED | LLM synthesis with extractive fallback |
| Multi-document synthesis | IMPLEMENTED + PARTIAL | Basic evidence aggregation |

### 1.5 Security (`kurukshetra/security/`, `kurukshetra/retrieval/access_control.py`)

| Capability | Status | Evidence |
|-----------|--------|----------|
| Visibility levels | IMPLEMENTED + VERIFIED | PUBLIC < INTERNAL < CONFIDENTIAL < RESTRICTED |
| VisibilityFilter | IMPLEMENTED + VERIFIED | Document-level filtering at retrieval time |
| Identity provider | IMPLEMENTED + VERIFIED | Entra, Local, Mock providers |
| AuthorizationContext | IMPLEMENTED + VERIFIED | Identity → max_visibility → filter |
| Memory isolation | IMPLEMENTED + VERIFIED | Per-user episodic memory |

### 1.6 Memory (`kurukshetra/agent/memory_store.py`)

| Capability | Status | Evidence |
|-----------|--------|----------|
| Working memory | IMPLEMENTED + PARTIAL | In-memory state, not persisted |
| Episodic memory | IMPLEMENTED + VERIFIED | DuckDB persistence, feedback recording |
| Semantic memory | IMPLEMENTED + PARTIAL | Wraps graph, limited query interface |
| Procedural memory | IMPLEMENTED + PARTIAL | Table exists, extraction not wired |
| Prospective memory | IMPLEMENTED + VERIFIED | Reminder detection and task storage |
| Knowledge source attribution | IMPLEMENTED | KnowledgeSource enum with ORGANIZATION/CONVERSATION/PROCEDURE/etc |

### 1.7 Watcher/Background Sync (`kurukshetra/runtime/`)

| Capability | Status | Evidence |
|-----------|--------|----------|
| WatcherManager | IMPLEMENTED + VERIFIED | Background polling thread with configurable interval |
| KnowledgeWatcher | IMPLEMENTED + VERIFIED | Filesystem scan and ingest |
| InboxWatcher | IMPLEMENTED | Watches upload inbox |

---

## 2. ARCHITECTURE GAPS

### 2.1 Source Registry Gaps

| Gap | Severity | Impact |
|-----|----------|--------|
| No source_authority table | HIGH | Cannot distinguish authoritative docs from observations |
| No source sync schedule | MEDIUM | No hourly/daily/event-driven sync configuration |
| No source sync state table | HIGH | Cannot track last_sync, sync_status, error_count per source |
| SourceAdapterRegistry is in-memory only | MEDIUM | Lost on restart; no persistence of registered sources |
| No source-specific visibility | MEDIUM | All documents from a source get same visibility |
| No source-specific team scope | LOW | Team detection is document-level, not source-level |

### 2.2 Authority/Provenance Gaps

| Gap | Severity | Impact |
|-----|----------|--------|
| No authority_level on documents | HIGH | Cannot rank official SOP > email > user upload |
| No authority hierarchy defined | HIGH | No precedence when sources conflict |
| trust_level on Provenance is unused | MEDIUM | "observed/candidate/confirmed" never enforced |
| No process drift detection | MEDIUM | Cannot detect when SOP says X but cases show Y |

### 2.3 Conflict/Process-Drift Gaps

| Gap | Severity | Impact |
|-----|----------|--------|
| Only TEAM_MISMATCH conflict type | MEDIUM | No CONTENT_CONTRADICTION or PROCESS_DRIFT |
| No cross-source conflict detection | HIGH | Salesforce vs Confluence contradictions invisible |
| No temporal conflict detection | MEDIUM | Cannot detect when procedures changed over time |
| Conflict resolution is manual only | LOW | No automatic precedence resolution |

### 2.4 Deletion/Freshness Gaps

| Gap | Severity | Impact |
|-----|----------|--------|
| Deletion works but no stale detection | MEDIUM | Documents not refreshed go stale silently |
| No freshness scoring | MEDIUM | Cannot prioritize recent over old documents |
| No cross-source deduplication | MEDIUM | Same doc on Confluence + filesystem = duplicate |
| No "last verified" timestamp | LOW | Cannot track when a document was last confirmed current |

### 2.5 Agent-to-Kurukshetra Gaps

| Gap | Severity | Impact |
|-----|----------|--------|
| No agent identity model | MEDIUM | Future agents cannot authenticate as agents |
| No agent capability declaration | LOW | Cannot discover what an agent can do |
| No agent-to-agent communication | LOW | Future A2A not architecturally blocked but not designed |

---

## 3. PROPOSED SOURCE REGISTRY MODEL

### 3.1 New DuckDB Table: `source_registry`

```sql
CREATE TABLE IF NOT EXISTS source_registry (
    source_id       TEXT PRIMARY KEY,
    source_type     TEXT NOT NULL,           -- filesystem, salesforce, confluence, etc.
    display_name    TEXT NOT NULL,
    description     TEXT DEFAULT '',
    owner_team      TEXT DEFAULT '',         -- team responsible for this source
    
    -- Authority
    authority_level TEXT DEFAULT 'observed', -- official | validated | observed | user_provided
    trust_score     DOUBLE DEFAULT 0.5,     -- 0.0 to 1.0
    
    -- Visibility default for documents from this source
    default_visibility TEXT DEFAULT 'Internal',
    
    -- Sync configuration
    sync_mode       TEXT DEFAULT 'manual',  -- manual | polling | event_driven | webhook
    sync_interval_s INTEGER DEFAULT 3600,   -- polling interval in seconds
    enabled         BOOLEAN DEFAULT TRUE,
    
    -- Sync state
    last_sync_at    TIMESTAMP,
    last_sync_status TEXT DEFAULT 'never',  -- never | success | partial | error
    last_error      TEXT DEFAULT '',
    consecutive_errors INTEGER DEFAULT 0,
    total_documents INTEGER DEFAULT 0,
    
    -- Provenance
    config_json     TEXT DEFAULT '{}',      -- non-secret config (JSON)
    created_at      TIMESTAMP,
    updated_at      TIMESTAMP
);
```

### 3.2 New DuckDB Table: `source_sync_log`

```sql
CREATE TABLE IF NOT EXISTS source_sync_log (
    log_id          TEXT PRIMARY KEY,
    source_id       TEXT NOT NULL,
    started_at      TIMESTAMP,
    completed_at    TIMESTAMP,
    status          TEXT,                    -- success | partial | error
    documents_found INTEGER DEFAULT 0,
    documents_new   INTEGER DEFAULT 0,
    documents_changed INTEGER DEFAULT 0,
    documents_removed INTEGER DEFAULT 0,
    documents_errored INTEGER DEFAULT 0,
    error_message   TEXT DEFAULT '',
    duration_ms     DOUBLE DEFAULT 0.0
);
```

### 3.3 New DuckDB Table: `document_authority`

```sql
CREATE TABLE IF NOT EXISTS document_authority (
    document_id         TEXT PRIMARY KEY,
    source_id           TEXT NOT NULL,
    authority_level     TEXT NOT NULL,      -- official | validated | observed | user_provided
    authority_evidence  TEXT DEFAULT '',    -- why this authority level
    last_verified_at    TIMESTAMP,
    expires_at          TIMESTAMP,          -- optional expiration
    FOREIGN KEY (source_id) REFERENCES source_registry(source_id)
);
```

---

## 4. PROPOSED CONNECTOR INTERFACE

The existing `SourceAdapter` contract is **already correct and sufficient**. The gaps are in how adapters are registered and how their output flows through authority tracking.

### 4.1 Enhanced Adapter Lifecycle

```
1. register(adapter)
   → adapter.identify() → SourceIdentity
   → adapter.setup()
   → INSERT INTO source_registry

2. sync(source_id)
   → adapter.discover(cursor) → Iterator[SourceDocument]
   → For each SourceDocument:
       → KnowledgeFabric.ingest_source_document(doc)
       → INSERT INTO document_authority (authority from source_registry)
   → UPDATE source_registry SET last_sync_at, last_sync_status
   → INSERT INTO source_sync_log

3. health(source_id)
   → adapter.health() → SourceHealth
   → UPDATE source_registry.last_error if unhealthy

4. unregister(source_id)
   → adapter.teardown()
   → UPDATE source_registry SET enabled = FALSE
```

### 4.2 Future Connector Contracts

Each future connector implements the same `SourceAdapter` ABC:

| Connector | SourceType | Incremental | Deletion | Versioning | Teams | Visibility |
|-----------|-----------|-------------|----------|------------|-------|------------|
| Filesystem/Network Share | filesystem/network_share | mtime-based | Yes | Content hash | Path-based | Config |
| Salesforce | salesforce | SystemModstamp | Yes | Yes | Field-based | Status |
| Confluence | confluence | last-modified | Yes | Version number | Space-based | Space perms |
| Datadog | datadog | Event timestamp | No | No | Tag-based | Role-based |
| GitHub | github | Commit SHA | Yes | Commit history | Team-based | Repo perms |
| Mail (SPM/ICS) | outlook | IMAP UID/Date | No | No | Address-based | Config |
| User uploads | filesystem | Immediate | Manual | Content hash | User-based | User-scoped |
| Future agents | custom | Agent-defined | Agent-defined | Agent-defined | Agent-owned | Agent-scoped |

---

## 5. SYNCHRONIZATION LIFECYCLE

### 5.1 Sync Modes

| Mode | Trigger | Use Case |
|------|---------|----------|
| `manual` | User/API trigger | Initial ingestion, ad-hoc refresh |
| `polling` | WatcherManager interval | Filesystem, network share |
| `event_driven` | Webhook/callback | Salesforce, GitHub |
| `immediate` | On upload | User-uploaded documents |

### 5.2 Incremental Sync Flow

```
SOURCE SYSTEM
    ↓
adapter.discover(cursor)
    ↓
SourceDocument (with DocumentProvenance)
    ↓
KnowledgeFabric.ingest_source_document(doc)
    ↓
  ┌─ Dedup by content_hash → skip if unchanged
  ├─ Extract text → chunk → embed
  ├─ Entity extraction → quality gate → graph
  ├─ Document state → document_state table
  ├─ Version tracking → document_versions table
  ├─ Authority tracking → document_authority table
  ├─ Team tracking → concept_teams table
  └─ Conflict detection → knowledge_conflicts table
    ↓
adapter saves cursor → source_cursors table
    ↓
source_sync_log records outcome
```

### 5.3 Deletion Handling

```
Source adapter detects deletion:
  → Yields SourceDocument with status="deleted"
    ↓
KnowledgeFabric.ingest_source_document(doc):
  → Finds existing document by external_id
  → _handle_removed():
      → DELETE FROM chunks WHERE document_id = ?
      → DELETE FROM vectors WHERE chunk_id IN (...)
      → UPDATE document_state SET state = 'removed'
      → UPDATE document_versions SET is_current = FALSE
      → UPDATE document_authority SET expires_at = NOW
    ↓
Document is no longer retrievable
    ↓
Source cursor records deletion
```

### 5.4 Stale Detection (Proposed)

```
WatcherManager._poll_loop():
    → For each enabled source with sync_mode='polling':
        → Check: last_sync_at + sync_interval_s < NOW?
        → If yes: trigger sync
    → For ALL indexed documents:
        → If last_ingested < freshness_threshold:
            → Mark as STALE in document_state
            → Include in knowledge state freshness_summary
    → For documents from deleted/removed sources:
        → Schedule graceful degradation (don't immediately delete)
```

---

## 6. AUTHORITY / PROVENANCE MODEL

### 6.1 Authority Hierarchy

```
HIERARCHY (highest to lowest):

1. OFFICIAL      — Authoritative organizational documentation
                  (approved SOPs, official process docs, signed procedures)
                  Source: ICS/SPM/SDOPS official doc repos

2. VALIDATED     — System records confirmed by organizational process
                  (Salesforce Knowledge articles, JIRA resolved items)
                  Source: Salesforce, system of record

3. OBSERVED      — Operational observations and records
                  (Datadog events, email threads, chat logs)
                  Source: Monitoring, communication

4. USER_PROVIDED — User-uploaded or user-contributed knowledge
                  (Uploaded files, user corrections, feedback)
                  Source: User uploads, feedback

5. INFERRED      — Derived from other knowledge (graph relationships)
                  Source: Kurukshetra inference engine
```

### 6.2 Authority Rules

```
RULE 1: Higher authority always wins for factual questions
  OFFICIAL > VALIDATED > OBSERVED > USER_PROVIDED > INFERRED

RULE 2: Authority is per-claim, not per-document
  A single document may contain claims at different authority levels

RULE 3: Multiple sources at same authority → corroborate
  Two OFFICIAL sources saying the same thing → higher confidence

RULE 4: Conflicting sources → surface the conflict
  OFFICIAL says X, OBSERVED says Y → present both with authority labels

RULE 5: USER_PROVIDED never silently overwrites OFFICIAL
  User upload saying "procedure is X" does NOT override official SOP

RULE 6: Authority degrades over time
  Documents not verified within freshness_window lose authority
```

### 6.3 Provenance Chain

Every answer must trace back:

```
ANSWER CLAIM
  → Evidence chunks
    → Source documents
      → Source adapters
        → Source systems
          → Authority levels
            → Verification timestamps
```

---

## 7. CONFLICT / PROCESS-DRIFT MODEL

### 7.1 Conflict Types

| Type | Description | Detection |
|------|-------------|-----------|
| TEAM_MISMATCH | Entity associated with different teams | Already implemented |
| VERSION_CONFLICT | Same document, different versions | Already implemented |
| CONTENT_CONTRADICTION | Two documents state conflicting facts | Not yet implemented |
| PROCESS_DRIFT | Official procedure differs from observed practice | Not yet implemented |
| AUTHORITY_CONFLICT | Higher-authority source contradicts lower | Not yet implemented |

### 7.2 Process Drift Detection

```
For a given process/procedure:
  1. Find OFFICIAL documents describing the procedure
  2. Find OBSERVED/VALIDATED records of how the procedure is actually performed
  3. Compare:
     - If official and observed agree → no drift
     - If official says X but observations show Y → flag PROCESS_DRIFT
     - If observations show Z that isn't in any official doc → flag UNDOCUMENTED_PRACTICE
  4. Surface drift to user as:
     "Official procedure says X (Source A, 2024).
      Recent cases indicate Y may be occurring instead (Source B, 2026).
      This may indicate process drift."
```

### 7.3 Conflict Resolution (Future)

Conflicts should NOT be auto-resolved. Instead:

```
1. Detect conflict → store in knowledge_conflicts
2. Classify by severity:
   - LOW: Different teams reference same concept (normal)
   - MEDIUM: Different versions of same document
   - HIGH: Content contradictions on same procedure
   - CRITICAL: Authority conflict (official vs observed)
3. Surface to user with full provenance
4. Allow manual resolution: mark which source is authoritative
5. Record resolution for future reference
```

---

## 8. SECURITY MODEL FOR MULTI-SOURCE RETRIEVAL

### 8.1 Current Architecture (Verified)

```
User Request
  → IdentityProvider.authenticate(token) → AuthenticatedIdentity
  → AuthorizationContext(identity) → max_visibility
  → VisibilityFilter(max_level) → filters retrieval results
  → EvidenceSufficiencyGate → validates evidence
  → EvidenceClaimVerifier → classifies claims
  → Answer generation → cites only authorized evidence
```

### 8.2 Multi-Source Security Requirements

| Requirement | Current Status | Gap |
|------------|---------------|-----|
| Source-level access control | NOT IMPLEMENTED | All sources visible to all users |
| Per-source team scope | NOT IMPLEMENTED | No source→team restriction |
| Document visibility from source | IMPLEMENTED | SourceDocument.visibility → documents.visibility |
| Retrieval-time filtering | IMPLEMENTED | VisibilityFilter works |
| Evidence authorization | IMPLEMENTED | Only authorized evidence reaches verifier |
| Cross-source authorization | NOT IMPLEMENTED | No per-source authorization check |
| User-uploaded doc isolation | PARTIAL | User uploads get default visibility |
| Agent identity scoping | NOT IMPLEMENTED | No agent identity model |

### 8.3 Proposed: Source-Level Authorization

```sql
CREATE TABLE IF NOT EXISTS source_access (
    source_id       TEXT NOT NULL,
    principal_type  TEXT NOT NULL,     -- user | group | role | agent
    principal_id    TEXT NOT NULL,     -- user_id, group_name, role_name, agent_id
    max_visibility  TEXT DEFAULT 'Internal',
    PRIMARY KEY (source_id, principal_type, principal_id)
);
```

At retrieval time:
```
1. Get user's authorized sources (from source_access)
2. Filter retrieval results to only authorized sources
3. Apply visibility filtering as today
4. Evidence reaching verifier is already authorized
```

---

## 9. FUTURE AGENT-TO-KURUKSHETRA MODEL

### 9.1 Agent Identity

```
AGENT PRINCIPAL:
  agent_id        TEXT          -- unique agent identifier
  agent_type      TEXT          -- team_agent | system_agent | connector_agent
  owner_team      TEXT          -- team that owns/operates this agent
  display_name    TEXT
  capabilities    TEXT[]        -- what the agent can do
  knowledge_scope TEXT[]        -- what knowledge the agent can access
  trust_level     TEXT          -- same authority hierarchy as sources
  created_at      TIMESTAMP
  last_active     TIMESTAMP
```

### 9.2 Agent → Kurukshetra Flow

```
AGENT (e.g., ICS Agent)
  → Authenticates as agent identity
  → Declares capabilities: ["ics_documents", "installation_procedures"]
  → Contributes knowledge:
      → SourceDocument with agent_id in provenance
      → Authority = agent's trust_level
      → Visibility = agent's knowledge_scope
  → Consumes knowledge:
      → Retrieves only within agent's knowledge_scope
      → All retrievals logged with agent_id
      → Provenance traces to agent identity
```

### 9.3 Agent Provenance

```
ANSWER PROVENANCE WITH AGENT CONTRIBUTION:

Claim: "G3 installation requires步骤1, 2, 3"
  → Evidence from: ICS Agent (agent_id: agent-ics-001)
  → Source document: ICS Installation Guide
  → Authority: validated (agent is trusted for ICS knowledge)
  → Agent owner: ICS team
  → Last verified: 2026-08-15
```

---

## 10. CURRENT DOCUMENT FLOW (VERIFIED)

```
FILE UPLOAD / NETWORK SHARE / ADAPTER
    ↓
TextExtractor (PDF, DOCX, XLSX, CSV, TXT, MD, PPTX, HTML, JSON, XML)
    ↓
SemanticChunker (with WordPress artifact cleanup)
    ↓
IngestionPipeline
    → DocumentRegistrar.register() → document_id
    → Store chunks in DuckDB
    → BGE-M3 embedding → vectors table
    → BM25 index
    ↓
GraphRegistry.ingest_document()
    → Entity extraction
    → Quality gate (NOISE rejection)
    → Relationship extraction
    → Evidence tracking
    ↓
KnowledgeFabric
    → document_state tracking
    → document_versions tracking
    → concept_teams tracking
    → conflict detection
    ↓
RETRIEVAL (on query)
    → Hybrid search (BM25 + vector)
    → Feedback-aware boost
    → Visibility filter
    → Evidence sufficiency gate
    → Agentic refinement (bounded 2 rounds)
    → Evidence claim verification
    → GX10 synthesis (or extractive fallback)
    → Answer with citations + confidence + provenance
```

---

## 11. INCREMENTAL IMPLEMENTATION PLAN

### Phase 1: Source Registry Persistence (1-2 days)
- Add `source_registry` and `source_sync_log` tables
- Wire `SourceAdapterRegistry` to persist in DuckDB
- Add `/api/sources` endpoint listing registered sources
- **Value:** Sources survive restart, visible in UI

### Phase 2: Authority Tracking (1-2 days)
- Add `document_authority` table
- Add `authority_level` to `SourceDocument.provenance`
- Wire authority into evidence claim verification
- **Value:** Distinguish official docs from observations

### Phase 3: Source-Level Sync Scheduling (1 day)
- Add `sync_mode` and `sync_interval_s` to source registry
- Extend `WatcherManager` to support per-source polling
- Add manual trigger endpoint per source
- **Value:** Automated incremental sync

### Phase 4: Cross-Source Conflict Detection (2-3 days)
- Extend `detect_conflicts()` for CONTENT_CONTRADICTION
- Add process drift detection (official vs observed)
- Surface conflicts in UI with provenance
- **Value:** Detect when practice diverges from procedure

### Phase 5: Filesystem Adapter (1 day)
- Implement `FilesystemAdapter(SourceAdapter)` for network shares
- Use existing `KnowledgeFabric.scan_source()` logic
- Register `\\ina6fs01\Dept_shares` as source
- **Value:** Network share through generic adapter

### Phase 6: Source-Level Authorization (1 day)
- Add `source_access` table
- Filter retrieval by source authorization
- Wire into VisibilityFilter
- **Value:** Per-source access control

### Phase 7: Agent Identity Foundation (2-3 days)
- Add `agent_principals` table
- Extend IdentityProvider for agent identities
- Agent-provenanced document ingestion
- **Value:** Future A2A readiness

---

## 12. WHAT SANJAYA CAN vs CANNOT DO TODAY

### CAN DO
- Ingest documents from filesystem, network share, user upload, Salesforce (mock)
- Detect new/changed/removed documents via SHA-256
- Track document versions
- Extract entities with quality gating
- Track multi-team concept associations
- Retrieve via hybrid search (BM25 + vector)
- Filter by document visibility
- Verify evidence claims (DIRECT/INFERRED/UNSUPPORTED)
- Detect evidence sufficiency
- Synthesize multi-document answers with GX10
- Record user feedback
- Maintain episodic memory
- Detect knowledge conflicts (team mismatch only)
- Serve futuristic Knowledge Brain UI

### CANNOT DO (YET)
- Automatically sync from Salesforce/Confluence/Datadog (adapters exist but not registered)
- Distinguish authority levels between sources
- Detect process drift across sources
- Authorize by source (only by document visibility)
- Track source health over time
- Manage source-specific sync schedules
- Handle cross-source deduplication
- Support agent-to-Kurukshetra communication
- Resolve conflicts automatically
- Detect stale knowledge proactively

---

## 13. ANSWER TO FINAL QUESTIONS

### "How much of the enterprise knowledge that is ACTUALLY ACCESSIBLE can SANJAYA understand?"

**Currently:** SANJAYA has ingested ~750 documents from the filesystem and network share. The adapter architecture is ready for Salesforce, Confluence, Datadog, and GitHub — but no production adapters are registered. The constraint is not the architecture but the **lack of registered production sources**.

**Accessible coverage** (within what we can currently reach):
- Filesystem documents: ~95% indexed (those in watched directories)
- Network share (when accessible): ~114 documents indexed
- User uploads: 100% (immediate ingestion)
- Salesforce: 0% (adapter exists, mock only, no production config)
- Confluence: 0% (no adapter yet)
- Datadog: 0% (no adapter yet)
- GitHub: 0% (no adapter yet)
- Mail: 0% (no adapter yet)

### "If we removed GX10 and used only deterministic retrieval, what capabilities would remain?"

- Hybrid search (BM25 + vector)
- Entity-aware retrieval
- Graph-augmented retrieval
- Feedback-aware retrieval
- Visibility filtering
- Evidence sufficiency gating
- Claim verification (deterministic)
- Citing source documents
- Abstention on insufficient evidence
- Extractive answer fallback (key sentences)

**Lost:** Natural language synthesis, cross-document reasoning, nuanced explanation, conversation handling.

### "If we keep GX10 only as the reasoning/generation engine, what does Kurukshetra provide around it?"

Kurukshetra provides:
- **Retrieval** (what evidence to use)
- **Authorization** (what evidence the user can see)
- **Evidence selection** (which chunks are relevant)
- **Sufficiency gating** (whether evidence answers the question)
- **Claim verification** (whether the answer is supported)
- **Provenance** (where every fact came from)
- **Confidence calibration** (how trustworthy the answer is)
- **Abstention** (when to say "I don't know")
- **Memory** (what happened before)
- **Feedback** (what users found helpful)
- **Knowledge graph** (what's connected to what)
- **Multi-source management** (where knowledge comes from)

GX10 provides: language understanding, synthesis, explanation, conversation.

---

## 14. MATURITY ASSESSMENT

| Dimension | Level | Evidence |
|-----------|-------|----------|
| Knowledge Ingestion | 70% | Works for files; adapters ready but not registered |
| Retrieval | 75% | Hybrid + entity + feedback-aware; no cross-source ranking |
| Reasoning | 60% | Agentic with sufficiency gate; limited multi-hop |
| Grounding | 70% | Claim verifier operational; false direct rate ~10-15% |
| Security | 65% | Visibility works; no source-level auth |
| Memory | 40% | Episodic works; others are foundations |
| Multi-Source | 30% | Architecture ready; no production adapters registered |
| Self-Learning | 25% | Feedback recorded; retrieval boost wired; limited impact |
| Conflict Detection | 20% | Team mismatch only; no content/authority contradictions |
| Enterprise Readiness | 35% | UI works; auth works; but limited real sources |

**Overall Enterprise Readiness: ~45%**

The architecture is sound. The gap is in **wiring production sources** and **authority tracking**, not in missing abstractions.
