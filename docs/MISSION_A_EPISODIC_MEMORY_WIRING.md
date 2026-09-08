# Mission A — Wire Episodic Memory Into the Live Path

## Summary

Completes the "episodic memory" leg of Mission 3.43's memory foundation, which Mission 3.47
correctly labeled `PARTIAL` ("99 episodes recorded; not yet used for retrieval"). Tracing
every caller confirmed the real state was worse than "partial": `EpisodicMemory` and
`SANJAYAMemory` (`kurukshetra/agent/memory_store.py`) were never instantiated anywhere in
the live request path — only in `test_memory_foundation.py` and a few unrelated
identity/security tests. `command_center/backend/routers/chat.py`'s own docstring claimed
"3. EpisodicMemory (if applicable) — drives conversation memory" for `/api/feedback`, but
the code beneath it never touched `EpisodicMemory` at all. This mission makes that claim
true, end to end, for both `/api/ask` and `/api/feedback`.

## Design decisions (and what was deliberately NOT done)

- **Episodic memory is recall/audit only — it never adjusts retrieval or the answer.**
  Chunk-level score adjustment from feedback already works and is validated
  (Mission 3.47's A/B test: +55–68% on positive-feedback queries) via `FeedbackAwareRetriever`
  / `FeedbackLoop`. Making episodic memory *also* influence retrieval would create a second,
  overlapping learning mechanism with no clear boundary between them. Episodic memory's job
  here is narrower and genuinely missing: "has something like this been asked before, and
  what happened" — recall, not scoring. `test_episodic_recall_never_alters_the_answer`
  enforces this as an explicit regression guard.
- **Instantiated inside `AgenticSANJAYA`, not the API layer.** `SANJAYAMemory`'s original
  design already coupled query lifecycle to memory (`start_query()` etc.); the natural owner
  of "was this interaction recorded" is the orchestrator that runs the interaction, not the
  FastAPI handler. This also means any future caller of `AgenticSANJAYA.ask()` (not just
  `/api/ask`) gets episodic recording for free.
- **Defensive by construction, same pattern as `sufficiency_gate`.** `episodic_memory` is
  `None` if construction fails (matches the existing `try/except ImportError` pattern for
  `EvidenceSufficiencyGate` right above it in `__init__`); every call site checks for `None`
  and every DB operation is wrapped so a storage failure can never fail the actual answer.
- **`knowledge_source` string→enum mapping is defensive.** `AnswerGenerator._determine_knowledge_source()`
  can return `"mixed"`, which has no matching `KnowledgeSource` member — falls back to
  `KnowledgeSource.UNKNOWN` rather than raising. Not fixed at the source (adding a `MIXED`
  member is a separate, small decision affecting other code that reads `KnowledgeSource`)
  — flagged as a follow-up, not silently patched.
- **Did not touch `ProceduralMemory` or `ProspectiveMemory`.** Per the earlier research: these
  need a different fix shape (`ProceduralMemory` should wrap the already-mature Process
  Intelligence system rather than growing its own empty table; `ProspectiveMemory`'s
  `detect_reminder_request()` needs the same "actually call it from `/api/ask`" treatment as
  this mission gave episodic memory, plus a `GET /api/tasks/pending` endpoint that doesn't
  exist yet). Scoped out of Mission A on purpose — separate missions, separate review.

## What Changed

### `kurukshetra/agent/orchestrator.py`
- `AgenticResult` gained `episode_id: Optional[str]` and `recalled_episodes: list[dict]`.
- `AgenticSANJAYA.__init__` constructs `self.episodic_memory` (an `EpisodicMemory`),
  defensively — `None` on any failure, never raises.
- New `_recall_similar_episodes(query)`: calls `find_similar_queries()`, returns a list of
  small dicts (episode_id, query, answer_snippet, confidence, abstained, timestamp) or `[]`.
  Called once at the top of `ask()`, before retrieval — uses the original query, not a
  round-2 refined one.
- New `_record_episode(query, answer_result, evidence, duration_ms)`: maps
  `answer_result.knowledge_source` to `KnowledgeSource` (defensively), calls
  `EpisodicMemory.record_episode()`, returns the new `episode_id` or `None`. Called once at
  the very end of `ask()`, right before constructing the final `AgenticResult` — covers both
  the normal-generation path and the sufficiency-gate-abstain path, since both funnel through
  the same return statement.

### `command_center/backend/routers/chat.py`
- New `RecalledEpisodeResponse` model.
- `AskResponse` gained `episode_id: Optional[str]` and `recalled_episodes: list[RecalledEpisodeResponse]`,
  populated from `agentic_result` in `ask_evidence_grounded`.
- `FeedbackRequest` gained an optional `episode_id: Optional[str]`.
- `submit_feedback` now actually implements the "3. EpisodicMemory" step its own docstring
  already claimed: if `episode_id` is provided, calls `EpisodicMemory().record_feedback(...)`
  alongside (not instead of) the existing `FeedbackLoop` / `EvaluationSignalTracker` calls,
  wrapped defensively the same way step 2 already was.

### `tests/test_agentic_sanjaya.py`
New `TestEpisodicMemoryWiring` class, 6 tests, all using distinctive uuid-suffixed queries
so they pass regardless of corpus state or the shared DuckDB's history from other test runs:
episode recorded on both answer and abstain, recall empty for a novel query, recall
populated on an exact repeat, recall never changes the answer/confidence, and `ask()`
degrades gracefully with `episodic_memory = None`.

### `kurukshetra/embeddings/` + `.gitignore` (reapplied, by explicit request)
This session started from a full rollback to `e34f571` (a prior, separate session's work —
promptfoo eval harness, an async fix, and this same embeddings fix — was explicitly reverted
by request). The missing `kurukshetra/embeddings/` module blocks *all* imports of
`kurukshetra.retrieval`/`kurukshetra.agent`, including the pre-existing `test_agentic_sanjaya.py`
— there was no way to test Mission A without it. Recreated identically to the prior fix
(lazy `BGEEmbedding`, defensive `.embed()`) and root-anchored the `.gitignore` rule again,
with explicit confirmation before doing so. Everything else from the prior session (evals/,
the async event-loop fix) was left reverted, as originally requested.

## Known limitation (pre-existing, not introduced here)

`EpisodicMemory.find_similar_queries()` does naive `LIKE '%keyword%'` matching on words
longer than 3 characters, including common words like "what" — confirmed live: a query
about "quantum computing" got recalled as "similar" to an unrelated query purely because
both contained the word "what". This is the same limitation Mission 3.43 shipped with; not
addressed here (would mean either a stopword list or embedding-based similarity, both
independent follow-up decisions).

## Verification

Live end-to-end, via the real API against a running backend:
1. `POST /api/ask` with a distinctive query → response includes a real `episode_id`
   (`EP-...`) and `recalled_episodes` (correctly picked up two unrelated prior test queries
   via the known keyword-matching limitation above — expected, not a bug in this mission).
2. Repeating the exact same query → the second response's `recalled_episodes` includes the
   first call's `episode_id`.
3. `POST /api/feedback` with that `episode_id` → confirmed by direct DB read after stopping
   the server: `episodic_memory.feedback` for that row is now `True`.

## Test Results

| Group | Result |
|-------|--------|
| `tests/test_agentic_sanjaya.py::TestEpisodicMemoryWiring` (new, 6 tests) | **6/6 pass** |
| `tests/test_agentic_sanjaya.py` (full file) | 52 passed, 3 failed — all 3 pre-existing, corpus-dependent (confirmed by reproducing identically with this mission's changes stashed out) |
| `tests/test_memory_foundation.py` | All pass (some only after `initialize_schema()` was run — same pre-existing bootstrap gap noted in the reverted session's Mission 3.61) |
| Live `/api/ask` → `/api/feedback` round trip | Verified manually, see above |

## Files Changed

| File | Change |
|------|--------|
| `kurukshetra/agent/orchestrator.py` | Wire episodic recording + recall into `ask()` |
| `command_center/backend/routers/chat.py` | Expose `episode_id`/`recalled_episodes` on `/api/ask`; implement the episodic-feedback step `/api/feedback` already claimed |
| `tests/test_agentic_sanjaya.py` | **New** `TestEpisodicMemoryWiring` (6 tests) |
| `kurukshetra/embeddings/__init__.py`, `bge_m3.py` | **Reapplied** (see note above) |
| `.gitignore` | Reapplied root-anchoring fix for the same 5 patterns |
| `docs/MISSION_A_EPISODIC_MEMORY_WIRING.md` | **New** — this file |

## Recommended Next Missions

**Mission B** — `ProceduralMemory` as a Process Intelligence adapter (see prior research:
`kurukshetra/process/intelligence.py` already has 182 real processes / 1,569 steps; don't
grow the empty, parallel `procedural_memory` table).

**Mission C** — Wire `ProspectiveMemory` the same way this mission wired episodic: call
`detect_reminder_request()`/`add_task()` from `AgenticSANJAYA.ask()`, and add a
`GET /api/tasks/pending` endpoint (none exists today).

## Not Committed

Awaiting approval.
