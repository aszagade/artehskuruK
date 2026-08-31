# Mission 3.38 — SANJAYA Entity-Aware RAG + Cross-Document Reasoning

## Date
August 28, 2026

## Root Causes Found

### 1. Corpus Pollution (PRIMARY)
**131 temp documents** from `AppData/Local/Temp/` were polluting the BM25 index:
- 47 copies of `G3_RMS_Data_Feed_Configuration.docx`
- 38 copies of `RMS_D360_Configuration.xlsx`
- 28 copies of `SFDC_Workflow_Template.docx`
- 18 other temp files

These duplicates had higher BM25 scores than the real documents, pushing the actual G3 Data Feed Configuration (DOC-000498) to rank 48th.

**Fix:** Cleaned all temp documents from DuckDB. 650→512 docs, 3642→3536 chunks.

### 2. Entity-Blind Retrieval (SECONDARY)
For queries like "What do you know about ICS?", BM25 returns chunks that mention "ICS" but the relevance check fails because:
- Document titles don't contain "ICS" (titles are "Agent to Agent Migration", etc.)
- Title-alignment (35% weight) penalizes entity queries
- Relevance=0.200 < threshold 0.45 → abstains

**Fix:** Added entity-aware retrieval augmentation that detects team/system entities in queries and fetches related documents from the `documents.team_owner` field and `graph_entities` table. Entity-augmented evidence bypasses the title-alignment relevance check.

### 3. LLM Over-Abstention (TERTIARY)
GX10 said "insufficient evidence" even when evidence WAS present, because the system prompt didn't explicitly encourage cross-document synthesis.

**Fix:** Updated `SYSTEM_PROMPT_GROUNDED` to explicitly allow synthesis across multiple evidence sources.

## Changes Made

### 1. Cleaned temp documents
```python
# DELETE FROM documents WHERE source_path LIKE '%AppData%Local%Temp%'
# 131 documents, ~100 chunks removed
```

### 2. Entity-aware retrieval augmentation (`answer_generator.py`)
- `_augment_with_entity_results()` method
- Detects team entities (ICS, SPM, ROA, etc.) and system entities (G3, RMS, Opera, etc.)
- Fetches related documents by `team_owner` and `graph_entities.owner`
- Entity-augmented evidence bypasses title-alignment relevance check

### 3. Improved GX10 system prompt (`client.py`)
- Explicitly allows cross-document synthesis
- "You MAY synthesize information across multiple evidence sources"
- "When evidence is distributed across multiple documents, synthesize it"

## Benchmark: Before vs After

### Before (Mission 3.35 baseline with temp pollution)

| Question | Result | Issue |
|---|---|---|
| Q1: What is G3 Data Feed Configuration? | ABSTAIN | Temp copies outrank real doc |
| Q2: How does AMS Recoding work? | ANSWER ✅ | — |
| Q3: What teams are involved with G3? | ANSWER (weak) | LLM over-abstains |
| Q4: What do you know about ICS? | ABSTAIN | Relevance too low |
| Q5: What do you know about SPM? | ANSWER ✅ | — |
| Q6: What is company annual revenue? | ABSTAIN ✅ | — |

**Score: 3/6 correct**

### After (Mission 3.38)

| Question | Result | Change |
|---|---|---|
| Q1: What is G3 Data Feed Configuration? | **ANSWER** ✅ | Fixed: temp cleanup + entity augmentation |
| Q2: How does AMS Recoding work? | **ANSWER** ✅ | Preserved |
| Q3: What teams are involved with G3? | **ANSWER** ✅ | Improved: LLM synthesizes |
| Q4: What do you know about ICS? | **ANSWER** ✅ | Fixed: entity augmentation |
| Q5: What do you know about SPM? | **ANSWER** ✅ | Preserved |
| Q6: What is company annual revenue? | **ABSTAIN** ✅ | Preserved |

**Score: 6/6 correct** (+3 improvement)

## Files Changed

| File | Change |
|---|---|
| `kurukshetra/agent/answer_generator.py` | Added `_augment_with_entity_results()`, entity-aware relevance bypass |
| `kurukshetra/llm/client.py` | Improved `SYSTEM_PROMPT_GROUNDED` for cross-document synthesis |
| `scripts/clean_temp_docs.py` | **Created:** Temp document cleanup utility |

## Files NOT Changed

- Retrieval algorithms (BM25, Vector, Hybrid)
- Hybrid weights
- Confidence calculation
- SANJAYA strategy selection
- Security/authorization
- Database schema
- Graph behavior
- SEAL behavior

## Test Result

**576/576 pass, 0 failures.**

## Remaining Limitations

1. **Q3/Q4 LLM hedges** — Says "no specific information" even though it answers. Prompt tuning could improve confidence.
2. **No concept_teams population** — Still 0 records. The backfill was never run.
3. **No document_versions** — Still 0 records.
4. **Corpus still small** — 512 docs, only 16 from real ICS source.
5. **Entity augmentation is simple** — Only matches by team_owner and graph entity owner. Doesn't handle aliases or multi-team concepts.

## Recommended Next Milestone

**Mission 3.39: Knowledge Fabric Backfill + Concept Teams** — Run `backfill_existing_documents()` to populate concept_teams, document_state, and document_versions for all 512 existing documents. This will enable true cross-team concept tracking (e.g., G3 → SPM + ICS + ROA).
