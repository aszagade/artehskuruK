# Mission C — Prospective Memory: Fix, Wire, and Scope It Properly

## Summary

Completes the memory foundation trio (episodic → Mission A, procedural → Mission B,
prospective → this mission). Before wiring `ProspectiveMemory` into the live path, found and
fixed a real correctness bug in its reminder detector that would have made "wire it in" an
active regression rather than a neutral completion — then wired it in, and researched where
else in the product this concept legitimately applies (nowhere else, on purpose — see
"Where this does and doesn't belong" below).

## The bug found before wiring anything

`detect_reminder_request()`'s original pattern set matched **bare temporal words** ("next
time", "later", "tomorrow", "next week", "next month") and the **bare word "schedule"** as
sufficient triggers on their own — not just as part of an explicit reminder phrase.
Confirmed live, before any fix:

```
"What is the deployment schedule for G3?"        -> "for G3?"                (task created!)
"What is the maintenance window tomorrow?"        -> full query as task        (task created!)
"What happened later in the incident timeline?"   -> full query as task        (task created!)
```

This was harmless as long as the code was never called from the live path (Mission 3.47's
own status: `FOUNDATION — table exists; not yet wired`). Wiring it into `/api/ask` as
requested would have turned this into an active bug: a meaningful fraction of real
questions containing common words like "tomorrow" or "schedule" would spuriously create
tasks. Fixed the detector to require an explicit imperative/reminder phrase (`"remind me
to"`, `"remember to"`, `"don't forget to"`, `"set a reminder"`, `"schedule a reminder"`,
`"follow up on"`, `"check back on"`, `"come back to"`) — validated against 5 true-positive
and 5 false-positive cases (including the exact strings above) before touching any
production code path. This is the concrete enforcement of "never invents tasks"
(`ProspectiveMemory`'s own stated contract, and CLAUDE.md §4's broader "never fabricate"
governance rule) — a bare temporal word is not evidence of an explicit request; treating it
as one is exactly the kind of implicit inference that rule exists to prevent.

## Where this does and doesn't belong (the "wherever it's useful" research)

The product already has several other "things to resolve later" mechanisms. Before wiring
prospective memory anywhere, checked each one to avoid creating a sixth overlapping system:

| System | What it tracks | Who creates it |
|---|---|---|
| **SEAL pending glossary terms** (`GET /api/glossary/pending`) | Unrecognized terms found during ingestion | The system, from document content |
| **Knowledge Acquisition** (`kurukshetra/learning/acquisition.py`) | Evidence gaps SANJAYA couldn't answer from | The system, from retrieval insufficiency |
| **Process Gaps** (`kurukshetra/process/intelligence.py`) | Structural issues in extracted processes (no_owner, no_successor, ...) | The system, from process extraction quality |
| **Opportunity Engine** (`kurukshetra/opportunity/`) | Automation/monitoring/improvement suggestions | The system, proactively, human-approval-gated |
| **Prospective Memory** (this mission) | Explicit user-requested future reminders | **Only the user, explicitly** |

Prospective memory's genuine, non-overlapping niche is the one row where the *user* is the
author, not the system. Every other row is system-inferred from evidence/quality/gaps —
different governance shape entirely (those are meant to surface automatically; prospective
memory must never do that). Wiring it into any of the other four would blur exactly the
boundary CLAUDE.md's architectural layers rule protects ("never merge responsibilities
between layers") and would risk the same kind of over-triggering this mission just fixed.
**Conclusion: `/api/ask` is the one correct integration point** — it's SANJAYA's only
natural-language conversational surface, and the only place a user explicitly asks for
something in these terms.

## What Changed

### `kurukshetra/agent/memory_store.py`
`ProspectiveMemory.detect_reminder_request()` tightened as described above. Everything else
(`add_task`, `get_pending_tasks`, `complete_task`, the `prospective_memory` table) unchanged
— this class's storage layer was already correct; only the trigger was broken.

### `kurukshetra/agent/orchestrator.py`
Same wiring shape as Missions A and B, deliberately:
- `AgenticSANJAYA.__init__` constructs `self.prospective_memory` defensively.
- New `_detect_and_record_task(query)`: calls the (now-fixed) detector, records a task if
  triggered, returns it as a dict or `None`. Called once at the top of `ask()`.
- `AgenticResult` gained `created_task: Optional[dict]`.
- **Additive, non-influencing** — same contract as episodic recall and procedural matching:
  detecting/recording a task is a side effect, never alters retrieval, evidence, generation,
  or confidence. If the query also contained a real question, SANJAYA still answers (or
  abstains) exactly as it would have without this check —
  `test_reminder_creation_never_alters_the_answer` enforces this.

