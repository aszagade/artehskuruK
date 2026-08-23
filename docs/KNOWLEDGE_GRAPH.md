# Knowledge Graph

Entity-relationship graph that maps organizational knowledge beyond text chunks.

---

## Entity Types (12)

| Type | Example | Extracted By |
|------|---------|-------------|
| `document` | G3_RMS_Guide.pdf | Ingestion pipeline |
| `team` | SPM, ICS, SDOPS | OrgMap integration |
| `person` | (not yet extracted) | Future: NER |
| `client` | Marriott, Hilton | Filename + content patterns |
| `property` | JW Marriott NYC | Content patterns |
| `system` | G3 RMS, Opera, OXI, OHIP | Keyword patterns |
| `process` | installation, migration | Keyword patterns |
| `job` | full upload, first decision | Keyword patterns |
| `incident` | step failure, timeout | Keyword patterns |
| `configuration` | parameter, CP config | Keyword patterns |
| `metric` | (not yet extracted) | Future: metric parser |
| `knowledge_article` | (not yet extracted) | Future: LLM |

---

## Relationship Types (12)

| Relationship | Source -> Target | Evidence |
|-------------|-----------------|----------|
| `owned_by` | DOCUMENT -> TEAM | Team classifier result |
| `belongs_to` | ENTITY -> TEAM | Content metadata |
| `uses` | PROCESS -> SYSTEM | Keyword co-occurrence |
| `depends_on` | SYSTEM -> SYSTEM | Dependency patterns |
| `triggers` | PROCESS -> INCIDENT | Error pattern matching |
| `references` | DOCUMENT -> SYSTEM | Content extraction |
| `resolves` | INCIDENT -> PROCESS | Resolution patterns |
| `generated_from` | ENTITY -> DOCUMENT | Extraction provenance |
| `contains` | DOCUMENT -> CHUNK | Pipeline linkage |
| `part_of` | SYSTEM -> TEAM | OrgMap mapping |
| `affects` | INCIDENT -> TEAM | Impact analysis |
| `configured_by` | SYSTEM -> CONFIGURATION | Content patterns |

---

## Evidence Model

Every relationship carries evidence:

```python
@dataclass
class Evidence:
    source_document: str      # document_id
    source_chunk: str         # chunk_id (optional)
    source_text: str          # actual text fragment
    confidence: float         # 0.0-1.0
    human_confirmed: bool     # SEAL verification
    created_at: str           # ISO timestamp
    updated_at: str           # ISO timestamp
```

Evidence is never deleted. New evidence is added when the same entity/relationship appears in additional documents.

---

## Graph Schema (DuckDB)

### graph_entities
```sql
CREATE TABLE graph_entities (
    id VARCHAR PRIMARY KEY,
    name VARCHAR,
    entity_type VARCHAR,       -- one of 12 types
    description TEXT,
    metadata JSON,
    owner VARCHAR,
    visibility VARCHAR
);
```

### graph_relationships
```sql
CREATE TABLE graph_relationships (
    source_id VARCHAR,
    target_id VARCHAR,
    relation_type VARCHAR,     -- one of 12 types
    description TEXT,
    confidence DOUBLE,
    metadata JSON,
    PRIMARY KEY (source_id, target_id, relation_type)
);
```

### graph_evidence
```sql
CREATE TABLE graph_evidence (
    evidence_id VARCHAR PRIMARY KEY,
    entity_id VARCHAR,
    source_document VARCHAR,
    source_chunk VARCHAR,
    source_text TEXT,
    confidence DOUBLE,
    human_confirmed BOOLEAN DEFAULT FALSE,
    created_at VARCHAR,
    updated_at VARCHAR
);
```

### graph_entity_meta
```sql
CREATE TABLE graph_entity_meta (
    entity_id VARCHAR PRIMARY KEY,
    team_id VARCHAR,
    product_scope JSON,
    visibility VARCHAR,
    average_confidence DOUBLE,
    first_seen VARCHAR,
    last_verified VARCHAR,
    verification_count INTEGER DEFAULT 0
);
```

### entity_resolutions
```sql
CREATE TABLE entity_resolutions (
    alias VARCHAR,
    canonical_id VARCHAR,
    resolution_confidence DOUBLE,
    PRIMARY KEY (alias, canonical_id)
);
```

---

## Entity Extraction

### SmartEntityExtractor

Extracts entities from text using deterministic regex patterns:

1. **SYSTEM detection** — G3 RMS, Opera, OXI, OHIP, OPERA Cloud, etc.
2. **PROCESS detection** — installation, migration, monitoring, troubleshooting, deployment
3. **JOB detection** — full upload, first decision, catchup, incremental
4. **INCIDENT detection** — error, failure, timeout, crash, exception
5. **CONFIGURATION detection** — parameter, setting, CP config, threshold
6. **CLIENT detection** — hotel chains, property names
7. **PROPERTY detection** — physical locations

Each extraction produces an `ExtendedEntity` with:
- Deterministic ID (`ENT-SYSTEM-g3-rms`)
- Evidence list (source document, text fragment, confidence)
- Team ownership (from OrgMap integration)

### Deduplication

Same entity across 50 documents → one canonical entity with 50 evidence records.

```python
# First document: "G3 RMS handles rate management"
# → Entity: ENT-SYSTEM-g3-rms, evidence: [doc1]

# Second document: "Configure G3 RMS for PMS integration"
# → Entity: ENT-SYSTEM-g3-rms (deduplicated), evidence: [doc1, doc2]
```

---

## Graph Traversal

### GraphTraversalEngine

| Operation | Algorithm | Purpose |
|-----------|-----------|---------|
| `find_path()` | BFS | Shortest path between two entities |
| `analyze_impact()` | BFS + scoring | What is affected if an entity changes |
| `expand_context()` | BFS + filtering | Neighboring entities at depth N |
| `detect_communities()` | Connected components | Cluster related entities |
| `shortest_distance()` | BFS | Number of hops between entities |
| `get_degree()` | Adjacency count | Connectivity of an entity |

All operations use an in-memory adjacency cache (bidirectional) rebuilt on demand.

---

## Graph Registry (Unified Facade)

`GraphRegistry` is the single entry point:

```python
registry = GraphRegistry()

# Ingest a document
result = registry.ingest_document(
    text="...",
    document_id="DOC-001",
    team_id="spm",
)

# Search entities
entities = registry.search_entities(query="G3 RMS", entity_type="system")

# Get entity context with neighborhood
context = registry.get_entity_context("ENT-SYSTEM-g3-rms", depth=2)

# Find path between entities
path = registry.find_path("ENT-SYSTEM-g3-rms", "ENT-TEAM-spm")

# Analyze impact
impact = registry.analyze_impact("ENT-SYSTEM-g3-rms", max_depth=3)

# Get team subgraph
team_graph = registry.get_team_graph("spm")

# Get statistics
stats = registry.get_stats()
```

---

## Validation

```bash
# Run all 43 graph tests
python -m pytest tests/test_graph.py -v

# Validate graph integrity
python scripts/validate_graph.py

# Validate with custom DB
python scripts/validate_graph.py --db custom.duckdb --summary
```

Validation checks:
- Every ingested document has a DOCUMENT entity
- Every document has an OWNED_BY relationship to a team
- All entities have at least one evidence record
- No orphan entities (entities without relationships)
- No duplicate entity IDs
- Confidence values in valid range (0.0-1.0)
