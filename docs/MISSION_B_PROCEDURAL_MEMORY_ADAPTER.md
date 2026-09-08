# Mission B — Procedural Memory as a Process Intelligence Adapter

## Summary

Completes the "procedural memory" leg identified in prior research (Mission 3.47 labeled it
`FOUNDATION — table exists; not yet wired to answering`). Rather than building out the
existing standalone `procedural_memory` table, this mission **replaces it entirely** with a
thin adapter over `kurukshetra/process/intelligence.py` (Mission 3.58's Process
Intelligence) — a real, evidence-backed, already-wired system that extracts processes with
steps, triggers, actors, and structural gap detection from the corpus (182+ processes /
1,569+ steps on the real corpus per Mission 3.58's own numbers). Then, mirroring Mission A's
shape, wires it into `AgenticSANJAYA.ask()` as additive diagnostic context.

## Why replace instead of build out

`ProceduralMemory.store_procedure()` had zero callers anywhere in the codebase except its
own unit test — the `procedural_memory` table had no production data. Meanwhile Process
Intelligence already does the same job better: real trigger/actor/system/handoff pattern
extraction, structural gap detection (`no_owner`, `no_successor`, etc.), evidence levels,
and a live API surface (`/api/processes/*`, a Process Explorer UI). Building `ProceduralMemory`
out as its own parallel store would have created a second, worse, still-empty implementation
of something the codebase already does well — exactly what `CLAUDE.md`'s charter warns
against ("never create a duplicate implementation of existing functionality"). This mirrors
the pattern `SemanticMemory` already correctly uses for the knowledge graph: wrap the
authoritative store, don't duplicate it.

## What Changed

### `kurukshetra/process/intelligence.py`
Added `search_processes(query, limit=5)` — the one query shape Process Intelligence lacked
(`list_processes()` only filters by exact `team`/`quality`, not free text). Same keyword-LIKE
style already used elsewhere in this codebase (`memory_store.py`'s `find_procedure`/
`find_similar_queries`) — no new search infrastructure introduced. Strips punctuation from
keywords (`re.findall(r"[A-Za-z0-9]+", ...)` instead of `.split()`) so a naturally phrased
question ending in "?" still matches — found as a real bug while testing this mission (a
query like "...marker?" failed to LIKE-match stored text "...marker Procedure" because the
keyword carried the trailing "?"); fixed at the source rather than worked around in tests.

### `kurukshetra/agent/memory_store.py`
`ProceduralMemory` rewritten as a thin adapter:
- `find_procedure(query, limit=5)` → `process.intelligence.search_processes()`
- `get_procedure(process_id)` → `process.intelligence.get_process()` (full detail: steps + gaps)
- `get_all_procedures(team=None, limit=50)` → `process.intelligence.list_processes()`
- Removed: `store_procedure()`, `_ensure_table()`, the `procedural_memory` table creation,
  and the custom `__init__` (no longer owns any state to initialize).
- Return shape changed from the old ad hoc `{id, name, description, source, team, steps,
  validated, confidence}` to the real `processes` table row shape (`process_id, name,
  description, team, quality, confidence, step_count, ...`) — there were no real external
  callers of the old shape to preserve compatibility with (confirmed by search before
  changing it).

### `kurukshetra/agent/orchestrator.py`
Same wiring pattern as Mission A's episodic memory, deliberately:
- `AgenticResult` gained `matched_procedures: list[dict]`.
- `__init__` constructs `self.procedural_memory` defensively (`None` on any failure, same
  `try/except` shape as `episodic_memory` right above it).
- New `_find_matching_procedures(query)`, called once at the top of `ask()` alongside
  `_recall_similar_episodes`.
- **Deliberately additive/non-influencing**, same contract as episodic memory: a matched
  procedure is surfaced for the caller to display, never fed into evidence, generation, or
  confidence. Feeding procedure steps into the LLM synthesis pipeline as better-structured
  evidence than raw chunks is a real, larger idea from the original research — but it's a
  bigger, riskier change to the sufficiency-gate/generation pipeline, deliberately deferred
  (see "Not Done" below), not folded into this mission.

### `command_center/backend/routers/chat.py`
- New `MatchedProcedureResponse` model (summary shape: process_id, name, description, team,
  quality, confidence, step_count — full steps/gaps require a separate
  `GET /api/processes/{process_id}` call, unchanged).
- `AskResponse` gained `matched_procedures: list[MatchedProcedureResponse]`, populated from
  `agentic_result.matched_procedures` in `ask_evidence_grounded`.

### Tests
- `tests/test_memory_foundation.py::TestProceduralMemory` — fully rewritten (the old
  `test_store_procedure`/`test_find_procedure` tested the removed method). New tests use the
  same `ensure_process_tables()`/`persist_process()` fixture pattern as
  `test_process_intelligence.py` itself, plus a guard test
  (`test_no_longer_owns_a_standalone_table`) asserting `store_procedure` is genuinely gone,
  not just unused.
- `tests/test_agentic_sanjaya.py::TestProceduralMemoryWiring` — 4 new tests: empty when
  nothing matches, a real seeded process is surfaced, matching never changes the
  answer/confidence (isolated by toggling `procedural_memory` on/off for the identical
  query), and `ask()` degrades gracefully with `procedural_memory = None`.

Both test files needed word-uniqueness fixes identical to what Mission A's episodic tests
already required: the shared, session-persistent DuckDB accumulates seeded rows across test
runs, and keyword-LIKE matching on any word >3 characters means generic words ("procedure",
"installation") collide with other tests' fixtures. Every new test query/seed name uses a
uuid-suffixed marker with no other shared words.

One further lesson found while stabilizing these: `search_processes()`/`find_procedure()`
match is **OR-across-keywords**, so a query mixing one unique word with generic ones can
still surface unrelated rows that only match the generic words — and confidence ties have
no guaranteed secondary sort order. A test asserting `found[0]["name"] == expected` was
flaky against a DB accumulating rows across repeated local runs; fixed by asserting
membership (`expected in [p["name"] for p in found]`) instead, which is the actually-correct
thing to test — "was it found," not "was it ranked first under an unspecified tie-break."
Confirmed stable across two consecutive runs with no DB cleanup between them.

## Verification

Live, end-to-end, via the real running API: seeded a real process through
`kurukshetra.process.intelligence.persist_process()`, then `POST /api/ask` with a matching
query returned `matched_procedures` with the correct `process_id`, `name`, `description`,
`team`, `confidence`, and `step_count` — while SANJAYA's own answer independently and
correctly abstained (no chunk-level evidence existed), proving the two systems are properly
decoupled: procedural memory surfaced real structured data even though retrieval had
nothing to answer with.

## Not Done (scoped out on purpose)

- **Feeding matched procedures into answer generation.** The bigger idea from the original
  research ("so 'how do I install G3' surfaces a real, gap-annotated procedure instead of
  prose reconstructed from chunks") needs procedure steps converted into evidence-shaped
  input for `AnswerGenerator`/GX10 synthesis, and needs to interact carefully with the
  already-sensitive evidence sufficiency gate. Real, valuable, and explicitly deferred as
  its own mission rather than risking the generation pipeline in this one.
- **`quality`/`validated` semantics.** The old `ProceduralMemory` had a `validated: bool`
  flag with no real meaning (never set to `True` outside tests); Process Intelligence's
  `quality` field (`unknown`/etc., driven by real extraction confidence) replaces it, but
  nothing yet uses `quality` to filter what gets surfaced to `find_procedure()` callers —
  worth revisiting once real corpus data populates it meaningfully.
- **Orphaned `procedural_memory` table**: not actively dropped (low-risk to leave — it was
  never written to except by tests, and no migration was needed since nothing depended on
  its data). If a real one exists in someone's local DB from before this mission, it's now
  simply unused.

## Recommended Next Mission

**Mission C** — wire `ProspectiveMemory` the same way (its `detect_reminder_request()`
already has working regex logic that just needs to be called from `ask()`), plus a new
`GET /api/tasks/pending` endpoint, which doesn't exist yet.

## Test Results

| Group | Result |
|-------|--------|
| `tests/test_agentic_sanjaya.py::TestProceduralMemoryWiring` (new, 4 tests) | **4/4 pass** |
| `tests/test_memory_foundation.py::TestProceduralMemory` (rewritten, 4 tests) | **4/4 pass** |
| `tests/test_agentic_sanjaya.py` (full file) | 8 failed → same 3 pre-existing corpus-dependent + `TestEpisodicMemoryWiring`/`TestProceduralMemoryWiring` all pass |
| `tests/test_process_intelligence.py` | 3 pre-existing failures, confirmed identical with this mission's changes stashed out — unrelated to `search_processes` |
| Live `/api/ask` with a seeded real process | Verified manually, see above |

## Files Changed

| File | Change |
|------|--------|
| `kurukshetra/process/intelligence.py` | New `search_processes()`; punctuation-safe keyword extraction |
| `kurukshetra/agent/memory_store.py` | `ProceduralMemory` rewritten as a Process Intelligence adapter; `store_procedure()` and its table removed |
| `kurukshetra/agent/orchestrator.py` | Wire procedure matching into `ask()`, additive-only |
| `command_center/backend/routers/chat.py` | Expose `matched_procedures` on `/api/ask` |
| `tests/test_memory_foundation.py` | `TestProceduralMemory` rewritten for the new adapter |
| `tests/test_agentic_sanjaya.py` | **New** `TestProceduralMemoryWiring` (4 tests) |
| `docs/MISSION_B_PROCEDURAL_MEMORY_ADAPTER.md` | **New** — this file |

## Not Committed

Awaiting approval.
