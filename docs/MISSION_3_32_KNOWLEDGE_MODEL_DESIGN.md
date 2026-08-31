# MISSION 3.32 — Knowledge Model Design

**Date:** August 28, 2026
**Test Baseline:** 546/546 pass
**Git HEAD:** 9deb5b5
**Network Share:** NOT ACCESSIBLE

---

## 1. Root Cause: Why concept_teams and document_versions Are Empty

### Evidence

| Table | Expected Records | Actual Records | Cause |
|---|---|---|---|
| document_state | 566 (all docs) | **0** | Documents ingested via `IngestionPipeline.ingest()`, not `KnowledgeFabric` |
| document_versions | 566 | **0** | Same — version tracking only in Fabric path |
| concept_teams | >0 | **0** | `_track_concepts()` only called from Fabric methods |
| fabric_scans | — | 6 | Watcher ran but didn't ingest through Fabric |

### Architecture Gap

```
CURRENT INGESTION PATH (used for all 566 documents):
  IngestionPipeline.ingest(file_path)
    → TextExtractor
    → DocumentRegistrar
    → TeamClassifier
    → Splitter
    → ChunkRepository
    → GraphRegistry
    → [DONE — no Fabric tracking]

FABRIC INGESTION PATH (never used for production docs):
  KnowledgeFabric.ingest_change(change)
    → IngestionPipeline.ingest()
    → document_state INSERT
    → document_versions INSERT
    → _track_concepts()
    → [Fabric tracking complete]
```

**The IngestionPipeline does not call KnowledgeFabric.** Documents go directly through the pipeline without Fabric's version tracking, concept-team mapping, or state management.

### Fix Required

The IngestionPipeline must notify KnowledgeFabric after successful ingestion, OR the Fabric must be the sole ingestion entry point. The smallest fix is to add Fabric tracking calls at the end of `IngestionPipeline.ingest()`.

---

## 2. Current Entity Inventory — What SANJAYA Actually Knows

### Reliable Entities (verified quality)

| Type | Count | Examples | Quality |
|---|---|---|---|
| **system** | 23 | G3 RMS, Opera Cloud, NGI, OHIP, FOLS, SFDC, Salesforce, Datadog | **GOOD** — all real systems |
| **team** | 7 | SPM, ICS, IT, ROA, SDOPS, HR, CPM | **GOOD** — all real teams |
| **property** | 19 | (mixed quality) | **PARTIAL** — some real, some fragments |

### Noise Entities (verified garbage)

| Type | Count | Examples | Problem |
|---|---|---|---|
| **knowledge_article** | 2,163 | "Chunk CH-000027", "Chunk CH-000028" | **GARBAGE** — chunk IDs treated as entities |
| **process** | 850 | "1 in the image above", "2 weeks", "500 Internal Server Error" | **GARBAGE** — sentence fragments from greedy regex |
| **job** | 220 | "Encoding", "attached", "file", "property" | **GARBAGE** — common words captured by `(\w+) job` pattern |
| **document** | 591 | Structural references | **NOISE** — not meaningful entities |
| **incident** | 213 | (mixed) | **PARTIAL** — some real incidents, some noise |
| **configuration** | 76 | "All", "Channel", "Data" | **NOISE** — single common words |

### Reliable Glossary Terms (35 confirmed)

Systems: AHWS, BMR, Channel Management Module, Data Feed, Decision File, GFT, Optix_1/2/3, RPM, TCPM, ngi-rra-internal, prod-cedf-g3-feeds-dashboard

Processes: Apply License, Continuous Pricing, Data Feed Configuration, Monitor Auto Processing, Post Data, Pricing Configuration, Pricing Troubleshooting, Rate Shopping, Rate Shopping Migration, Re-start, Related Salesforce Task, Switch Close Task, Vendor Integration

Configurations: Component Rooms, Exclude Room Types, Market Segment, Pricing Configuration, Room Types

People: Ajay Gandhi, Amol Bembde, Sharayu Abhang

Identifiers: Census Number

---

## 3. Canonical Organizational Knowledge Model

### 3.1 Entity Types (what should exist)

```
ORGANIZATIONAL ENTITIES
├── TEAM           — SPM, ICS, SDOPS, CPM, IT, HR, ROA
├── SYSTEM         — G3 RMS, Opera, NGI, OHIP, FOLS, SFDC, etc.
├── PROCESS        — Installation, Migration, Monitoring, Troubleshooting
├── PRODUCT        — G3 RMS, Opera Cloud, Demand360, RPM
├── CONFIGURATION  — STR, EDF, Room Types, Market Segment
├── PROPERTY       — Hotel/property codes and instances
├── PERSON         — Named individuals and roles
├── TEAM_CONCEPT   — Cross-team ownership (G3 → SPM + ICS)
└── DOCUMENT       — Source documents (for provenance only)
```