### `command_center/backend/routers/chat.py`
- `AskResponse` gained `created_task: Optional[CreatedTaskResponse]`.
- New: `GET /api/tasks/pending` (list pending tasks) and
  `POST /api/tasks/{task_id}/complete` (mark one done) — the first API surface this data has
  ever had. Deliberately no "create a task directly" endpoint: tasks are created *only* as a
  side effect of an explicit request through `/api/ask`, matching `ProspectiveMemory`'s
  existing "never invents/accepts arbitrary tasks" contract — there is no back door around
  the detector.

### Tests
- `tests/test_memory_foundation.py::TestProspectiveMemory` — added
  `test_no_false_positive_on_bare_temporal_words` (locks in the fix, using the exact strings
  that were confirmed broken) and `test_explicit_reminder_phrases_still_detected` (confirms
  the tightening didn't lose real detection capability). All 5 pre-existing tests still pass
  unchanged.
- `tests/test_agentic_sanjaya.py::TestProspectiveMemoryWiring` — 4 new tests: explicit
  reminder creates a task, an ordinary tricky question creates none, task creation never
  changes the answer, and graceful degradation when `prospective_memory` is unavailable.

## Verification

Live, end-to-end, via the real running API:
1. `POST /api/ask` with `"Remind me to check the Zzqlivetask4477 rollout status next week"`
   → `created_task` populated with the correct extracted description.
2. `POST /api/ask` with `"What is the deployment schedule for tomorrow?"` (the exact kind of
   query that used to false-positive) → `created_task: null` — confirms the fix holds live,
   not just in unit tests.
3. `GET /api/tasks/pending` → correctly lists all pending tasks.
4. `POST /api/tasks/{task_id}/complete` → task no longer appears in the pending list.

## Not Done (scoped out on purpose)

- **Detecting task completion from natural language** ("Done" → `complete_task()`, part of
  Mission 3.43's original vision). Explicit `POST /api/tasks/{id}/complete` by ID is the
  safe, sufficient path for now; inferring "the user means task X is done" from conversation
  is a separate, riskier NLP problem — same category of thing Missions A and B each
  deferred their bigger idea for.
- **`due_at` extraction** ("remind me tomorrow" → an actual timestamp). `add_task()` already
  accepts `due_at`, but nothing populates it from parsed natural language yet — dates stay
  `null` unless set programmatically. Worth a future mission once there's a concrete need to
  act on due dates (a digest, a proactive nudge, etc.) rather than just storing them.
- **Surfacing tasks proactively** (e.g. "you have 3 pending reminders" prepended to an
  unrelated answer). `GET /api/tasks/pending` makes this possible for a caller/UI to build,
  but nothing today calls it automatically — consistent with keeping `/api/ask` additive/
  non-invasive rather than growing new automatic behavior into it.

## Test Results

| Group | Result |
|-------|--------|
| `tests/test_agentic_sanjaya.py::TestProspectiveMemoryWiring` (new, 4 tests) | **4/4 pass** |
| `tests/test_memory_foundation.py::TestProspectiveMemory` (5 existing + 2 new) | **7/7 pass** |
| Full regression (`test_agentic_sanjaya.py` + `test_memory_foundation.py` + `test_process_intelligence.py`) | 89 passed, 6 failed — all 6 the same pre-existing corpus-dependent/extraction failures already confirmed unrelated in Missions A and B |
| Live `/api/ask` → task creation, false-positive guard, `/api/tasks/pending`, `/api/tasks/{id}/complete` | Verified manually, see above |

## Files Changed

| File | Change |
|------|--------|
| `kurukshetra/agent/memory_store.py` | Tightened `detect_reminder_request()` — fixes a real false-positive bug |
| `kurukshetra/agent/orchestrator.py` | Wire task detection into `ask()`, additive-only |
| `command_center/backend/routers/chat.py` | Expose `created_task` on `/api/ask`; new `GET /api/tasks/pending` and `POST /api/tasks/{id}/complete` |
| `tests/test_memory_foundation.py` | 2 new regression tests locking in the fix |
| `tests/test_agentic_sanjaya.py` | **New** `TestProspectiveMemoryWiring` (4 tests) |
| `docs/MISSION_C_PROSPECTIVE_MEMORY_WIRING.md` | **New** — this file |

## The memory foundation, now actually complete

With Missions A, B, and C, all three previously-"foundation only" memory types from
Mission 3.43 are wired into SANJAYA's live conversational path, each independently
verified live, each following the same deliberate contract: **additive to the answer, never
load-bearing for it, and gracefully absent if unavailable.** Episodic and procedural surface
context; prospective records explicit intent. None of them can change what SANJAYA answers
or how confident it is — that boundary was the one design principle carried consistently
across all three missions.

## Not Committed

Awaiting approval.
