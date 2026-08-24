# ICS Network Knowledge Source Profile

**Generated:** 2026-08-24
**Source:** `\\ina6fs01\Dept_shares\ICS`
**Mode:** Read-Only (CSV inventory analysis)
**Profiler:** KURUKSHETRA Source Discovery v1.0

---

## Executive Summary

The ICS department network share contains **152,867 files** across **12,980 folders**.
Of these, **40,566 files (26.5%)** are immediately ingestible by the current
KURUKSHETRA TextExtractor. The remaining 112,301 files are primarily:

- **33,181 SAS data files** (`.sas7bdat`) — 78 GB, require SAS reader
- **27,990 Python files** (`.py`) — code, not knowledge documents
- **25,972 compiled Python** (`.pyc`) — compiled bytecode
- **12,694 files with no extension** — mixed content
- **1,515 `.download` files** — partial/incomplete downloads

The source is **100% readable** — no access-denied folders were found.

---

## Folder Structure

```
\\ina6fs01\Dept_shares\ICS\
  |
  +-- Install/                         150,363 files (98.4%)
  |     +-- 60DayDiscrepanyandDV/      150,335 files
  |           +-- Forecast Reviews/     52,862 files
  |           +-- Ankit's DV Automation/ 43,887 files
  |           +-- TAJ/                  22,030 files
  |           +-- Data Verification/    14,746 files
  |           +-- Technical Verification_Code/ 7,171 files
  |           +-- Oberoi Hotels/         3,443 files
  |           +-- (40+ more subfolders)
  |     +-- Special Client/                24 files
  |     +-- (root files)                   4 files
  |
  +-- Omkar/                           2,165 files (1.4%)
  |     +-- Backups/                   1,207 files
  |     +-- G2 Enjoy Hotels/             637 files
  |     +-- G2 SUN International/        292 files
  |     +-- Process Documents/            24 files
  |     +-- CPMigration Switch RCA/        3 files
  |
  +-- Data Discrepancy Inputs/           337 files (0.2%)
  |     +-- Processed/                   120 files
  |     +-- Output/                       91 files
  |     +-- Logs/                         89 files
  |     +-- Failed/                       37 files
  |
  +-- Audit/                               1 file
  +-- Installation & Audit Dashboard/      1 file
```

---

## Extension Distribution

| Extension | Count | Size (MB) | Category | Ingestible |
|-----------|------:|----------:|----------|:----------:|
| .sas7bdat | 33,181 | 78,459 | DATA | No |
| .py | 27,990 | 364 | CODE | No |
| .csv | 26,823 | 21,754 | DATA | **Yes** |
| .pyc | 25,972 | 450 | CODE | No |
| (none) | 12,694 | 18 | UNKNOWN | No |
| .xlsx | 10,652 | 14,012 | SPREADSHEET | **Yes** |
| .pyi | 3,634 | 16 | CODE | No |
| .pdf | 1,911 | 4,829 | DOCUMENT | **Yes** |
| .download | 1,515 | 1,225 | UNKNOWN | No |
| .pyd | 961 | 287 | CODE | No |
| .zip | 778 | 13,542 | ARCHIVE | No |
| .json | 691 | 1,536 | DATA | No |
| .docx | 577 | 395 | DOCUMENT | **Yes** |
| .psv | 447 | 184 | DATA | No |
| .txt | 409 | 37 | TEXT | **Yes** |
| .md | — | — | TEXT | **Yes** |

---

## Content Sampling Results (Omkar/Process Documents)

This is the most valuable knowledge area in ICS — 24 documents containing
real process knowledge:

| Document Type | Extraction | Quality | Systems Detected |
|---------------|:----------:|---------|-----------------|
| XLSX (SFDC Workflows) | OK | Structured form data | G3, SFDC |
| XLS (RMS Config) | OK | Tabular workflow steps | RMS, G3, D360, SFDC |
| DOCX (G3 Data Feed) | OK | Rich narrative + tables | G3, NGI, Salesforce, Datadog, CRM, SFTP, EDF |
| PDF (KB Pricing) | OK | Step-by-step guide | G3, RMS |

**Key findings from sampled documents:**

- **Systems recognized:** G3, RMS, NGI, SFDC, Salesforce, Datadog, CRM, SFTP, D360
- **Acronyms detected:** CPM, NGI, EDF, CRM, BDE, SFTP, IP, GFE, ROA, ISM
- **Team signals:** ICS, CPM, ROA
- **Processes detected:** configuration, installation, workflow, migration,
  validation, verification, monitoring, automation, pricing, evaluation

---

## Ingestion Zone Recommendations

### HIGH_VALUE_KNOWLEDGE (Recommended for future ingestion)

- `ICS\Omkar\Process Documents` — 24 files, 100% ingestible, real process knowledge
- `ICS\Install\60DayDiscrepanyandDV\Install Documents` — 17 files, workflow documentation

### REVIEW_REQUIRED