### 3.2 What Exists vs What Should Exist

| Entity Type | Current Count | Quality | Should Exist? | Action |
|---|---|---|---|---|
| system | 23 | Good | Yes | Keep, add missing (Demand360, RPM as system) |
| team | 7 | Good | Yes | Keep |
| process | 850 | Garbage | Yes (but different) | Replace with curated process entities |
| job | 220 | Garbage | No | Remove, replace with real job names |
| knowledge_article | 2,163 | Garbage | No | Remove entirely |
| document | 591 | Noise | No (provenance only) | Remove from graph, keep in documents table |
| incident | 213 | Mixed | Partially | Keep real incidents, remove noise |
| configuration | 76 | Noise | Yes (but different) | Replace with curated configurations |
| property | 19 | Mixed | Yes | Keep real properties, remove fragments |
| **PRODUCT** | 0 | — | Yes | Add: G3 RMS, Opera Cloud, Demand360, RPM, etc. |
| **TEAM_CONCEPT** | 0 | — | Yes | Add: G3→SPM+ICS, Opera→ICS, etc. |

---

## 4. Cross-Team Concept Model: G3 → SPM + ICS

### 4.1 Current State

G3 documents exist across 7 teams:
- SPM: 70 docs
- UNKNOWN: 57 docs
- IT: 31 docs
- ICS: 29 docs
- ROA: 15 docs
- SDOPS: 10 docs
- CPM: 4 docs

But `concept_teams` table is empty — the system cannot represent "G3 belongs to SPM and ICS."

### 4.2 Proposed Model

```
concept_teams table:
  concept_name: "G3 RMS"
  concept_type: "system"
  team_id: "SPM"
  association_type: "owner"
  confidence: 0.9
  source_document_id: "DOC-000498"
  first_seen: "2026-08-24"
  last_seen: "2026-08-28"

  concept_name: "G3 RMS"
  concept_type: "system"
  team_id: "ICS"
  association_type: "user"
  confidence: 0.7
  source_document_id: "DOC-000501"
  first_seen: "2026-08-24"
  last_seen: "2026-08-28"
```

### 4.3 How to Populate

For each entity in the graph:
1. Find all documents mentioning that entity
2. Look up each document's team_owner
3. Create a concept_team association for each team
4. Set association_type based on frequency:
   - Most frequent team → "owner"
   - 50-80% of frequency → "primary_user"
   - <50% → "associated"

### 4.4 What This Enables

- "Which teams work on G3?" → SPM (owner), ICS (user), IT (associated)
- "What systems does the ICS team manage?" → Opera, NGI, OHIP, G3
- "G3 belongs to which organizational contexts?" → SPM operations, ICS integration, SDOPS monitoring

---

## 5. Version/Temporal Knowledge Model

### 5.1 Current State

- `document_versions` table: 0 records
- `document_state` table: 0 records
- Documents ingested but not tracked for versions

### 5.2 Proposed Model

```
document_state table (per-document):
  document_id: "DOC-000498"
  source_path: "\\ina6fs01\...\G3 Data Feed Configuration.docx"
  sha256: "abc123..."
  file_size: 45000
  last_modified: "2026-03-15"
  last_ingested: "2026-08-24"
  state: "current"  (current | changed | removed | stale)
  version: "1.0.0"
  team_ids: '["SPM"]'

document_versions table (history):
  document_id: "DOC-000498"
  version: "1.0.0"
  sha256: "abc123..."
  ingested_at: "2026-08-24T10:00:00Z"
  source_path: "..."
  chunks_count: 5
  is_current: TRUE

  document_id: "DOC-000498"
  version: "1.0.1"
  sha256: "def456..."
  ingested_at: "2026-08-28T14:00:00Z"
  source_path: "..."
  chunks_count: 6
  is_current: TRUE
  (previous version marked is_current=FALSE)
```

### 5.3 What This Enables

- "When was this document last updated?" → version history
- "Is this current or historical?" → document_state.version
- "What changed between versions?" → SHA-256 comparison
- "Which documents are stale?" → last_ingested vs last_modified

### 5.4 How to Populate

1. On first ingestion: INSERT INTO document_state + document_versions (version 1.0.0)
2. On re-ingestion (content changed): UPDATE document_state (bump version), INSERT new document_versions, mark old as is_current=FALSE
3. On removal: UPDATE document_state SET state='removed'

---

## 6. How Knowledge Feeds Retrieval and Answer Generation

### 6.1 Current Flow (works today)

```
Query → SANJAYA Planner → HybridRetriever → AnswerGenerator → Answer + Citations
```

