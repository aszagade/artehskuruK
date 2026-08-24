# KURUKSHETRA Foundation Demo

Local demonstration runtime proving end-to-end knowledge acquisition.

---

## Quick Start

```bash
# Start KURUKSHETRA
python -m kurukshetra.runtime
```

This starts:
- FastAPI backend on `http://localhost:8000`
- Inbox watcher polling `knowledge/inbox/` every 5 seconds
- Swagger docs at `http://localhost:8000/docs`

---

## Demo Procedure

### 1. Start KURUKSHETRA

```bash
python -m kurukshetra.runtime
```

Output:
```
KURUKSHETRA Runtime
============================================================
  Knowledge Inbox: knowledge/inbox/
  Processed:       knowledge/processed/
  Failed:          knowledge/failed/
  API:             http://localhost:8000
  Docs:            http://localhost:8000/docs

  Drop a document into knowledge/inbox/ to start.
[WATCHER] Watching knowledge/inbox/ (poll every 5s)
```

### 2. Drop a Document

Copy any supported file into `knowledge/inbox/`:

```bash
cp my_document.txt knowledge/inbox/
```

Supported types: `.pdf`, `.txt`, `.md`, `.docx`, `.xlsx`, `.csv`

### 3. Watch Ingestion Progress

The watcher automatically detects and ingests the file:

```
[WATCHER] Found 1 new document(s)
[WATCHER] Ingesting: my_document.txt
[WATCHER] OK: DOC-000042 | 3 chunks | 8 entities | 16 relationships | 5 unknown terms
```

### 4. Query via API

```bash
# Check activity
curl http://localhost:8000/api/activity

# Query SANJAYA
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is QuantumBridge?", "top_k": 3}'

# Check metrics
curl http://localhost:8000/api/metrics

# Check graph
curl http://localhost:8000/api/graph/stats

# Check SEAL unknowns
curl http://localhost:8000/api/glossary/pending

# Trigger inbox ingestion manually
curl -X POST http://localhost:8000/api/ingest/inbox
```

### 5. Open Swagger UI

Navigate to `http://localhost:8000/docs` for interactive API exploration.

---

## What Happens Automatically

```
knowledge/inbox/document.txt
    |
    v (watcher detects)
NEW DOCUMENT DETECTED
    |
    v
EXTRACTING (TextExtractor: PDF/TXT/MD/DOCX/XLSX/CSV)
    |
    v
REGISTERED (DocumentRegistrar: SHA-256 dedup)
    |
    v
CLASSIFIED (TeamClassifier: 7 teams via OrgMap)
    |
    v
CHUNKED (DeterministicSplitter: 500-char chunks)
    |
    v
PERSISTED (ChunkRepository: DuckDB)
    |
    v
GRAPH UPDATED (SmartEntityExtractor: entities + relationships + evidence)
    |
    v
RAG READY (BM25 retrieval works immediately)
    |
    v
UNKNOWN TERMS (GlossaryManager: terms for SEAL)
    |
    v
COMPLETE (file moved to knowledge/processed/)
```

---

## API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/health` | System health check |
| POST | `/api/query` | Query SANJAYA/RAG |
| POST | `/api/ingest` | Ingest a specific file |
| POST | `/api/ingest/inbox` | Ingest all files from inbox |
| GET | `/api/activity` | Ingestion activity status |
| GET | `/api/activity/{filename}` | Status for specific document |
| GET | `/api/metrics` | System metrics |
| GET | `/api/graph/stats` | Graph statistics |
| GET | `/api/graph/entities` | Search graph entities |
| GET | `/api/graph/entity/{id}` | Entity context + neighborhood |
| GET | `/api/glossary/pending` | SEAL unknown terms |
| GET | `/api/recommendations` | Self-improvement recommendations |
| GET | `/api/org/map` | Organizational hierarchy |
| POST | `/api/feedback` | Submit retrieval feedback |

---

## Architecture

```
knowledge/inbox/           <-- Drop documents here
    |
    v
InboxWatcher (polls every 5s)
    |
    v
IngestionPipeline
    +-- TextExtractor (PDF/TXT/MD/DOCX/XLSX/CSV)
    +-- KnowledgeCleaner
    +-- DocumentRegistrar (SHA-256 dedup)
    +-- TeamClassifier (OrgMap)
    +-- ContentEnricher
    +-- DeterministicSplitter
    +-- ChunkRepository (DuckDB)
    +-- GlossaryManager (unknown terms)
    +-- GraphRegistry (entities + relationships + evidence)
    |
    v
knowledge/processed/      <-- Successfully ingested
    or
knowledge/failed/         <-- Ingestion errors
```

---

## Graph Visualization

After ingestion, query the graph for the new document:

```bash
# Get graph stats
curl http://localhost:8000/api/graph/stats

# Search for entities
curl "http://localhost:8000/api/graph/entities?query=QuantumBridge"

# Get entity context
curl http://localhost:8000/api/graph/entity/SYS-QUANTUMBRIDGE
```

The graph view shows:
```
Document (DOC-xxx)
   |
   +-- Team (TEAM-SPM)
   |     relationship: OWNED_BY
   |
   +-- System (SYS-G3-RMS)
   |     relationship: USES
   |
   +-- Process (PROC-DEPLOYMENT)
         relationship: REFERENCES
```

---

## SEAL Unknown Terms

After ingestion, check for unknown terms:

```bash
curl http://localhost:8000/api/glossary/pending
```

Response shows terms requiring human confirmation:
```json
[
  {
    "term": "QuantumBridge",
    "first_seen_doc": "DOC-000042",
    "occurrence_count": 3,
    "suggested_category": "product",
    "context_snippet": "QuantumBridge sends deployment events..."
  }
]
```

---

## Limitations

1. **Entity extraction is regex-only**: Only 28 hardcoded systems detected. Unknown systems like "QuantumBridge" are not extracted as entities (but appear as unknown terms).
2. **Embeddings off by default**: Vector search requires `build_embeddings=True`.
3. **No real-time UI updates**: Polling-based, not WebSocket.
4. **Single-process**: No parallel ingestion.
5. **No authentication**: Open access.

---

## Deterministic Components

| Component | Algorithm |
|-----------|-----------|
| File detection | Extension matching |
| Text extraction | Per-type extractor |
| Document registration | SHA-256 hash |
| Team classification | Keyword matching |
| Chunking | Character-based splitting |
| Entity extraction | Regex patterns |
| Relationship inference | Co-occurrence |
| Evidence attachment | Source document linkage |
| Unknown term detection | Regex (ALL CAPS, CamelCase) |
| Deduplication | Document ID + fingerprint |

---

## Future Capabilities (Not Implemented)

- Candidate entity discovery
- Multi-team entity ownership
- Event -> Graph connection
- Graph -> RAG enhancement
- SEAL -> knowledge reuse
- Real-time UI updates (WebSocket)
- LLM entity extraction
- Real enterprise connectors