- `ICS\Install\60DayDiscrepanyandDV` — 150,335 files, massive collection requiring filtering
- `ICS\Omkar` — 2,165 files, mix of backups and active work
- `ICS\Data Discrepancy Inputs` — 337 files, operational data (Processed/Output/Logs/Failed)

### OPERATIONAL_DATA

- `ICS\Audit` — 1 file (Jan 2024 audit spreadsheet)
- `ICS\Data Discrepancy Inputs\Logs` — 89 log files

### LIKELY_NOISE

- `ICS\Install\60DayDiscrepanyandDV\Downloads` — 14 files (browser downloads)
- `ICS\Install\60DayDiscrepanyandDV\Overdue Tasks` — 8 files
- `.download` files — 1,515 partial/incomplete downloads
- `.pyc` files — 25,972 compiled Python bytecode

---

## Duplicate / Version Patterns Detected

### Duplicate Files (same filename in multiple locations)

| Filename | Occurrences |
|----------|:-----------:|
| TaskDetailReport.xlsx | 3+ |
| error.txt | 3+ |
| READ_ME_ERROR.txt | 3+ |
| PROMO.xlsx | 3+ |
| G3_DataExtraction_*.xlsx | 2+ |

### Version Patterns

- **Dated versions:** G3_DataExtraction_2026-08-05, HtngMessage variants
- **Numbered versions:** Not heavily present
- **Suffixed versions:** G3_DataExtraction variants

---

## Key Insights

1. **The source is overwhelmingly code/data, not knowledge.**
   73.5% of files are unsupported (SAS, Python, compiled Python).
   Only 26.5% are knowledge documents.

2. **The knowledge is concentrated.**
   `Omkar/Process Documents` (24 files) contains the richest process knowledge.
   `Install/60DayDiscrepanyandDV/Install Documents` (17 files) contains workflow docs.

3. **G3 RMS is the dominant system.**
   Almost every sampled document references G3, RMS, or related systems.

4. **SFDC workflows are heavily represented.**
   10,652 XLSX files + workflow templates suggest SFDC integration is a major ICS activity.

5. **Forecast Reviews is the largest subfolder.**
   52,862 files — likely automated forecast data, not human knowledge.

6. **The source changes frequently.**
   Last modified dates span 2023-2026, with many recent files.

7. **Person-organized folders exist.**
   "Ankit's DV Automation Code" (43,887 files) suggests individual developer automation.

---

## Architecture Readiness

### Existing Components That Can Be Reused

| Component | Role |
|-----------|------|
| TextExtractor | PDF, DOCX, XLSX, XLS, TXT, MD, CSV extraction |
| IngestionPipeline | Full pipeline: extract -> register -> classify -> chunk -> persist -> graph |
| DocumentRegistrar | SHA-256 dedup, source_path provenance |
| TeamClassifier | OrgMap keyword-based team assignment |
| ChunkRepository | DuckDB chunk persistence |
| GraphRegistry | Entity/relationship/evidence persistence |
| GlossaryManager | Unknown term detection for SEAL |
| DatabaseBM25Retriever | BM25 text search |
| VectorRetriever | BGE embedding search |
| StatusTracker | Ingestion lifecycle monitoring |
| InboxWatcher | File detection and movement |

### Gaps Before Real Network-Source Ingestion

1. **Source abstraction** — No universal SOURCE interface for FS/Salesforce/Confluence/etc.
2. **Folder-aware watcher** — Current watcher is flat, no subfolder tracking
3. **Incremental change detection** — No mtime/size-based delta scan
4. **Batch ingestion orchestration** — No priority queue for large sources
5. **Network path normalization** — UNC paths not standardized
6. **File version management** — No CURRENT/HISTORICAL distinction
7. **Source-specific filtering** — No per-source include/exclude rules
8. **Cross-source dedup** — Same doc in ICS share + inbox not detected
9. **Large-scale embedding** — No batch embedding for 40K+ files
10. **Graph entity dedup across sources** — Entity IDs not globally unique
11. **Source health monitoring** — No access/latency tracking
12. **Connector registry** — No plugin architecture for future connectors

---

## Future Connector Architecture

```
Network Share ─────┐
Salesforce ────────┤
Confluence ────────┤
Datadog ───────────┤
SQL ───────────────┤──> Source Abstraction Layer
Smartsheet ────────┤         |
Teams/Outlook ─────┤         v
Graph API ─────────┘   Canonical Event/Document Model
                             |
                             v
                     KURUKSHETRA Knowledge Fabric
                     (RAG + Graph + SEAL + SANJAYA)
```

---

## Recommended Next Steps

1. **Pilot ingestion of Omkar/Process Documents** (24 files) — high-value, low-risk
2. **Build the Source abstraction layer** — universal interface for all future connectors
3. **Implement incremental change detection** — scan only modified files
4. **Build selective ingestion rules** — per-source include/exclude patterns
5. **Connect Event Bus to ICS Data Discrepancy Inputs** — operational event flow
