# Mission 3.43 — SANJAYA Memory Foundation

## Objective

Implement the minimum necessary memory foundation so SANJAYA distinguishes between organizational knowledge, conversation context, procedures, future tasks, and model knowledge.

## Test Result

**629/629 tests pass, 0 failures** (including 28 new memory tests)

## Memory Architecture

### What Was Implemented

| Memory Type | Component | Storage | Purpose |
|-------------|-----------|---------|---------|
| **Working Memory** | `WorkingMemoryState` | In-memory | Current query, evidence, reasoning trace |
| **Episodic Memory** | `EpisodicMemory` | DuckDB | Past interactions, feedback, outcomes |
| **Semantic Memory** | `SemanticMemory` | Wraps existing graph | Teams, concepts, relationships, glossary |
| **Procedural Memory** | `ProceduralMemory` | DuckDB | Validated workflows from documents |
| **Prospective Memory** | `ProspectiveMemory` | DuckDB | Explicit future tasks/reminders |
| **External Memory** | Knowledge Fabric | Unchanged | Authoritative retrieval memory |
| **Parametric Memory** | GX10 model | Untouched | Pretrained model knowledge |

### What Was NOT Implemented (By Design)

- **Autonomous self-learning** — no automatic behavior changes
- **LLM fine-tuning** — parametric memory stays as-is
- **Memory consolidation** — not needed yet
- **Cross-session memory** — episodic memory persists, working memory is per-session

## Knowledge Source Attribution

Every answer now includes a `knowledge_source` field:

| Source | Meaning | When |
|--------|---------|------|
| `organization` | From ingested documents | Standard retrieval from Knowledge Fabric |
| `conversation` | From entity/graph lookup | Entity-augmented retrieval |
| `mixed` | Combination of both | Entity + document evidence |
| `model` | LLM synthesis with evidence | GX10-generated answer |
| `unknown` | Cannot determine | Abstention or error |

### Source Distinction Tests

SANJAYA now explicitly distinguishes:
- ✅ "I know this from the organization" → `organization` source
- ✅ "I remember this from our conversation" → `conversation` source
- ✅ "This is a procedure" → stored in ProceduralMemory
- ✅ "This is a future task" → stored in ProspectiveMemory
- ✅ "I do not have evidence" → abstained with `unknown` source
- ✅ "This is general model knowledge" → NOT used for org answers (parametric)

## Files Created/Modified

| File | Change |
|------|--------|
| `kurukshetra/agent/memory_store.py` | **NEW** — Complete memory foundation (6 components) |
| `kurukshetra/agent/answer_generator.py` | Added `knowledge_source` field + attribution method |
| `tests/test_memory_foundation.py` | **NEW** — 28 tests for all memory types |

## Memory Tables (DuckDB)

| Table | Purpose |
|-------|---------|
| `episodic_memory` | Past interactions (query, answer, feedback, sources) |
| `procedural_memory` | Validated workflows (name, steps, team, confidence) |
| `prospective_memory` | Future tasks/reminders (description, due, completed) |

## How Each Memory Type Is Used

### Working Memory (per-query)
```
Query arrives → start_query() → set evidence → add claims → record_episode()
```
Tracks the current reasoning process. Reset on each new query.

### Episodic Memory (persistent)
```
Answer generated → record_episode() → user feedback → record_feedback()
Next query → find_similar_queries() → inform retrieval
```
Learns from past interactions without modifying production behavior.

### Semantic Memory (read-only wrapper)
```
"What teams exist?" → get_teams()
"Is G3 known?" → knows("G3")
"What concepts does ICS have?" → get_team_concepts("ics")
```
Wraps existing graph/glossary with a clean interface.

### Procedural Memory (extracted from docs)
```
Document contains workflow → store_procedure()
"How do I install G3?" → find_procedure() → return steps
```
Extracts and stores validated procedures from authoritative documents.

### Prospective Memory (explicit only)
```
"Remind me to check G3 tomorrow" → detect_reminder_request() → add_task()
"Any pending tasks?" → get_pending_tasks()
"Done" → complete_task()
```
NEVER invents tasks. Only stores explicitly requested future actions.

## Security

- All memory operations respect existing visibility filtering
- Episodic memory stores only authorized evidence references
- Prospective tasks are user-scoped
- No autonomous behavior changes

## Not Committed

Awaiting approval.
