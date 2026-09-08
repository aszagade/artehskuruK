# Mission D — Care/ICS Agent Email Extraction as a Knowledge Source

## Summary

Adds the Care and ICS teams' agent-extracted support-conversation data (SQL Server,
`CareAgent`/`ICSAgent` databases) as a new knowledge source, following the existing
`SourceAdapter` contract (`kurukshetra/sources/adapter.py`) that Salesforce and Confluence
already use. Zero changes to the Knowledge Fabric, the ingestion pipeline, or the graph/3D
visualization — all of that already works generically for any adapter; this mission is only
the adapter itself, plus config to register two sources through it.

## Business context (verified by connecting to the real database, not assumed)

`CareAgent` and `ICSAgent` each have a nearly-identical schema: conversation-level rollups
of support email threads (case number, issue/error type, property/chain code, SLA flag,
waiting time, resolution status), in two live generations per team:

| Source | Rows | Status |
|---|---|---|
| `Care_Email_Extraction` (legacy) | 45,991 | **Frozen** — last write 2026-06-01, one-time backfill candidate |
| `Care_Email_Extraction_V3` | 57,682 | **Active** — last write 2026-09-08 (today), ongoing incremental source |
| `ICS_Email_Extraction` (legacy) | 0 | Empty — harmless no-op |
| `ICS_Email_Extraction_V3` | 2,468 | Active but stale (last write 2026-07-28) — only real ICS source |

A third generation (`*_Email_Extraction_V2_1`) exists in both databases with 0 rows in
either — excluded, nothing to ingest. The `*_Email_Extract_Raw*` tables (raw email bodies,
`from_address`/`to_recipients`) are **deliberately out of scope**: real customer PII, and
not what was asked for ("email extraction," not raw email). If raw content is wanted later,
that's a separate, higher-sensitivity design decision (different visibility level at
minimum), not a small extension of this one.

## Architecture: one adapter, config-driven, zero new files for future sources

```
CareAgent / ICSAgent (SQL Server 172.26.122.106)
        │  pyodbc, "ODBC Driver 18 for SQL Server"
        ▼
AgentExtractionTransport            (schema-agnostic row fetch, any table)
        ▼
AgentExtractionAdapter               (SourceAdapter — the only new "logic" file)
  .discover(cursor) → SourceDocument
        ▼
KnowledgeFabric.ingest_source_document()   ← existing, UNCHANGED
        ├─ dedup (content hash), chunk, entity/relationship extraction → graph_entities
        └─ SEAL unknown-term detection
        ▼
Same retrieval + knowledge graph + 3D visualization every other source already uses
```

**The scalability requirement** ("adding data later shouldn't need a new file") is met at
two levels:

1. **Schema-agnostic row handling.** `AgentExtractionTransport.fetch_rows()` reads whatever
   columns a table actually has via `cursor.description` — no hardcoded column list.
   `AgentExtractionAdapter._row_to_document()` renders a fixed set of *known* fields in a
   readable order for chunk quality, but any column NOT in that known list still gets
   included generically (`tests/test_agent_extraction_adapter.py::test_unknown_fields_still_included`
   locks this in). A new column added upstream — by either team — needs no code change here.
2. **Config-driven multi-source.** One `AgentExtractionAdapter` class, parameterized
   entirely by a config dict (server, database, team, list of tables with their own
   version tag and cursor column). `kurukshetra/sources/persistent_registry.py`
   (`PersistentSourceRegistry`, pre-existing, previously unused for this purpose) stores that
   config durably in DuckDB. `load_registered_adapters()` turns every enabled
   `sql_agent_extraction` registry row into a live adapter instance at sync time. **Adding a
   third team's database, or a new table generation on an existing one, is one
   `register_source(...)` call** (edit the `SOURCES` list in
   `scripts/register_agent_extraction_sources.py` and re-run — it's an idempotent upsert —
   or call it directly from a REPL). `agent_extraction_adapter.py` and
   `scripts/sync_agent_extraction_sources.py` need zero changes either way.

## Row → document mapping

