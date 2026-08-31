# Mission 3.42 — User Document Ingestion

## Objective

Allow users to upload organizational documents through the API and make them immediately searchable by SANJAYA, without restarting the server.

## Test Result

**601/601 tests pass, 0 failures** (including 20 new upload/ingestion tests)

## What Was Built

### 1. Upload Endpoint: `POST /api/knowledge/upload`

Accepts multipart file uploads and routes through the existing KnowledgeFabric pipeline.

**Security:**
- Validates file extension against allowed list
- Rejects dangerous extensions (exe, bat, sh, py, etc.)
- Enforces 50 MB file size limit
- Rejects empty files
- Sanitizes filename (strips path components)
- Saves to safe internal directory (`knowledge/inbox/uploads/`)
- SHA-256 content hash prevents overwrites
- Preserves provenance and source identity

**Response:**
```json
{
  "document_id": "DOC-000700",
  "filename": "my_document.pdf",
  "status": "ok",
  "message": "Document ingested successfully: 12 chunks, 5 entities",
  "chunks_stored": 12,
  "entities_extracted": 5,
  "team_id": "spm",
  "execution_time_ms": 1250.0
}
```

### 2. New Format Support in TextExtractor

| Format | Extension | Library | Status |
|--------|-----------|---------|--------|
| PDF | `.pdf` | pdfplumber | ✅ Existing |
| Word | `.docx` | python-docx | ✅ Existing |
| Excel | `.xlsx` | openpyxl+pandas | ✅ Existing |
| Legacy Excel | `.xls` | xlrd+pandas | ✅ Existing |
| CSV | `.csv` | pandas | ✅ Existing |
| Text | `.txt` | built-in | ✅ Existing |
| Markdown | `.md` | built-in | ✅ Existing |
| **PowerPoint** | `.pptx` | python-pptx | ✅ **NEW** |
| **HTML** | `.html/.htm` | html.parser | ✅ **NEW** |
| **JSON** | `.json` | json | ✅ **NEW** |
| **XML** | `.xml` | xml.etree | ✅ **NEW** |

### 3. Ingestion Pipeline (Reused)

The upload endpoint routes through the existing canonical pipeline:

```
Upload → Save to knowledge/inbox/uploads/
       → KnowledgeFabric.ingest_file()
       → TextExtractor (extract text)
       → IngestionPipeline (chunk, embed, store)
       → DocumentRegistrar (register, deduplicate)
       → GraphRegistry (extract entities, relationships)
       → BM25 index (update)
       → Vector index (update)
       → ConceptTeams (track multi-team associations)
       → DocumentState (version tracking)
       → Provenance (source path, SHA-256, timestamp)
```

No parallel pipeline created. No existing behavior changed.

## Files Changed

| File | Change |
|------|--------|
| `kurukshetra/extractors/text_extractor.py` | Added PPTX, HTML, JSON, XML extraction |
| `command_center/backend/routers/knowledge.py` | Added `POST /api/knowledge/upload` endpoint |
| `tests/test_upload_ingestion.py` | **NEW** — 20 tests for upload/ingestion |

## Files NOT Changed

- Retrieval algorithms (BM25, Vector, Hybrid)
- Security/visibility filtering (existing model reused)
- Knowledge Fabric core logic
- Graph/SEAL behavior
- Database schema
- SANJAYA answer generation
- External dependencies

## Supported Formats Summary

After this mission, KURUKSHETRA supports **13 file formats**:

```
Document formats:  PDF, DOCX, PPTX
Spreadsheet:       XLSX, XLS, CSV
Text:              TXT, MD, RST
Web/Config:        HTML, HTM, JSON, XML
```

## Upload → Answer Flow

1. User uploads file via `POST /api/knowledge/upload`
2. File saved to `knowledge/inbox/uploads/`
3. KnowledgeFabric ingests: extract → chunk → embed → graph → index
4. Document becomes searchable immediately
5. User asks question via `POST /api/ask`
6. SANJAYA retrieves evidence from newly ingested document
7. GX10 generates grounded answer with citations

## Test Coverage

| Test Category | Count | Status |
|---------------|-------|--------|
| Format extraction (HTML, JSON, XML, PPTX) | 6 | ✅ |
| Security constraints | 4 | ✅ |
| End-to-end upload | 10 | ✅ |
| **Total** | **20** | **All pass** |

### Key Test Scenarios

- ✅ TXT upload → ingest → searchable
- ✅ CSV upload → ingest
- ✅ JSON upload → ingest
- ✅ Duplicate upload → deduplication
- ✅ Empty file → rejected (400)
- ✅ Dangerous extension → rejected (400)
- ✅ Unsupported format → rejected (400)
- ✅ Large file (51MB) → rejected (413)
- ✅ Path traversal → sanitized
- ✅ Filename preserved in response

## Security

- Upload directory is within project scope
- Dangerous extensions blocked
- File size limit enforced
- Path traversal prevented
- SHA-256 deduplication
- Existing visibility/access control applied
- Provenance preserved

## Not Committed

Awaiting approval.

---

What would you like to do next?
