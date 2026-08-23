# Ingestion Pipeline

9-step pipeline that transforms raw documents into queryable organizational knowledge.

---

## Pipeline Stages

```
Raw Document (PDF)
    |
    1. [Extract]     PDFExtractor.extract(file_path) -> raw text
    2. [Clean]       KnowledgeCleaner.clean(raw_text) -> cleaned text
    3. [Register]    DocumentRegistrar.register(file_path) -> DocumentIdentity
    4. [Classify]    TeamClassifier.classify_document(text, filename) -> team
    5. [Enrich]      ContentEnricher.enrich(text, filename) -> product, type
    6. [Chunk]       SemanticSplitter.split(doc_id, text) -> [Chunk, ...]
    7. [Store]       Chunk storage -> DuckDB chunks table + embeddings
    8. [Terms]       GlossaryManager.detect_unknown_terms(text) -> [UnknownTerm, ...]
    9. [Graph]       GraphRegistry.ingest_document(text, doc_id, team) -> entities, relationships
```

---

## Entry Points

### Single document
```python
from pathlib import Path
from kurukshetra.pipeline.ingest import IngestionPipeline

pipeline = IngestionPipeline(use_semantic_chunking=True)
result = pipeline.ingest(Path("docs/G3_RMS_Guide.pdf"))
```

### Batch
```python
results = pipeline.ingest_batch(list(Path("docs/").glob("*.pdf")))
```

### Graph-only population (existing documents)
```bash
python -m kurukshetra.pipeline.graph_indexer
```

---

## Stage Details

### 1. Extract
- **Module:** `kurukshetra.extractors.PDFExtractor`
- **Input:** File path
- **Output:** Raw text string
- **Behavior:** Reads PDF with pdfplumber. Falls back to plain text for .txt files.

### 2. Clean
- **Module:** `kurukshetra.preprocessing.KnowledgeCleaner`
- **Input:** Raw text
- **Output:** Cleaned text
- **Behavior:** Removes headers/footers, normalizes whitespace, strips non-content.

### 3. Register
- **Module:** `kurukshetra.services.DocumentRegistrar`
- **Input:** File path
- **Output:** `DocumentIdentity` (document_id, title, path, hash)
- **Behavior:** Creates document record in DuckDB `documents` table. Deduplicates by content hash.

### 4. Classify Team
- **Module:** `kurukshetra.services.team_classifier.TeamClassifier`
- **Input:** Text, filename, document_id
- **Output:** `ClassificationResult` (primary_team_id, team_scores, evidence)
- **Behavior:** Multi-signal classification using OrgMap keywords, filename patterns, and content signals. Cross-team detection for documents used by multiple teams.
- **Teams:** SPM, ICS, SDOPS, CPM, HR, IT, ROA

### 5. Enrich Content
- **Module:** `kurukshetra.services.content_enricher.ContentEnricher`
- **Input:** Text, filename
- **Output:** `ContentMetadata` (product_scope, document_type, content_signals)
- **Behavior:** Identifies IDeaS products (G3 RMS, Opera, OXI, OHIP) and document types.

### 6. Chunk
- **Module:** `kurukshetra.chunking.semantic.SemanticSplitter`
- **Input:** Document ID, text
- **Output:** List of `Chunk` objects (chunk_id, document_id, text, position)
- **Config:** max_chunk_size=1000, overlap=150
- **Fallback:** `DeterministicSplitter` (fixed-size with overlap)

### 7. Store
- Chunks written to DuckDB `chunks` table
- Embeddings generated via BGE model
- Vector index updated

### 8. Detect Terms
- **Module:** `kurukshetra.services.glossary.GlossaryManager`
- **Input:** Text, document_id
- **Output:** List of `UnknownTerm` objects
- **Behavior:** Identifies terms not in the glossary. Stores in `unknown_terms` table for SEAL interview.

### 9. Build Graph
- **Module:** `kurukshetra.graph.registry.GraphRegistry.ingest_document()`
- **Input:** Text, document_id, team_id, product_scope
- **Output:** `ExtractionResult` (entities, relationships)
- **Behavior:** Extracts SYSTEM, PROCESS, JOB, INCIDENT, CONFIGURATION, CLIENT, PROPERTY entities. Creates TEAM entity + OWNED_BY relationship. Stores evidence. Deduplicates by entity ID.

---

## DuckDB Schema (relevant tables)

| Table | Purpose | Written By |
|-------|---------|------------|
| `documents` | Document registry | Stage 3 (Register) |
| `chunks` | Text chunks | Stage 6-7 (Chunk + Store) |
| `graph_entities` | Entity nodes | Stage 9 (Graph) |
| `graph_relationships` | Relationship edges | Stage 9 (Graph) |
| `graph_evidence` | Evidence records | Stage 9 (Graph) |
| `graph_entity_meta` | Extended entity metadata | Stage 9 (Graph) |
| `unknown_terms` | Pending unknown terms | Stage 8 (Terms) |
| `glossary` | Confirmed terms | Stage 8 (Terms) |
| `content_metadata` | Content classification | Stage 5 (Enrich) |
| `team_classifications` | Team routing results | Stage 4 (Classify) |

---

## Graph Population Bridge

For documents already in DuckDB that need graph population:

```bash
# Populate graph for all 483 registered documents
python -m kurukshetra.pipeline.graph_indexer

# Validate after population
python scripts/validate_graph.py
```

The bridge:
1. Reads all documents from `documents` table
2. For each document, extracts text from `chunks` table
3. Calls `GraphRegistry.ingest_document()` for each
4. Prints progress every 25 documents
5. Reports final counts

---

## Backward Compatibility

- The pipeline is additive. All new stages (4, 5, 8, 9) are additions to the existing 3-step flow.
- Existing documents continue to work. Graph population is a separate step.
- No changes to RAG retrieval, SANJAYA, or chat behavior.