### 6.2 Enhanced Flow (with knowledge model)

```
Query
  → SANJAYA Planner (intent + team context)
  → Team-aware retrieval (boost documents from relevant teams)
  → HybridRetriever (BM25 + Vector)
  → VisibilityFilter (authorization)
  → AnswerGenerator (grounding + citations)
  → Provenance chain (source → document → chunk → entity → evidence)
  → Version awareness (prefer current, flag historical)
```

### 6.3 What Changes

| Component | Current | Enhanced |
|---|---|---|
| Retrieval | Flat BM25+Vector | Team-aware boosting |
| Grounding | Token + title alignment | + entity/team context |
| Citations | chunk + document | + team + version |
| Abstention | relevance threshold | + team context check |
| Answer | extractive sentences | + cross-document synthesis (future) |

---

## 7. Memory Architecture Mapping

| Memory Type | Status | Current Component | What's Needed | Milestone |
|---|---|---|---|---|
| **Working/In-context** | **PARTIAL** | ConversationMemory (20 turns) | + user context, session persistence | 3.33 |
| **Semantic** | **PARTIAL** | Glossary (35) + Graph (4K) | + entity quality fix, concept_teams, version tracking | 3.32 |
| **Episodic** | **PARTIAL** | FeedbackLoop | + per-user interaction log, answer history | 3.34 |
| **Procedural** | **MISSING** | OrgMap + AgentTemplates | + workflow extraction from docs | 3.35 |
| **External/Retrieval** | **VERIFIED** | 7 strategies, benchmarked | + team-aware retrieval | 3.32 |
| **Parametric** | **PARTIAL** | BGE embeddings | + domain fine-tuning (future) | 3.36 |
| **Prospective** | **MISSING** | OpportunityEngine (unused) | + temporal awareness | 3.37 |

---

## 8. Implementation Sequence (smallest changes, highest impact)

### Step 1: Wire IngestionPipeline → KnowledgeFabric (fixes empty tables)

**Change:** In `IngestionPipeline.ingest()`, after successful ingestion, call:
- `KnowledgeFabric._track_concepts()` for concept-team mapping
- `KnowledgeFabric` to create document_state and document_versions entries

**Impact:** concept_teams and document_versions populate automatically for all future ingestion.

**Risk:** Low — additive, no existing behavior changes.

### Step 2: Filter Noisy Graph Entities

**Change:** In `SmartEntityExtractor`, add minimum quality filters:
- Knowledge articles: don't extract "Chunk CH-XXX" as entities
- Processes: require 10+ chars, no digits-only, no common English words
- Jobs: require meaningful names, not single common words
- Configurations: require domain-specific context

**Impact:** Graph noise drops from ~3,400 noise entities to ~200 reliable entities.

**Risk:** Low — only affects entity extraction, not retrieval.

### Step 3: Populate concept_teams from Existing Documents

**Change:** Backfill script that:
1. For each entity in graph_entities
2. Find all documents mentioning it (via graph_evidence)
3. Look up document team_owner
4. Insert into concept_teams

**Impact:** G3→SPM+ICS, Opera→ICS, etc. become queryable.

**Risk:** Low — data-only, no behavior change.

### Step 4: Team-Aware Retrieval Boost

**Change:** In HybridRetriever, optionally boost documents from the same team as the query context.

**Impact:** Queries about SPM topics prefer SPM documents, reducing irrelevant results.

**Risk:** Medium — affects retrieval ranking, needs benchmark validation.

---

## 9. Decision Record

| Decision | Choice | Rationale |
|---|---|---|
| Entity types to keep | system, team, process (curated), configuration (curated), property | Only types with verified quality |
| Entity types to remove | knowledge_article, document, job (as currently extracted) | >95% noise |
| concept_teams population | Derived from document→entity→team provenance chain | Deterministic, no LLM needed |
| Version tracking | Populate on every ingestion through Fabric | Small change, high value |
| Team-aware retrieval | Optional boost, not mandatory filter | Preserves current behavior |
| LLM entity extraction | DEFER | Wait for 200+ documents, measure ROI first |

---

## 10. Files to Modify (when approved)

| File | Change | Risk |
|---|---|---|
| `kurukshetra/pipeline/ingest.py` | Add Fabric tracking calls after ingestion | Low |
| `kurukshetra/graph/extractor.py` | Add entity quality filters | Low |
| `kurukshetra/graph/builder.py` | Add entity quality filters | Low |
| `kurukshetra/knowledge/fabric.py` | Add backfill method for concept_teams | Low |
| `kurukshetra/retrieval/hybrid.py` | Add optional team-aware boost | Medium |

---

**No code changes. No commits. Design document complete. Awaiting approval.**