Each conversation row becomes one `SourceDocument`. Since these are structured rollups, not
free text, `text_content` is synthesized: known fields render first in a fixed,
human-readable order (case number, subject, property, issue/error type, status, SLA,
timestamps, ...), then any remaining columns render generically. `provenance.version_tag`
is `"legacy"` or `"v3"` (lets the Fabric's existing version-reconciliation handle the
overlap between generations rather than custom merge logic); `provenance.external_id` is
the `conversation_id`; `content_hash` is SHA-256 of the synthesized text for the Fabric's
existing dedup.

## Sync strategy — matched to what's actually true about each table

- **Legacy tables**: one-time backfill. The adapter's per-table cursor state (a JSON dict,
  packed into the single opaque cursor string the Fabric's `save_source_cursor`/
  `load_source_cursor` already support) marks a table `"__backfilled__"` after its first
  full read and never queries it again.
- **V3 tables**: ongoing incremental sync, cursored on `last_updated_at` — each run only
  reads rows newer than the last run's cursor.
- One table's failure (connection drop, permissions change) doesn't block the others —
  caught and logged per-table, cursor state for that table is simply left unadvanced so the
  next run retries it (`test_one_failing_table_does_not_break_the_other`).

## Governance decisions made (flagged, not silently assumed)

Per CLAUDE.md §4's closed ownership enum (Service Delivery/SDOPS/Support/Operations/
Revenue/QA/Shared Systems/UNKNOWN) and the existing OrgMap team list (SPM/ROA/ICS/SDOPS/HR/
IT/CPM, which doesn't include "Care"):

- `team_ids=["care"]` / `["ics"]` — new team tags on the document, additive, doesn't touch
  `kurukshetra/agent/org_map.py` or `TeamClassifier`.
- `owner_team` (the closed CLAUDE.md enum) — defaulted to `"Support"` for Care and
  `"SDOPS"` for ICS as the closest fit. **This is a default, set in
  `scripts/register_agent_extraction_sources.py`'s config, not hardcoded in the adapter** —
  changing it later is a one-line edit + re-run, not a code change.
- `default_visibility="Internal"` — no raw PII is ingested (see scope exclusion above), but
  this is real operational data about real customers/properties, so not `Public`.

## Security

- Credentials (`AGENT_DB_USER`, `AGENT_DB_PASSWORD`) are read **only** from environment
  variables, never written to any file, matching `kurukshetra/sources/adapter.py`'s own
  stated contract and `salesforce_adapter.py`'s precedent.
  `PersistentSourceRegistry._validate_no_secrets()` — pre-existing — would flag it if a
  future config edit accidentally included one.
- The password used to verify connectivity during this mission was shared in plaintext chat.
  **Recommend rotating it** — not a code fix, a real operational follow-up.
- Server/database/table identifiers are validated (alnum + underscore only) before being
  used in SQL string formatting — they're config-supplied, not raw user input, but the guard
  is cheap insurance in `agent_extraction_transport.py`'s `_validate_identifier()`.

## What Changed

| File | Purpose |
|---|---|
| `kurukshetra/sources/agent_extraction_transport.py` | **New** — schema-agnostic pyodbc data access, retry/backoff |
| `kurukshetra/sources/agent_extraction_adapter.py` | **New** — the `SourceAdapter`; `load_registered_adapters()` factory |
| `scripts/register_agent_extraction_sources.py` | **New** — config-only source registration (Care + ICS today) |
| `scripts/sync_agent_extraction_sources.py` | **New** — generic sync runner, unchanged as sources are added |
| `tests/test_agent_extraction_adapter.py` | **New** — 17 tests, mocked transport, no live DB required |
| `requirements.txt` | Added `pyodbc` |
| `docs/MISSION_D_AGENT_EXTRACTION_SOURCE.md` | **New** — this file |

## Verification

- 17/17 unit tests pass (mocked transport — config validation, identity/capabilities,
  row→document mapping including the schema-drift case, discover()'s backfill/incremental
  cursor logic including out-of-order rows, and registry-driven loading).
- Live connectivity confirmed against the real `172.26.122.106` server for both `CareAgent`
  and `ICSAgent`: health checks, `identify()`, and `discover()` verified to yield
  correctly-shaped real `SourceDocument`s from all four tables in scope (Care legacy, Care
  V3, ICS legacy — confirmed harmless no-op on its 0 rows, ICS V3).
- **Two real issues found and fixed during live verification, not just code review:**
  1. **Performance**: the first version's `fetch_rows()` did `ORDER BY [cursor_column]`
     even for a full/first-run scan with no filter — forcing SQL Server to sort the entire
     unfiltered table before returning a single row. Against the real
     `Care_Email_Extraction_V3` (57,682 rows) this didn't return in over 2 minutes. Fixed by
     only sorting server-side for the (small-result-set) incremental case, and having the
     adapter compute the cursor as a true `max()` over whatever order rows arrive in for a
     full scan — same result, no server-side sort. Confirmed the same call went from timing
     out to 0.1–0.4s. Locked in by
     `test_cursor_advances_correctly_even_with_out_of_order_rows`.
  2. **Title readability**: real Care rows showed `property_name` sometimes duplicating (or
     near-duplicating) the email subject — an upstream extraction quirk in the source data
     itself, not something this adapter should "clean up" (it renders what the source has,
     faithfully). Added a cheap case-insensitive substring check so the title doesn't repeat
     property_name when it's already contained in the subject; genuinely malformed/reformatted
     duplicates (e.g. a property name with extra stray text not verbatim in the subject) still
     render as-is — expected, not a bug.
- **Full ingestion was deliberately NOT run as part of this mission.** ~58k Care V3 rows +
  46k Care legacy rows + 2.5k ICS V3 rows is a real, resource-intensive operation (chunking +
  entity extraction for tens of thousands of documents) — that's a decision for you to
  trigger deliberately (`python scripts/sync_agent_extraction_sources.py`), not something to
  run as a side effect of building the adapter.

### Confirmed live: the knowledge graph (2D and 3D) actually updates, not just architecturally

Ingested 15 real `Care_Email_Extraction_V3` rows through the real
`KnowledgeFabric.ingest_source_document()` (no adapter/pipeline changes — the exact same
path every other source uses), then queried the real running API:

- `GET /api/graph/stats` (the 2D "Knowledge Overview" dashboard's source): entity/
  relationship counts increased, `"care"` and `"ics"` present in `teams_represented`.
- `GET /api/graph/visualization` (what `command_center/frontend/graph3d.js` renders): a
  `SYS-G3-RMS` node appeared — extracted directly from the synthesized text
  ("...IDeaS G3 RMS...") — with real edges: `G3 RMS —uses→ TEAM-SPM` (derived from
  document co-occurrence), `G3 RMS —triggers→ Issue Status`. `TEAM-CARE` appeared as a new
  team-concept node, created directly from this adapter's `team_ids=["care"]` tagging —
  proof the "care" team (not previously in OrgMap) is now a real, visible concept in the
  graph without any OrgMap code change.

No graph/visualization code was touched to make this happen — this is the payoff of using
the existing `SourceAdapter` contract rather than a bespoke ingestion path.

## Not Done (scoped out on purpose)

- **Raw email content** (`*_Extract_Raw*` tables) — excluded per the scope discussion above;
  a separate, higher-sensitivity design if ever wanted.
- **Deletion detection** — the extraction tables don't signal deletions; `capabilities()`
  correctly declares `supports_deletion=False` rather than pretending otherwise.
- **Scheduling the sync** — `scripts/sync_agent_extraction_sources.py` is written to be
  cron/Task-Scheduler-friendly (proper exit codes, `--source-id` filter) but nothing
  schedules it yet; that's an infra decision (this repo has no CI/scheduler today) outside
  this mission's scope.
- **A dedicated UI/API surface for this source** (beyond it flowing into the existing
  `/api/ask`, `/api/query`, and graph endpoints automatically) — not requested, and the
  whole point of using the existing adapter contract is that no new surface is needed.

## Not Committed

Awaiting approval.
