# Mission 3.48 — Knowledge Graph Quality / Brain Cleanup

## Executive Summary

Applied deterministic quality scoring to 4,679 graph entities. Identified 160 HIGH-quality organizational entities, 3,465 MEDIUM, 329 LOW, and 725 NOISE. Built 50 cross-team relationships from real evidence. SANJAYA now filters noise from entity-augmented retrieval.

## Before vs After

### Graph Entity Quality

| Label | Before | After | Notes |
|-------|--------|-------|-------|
| HIGH | unknown | **160** | Real systems, teams, processes |
| MEDIUM | unknown | **3,465** | Potentially relevant |
| LOW | unknown | **329** | Likely noise |
| NOISE | unknown | **725** | Stopwords, temp files, fragments |
| **Total** | 4,679 | **4,679** | No entities deleted |

### Noise Removed from Retrieval

| Category | Count | Examples |
|----------|-------|---------|
| Common English words | 63+ | "the", "this", "and", "update", "process" |
| Temp file entities | 29 | "tmpytu8qifn.txt", "doc.txt" |
| Sentence fragments | 265 | "This document covers the installation..." |
| Numeric-only | ~50 | "02375162", "2 weeks", "1 to 6" |
| **Total noise** | **725** | Excluded from entity-augmented search |

### Real Organizational Entities (HIGH Quality)

| Entity | Type | Evidence | Documents | Teams |
|--------|------|----------|-----------|-------|
| SPM | team | 135 | 33 | SPM |
| Datadog | system | 128 | 85 | multiple |
| G3 RMS | system | 125 | 34 | SPM, ICS |
| SFDC | system | 119 | 82 | IT, ICS, SDOPS |
| ICS | team | 117 | 81 | ICS |
| SDOPS | team | 105 | 13 | SDOPS |
| NGI | system | 94 | 79 | ICS |
| IT | team | 93 | 6 | IT |
| Property Management | property | 89 | 77 | multiple |
| property setup | property | 84 | 76 | multiple |
| HR | team | 78 | 4 | HR |
| Salesforce | system | 78 | 5 | SPM, SDOPS |
| CPM | team | 75 | 3 | CPM |

### Cross-Team Relationships (Evidence-Based)

| Relationship | Type | Evidence | Confidence |
|-------------|------|----------|------------|
| G3 RMS ↔ SPM | system_team | 1,070 | 1.0 |
| Datadog ↔ SDOPS | system_team | 297 | 1.0 |
| SFDC ↔ IT | system_team | 148 | 1.0 |
| Datadog ↔ ICS | system_team | 103 | 1.0 |
| NGI ↔ ICS | system_team | 100 | 1.0 |
| G3 RMS ↔ SFDC | system_system | 53 | 1.0 |
| SFDC ↔ SPM | system_team | 52 | 1.0 |
| SFDC ↔ SDOPS | system_team | 60 | 1.0 |

### Document Team Distribution

| Team | Documents |
|------|-----------|
| UNKNOWN | 304 |
| SPM | 122 |
| ICS | 95 |
| IT | 62 |
| ROA | 37 |
| SDOPS | 36 |
| HR | 28 |
| CPM | 8 |

## Test Results

| Suite | Count | Status |
|-------|-------|--------|
| test_entity_quality (NEW) | 18 | ✅ PASS |
| test_closed_loop_learning | 22 | ✅ PASS |
| test_learning_safety | 10 | ✅ PASS |
| test_memory_foundation | 28 | ✅ PASS |
| test_fabric_wiring | 8 | ✅ PASS |
| test_gx10_integration | 22 | ✅ PASS |
| test_identity_boundary | 32 | ✅ PASS |
| test_upload_ingestion | 20 | ✅ PASS (1 skipped) |
| **Total** | **160** | **✅ ALL PASS** |

## Quality Rules Implemented

1. **Stopword filter**: 150+ common English words excluded
2. **Temp file filter**: Regex patterns for tmp*.txt, doc.txt
3. **Numeric filter**: Numbers, date ranges, temporal expressions
4. **Sentence fragment filter**: Names > 50 chars
5. **Known entity whitelist**: 27 verified organizational entities
6. **Acronym bonus**: ALL CAPS names get quality boost
7. **Evidence bonus**: Entities with 10+ evidence get quality boost
8. **Type penalty**: "job" and "document" types get quality penalty
9. **Filtered retrieval**: Entity-augmented search only uses MEDIUM+ entities

## Files Changed

| File | Change |
|------|--------|
| `kurukshetra/graph/entity_quality.py` | **NEW** — Quality scoring and filtering |
| `kurukshetra/graph/cross_team.py` | **NEW** — Cross-team relationships and brain snapshot |
| `kurukshetra/agent/answer_generator.py` | Added quality filter to entity-augmented retrieval |
| `tests/test_entity_quality.py` | **NEW** — 18 tests |
| `docs/MISSION_3_48_KNOWLEDGE_GRAPH_QUALITY.md` | **NEW** — This report |

## Honest Assessment

### What Improved
- **Entity precision**: 725 noise entities excluded from retrieval
- **Cross-team understanding**: 50 evidence-based relationships built
- **Knowledge transparency**: Brain snapshot shows what SANJAYA actually knows
- **Retrieval quality**: Entity-augmented search uses only quality-scored entities

### What Remains Weak
- **304 documents have UNKNOWN team** — 44% of corpus lacks team classification
- **Entity extraction is still noisy** — the underlying extractor produces garbage; quality scoring filters it but doesn't fix the source
- **Many MEDIUM entities are sentence fragments** — e.g., "Template for G3 Property Management" scored 0.85 because it has high evidence, but it's a document title not a process name
- **Cross-team relationships lack source_document provenance** — the evidence count is accurate but the specific source document query needs refinement

### What SANJAYA Knows Today

**Teams:** SPM, ICS, IT, ROA, SDOPS, HR, CPM
**Systems:** G3 RMS, Datadog, SFDC, NGI, OHIP, FOLS, Demand360, Salesforce, Opera AGENT
**Cross-team:** G3 RMS ↔ SPM ↔ ICS ↔ SDOPS ↔ ROA ↔ IT
**Processes:** AMS Recoding, Property Management, Proactive Monitoring
**Documents:** 692 indexed, 49,546 chunks

### What SANJAYA Does NOT Know
- Why teams use specific systems (the "why" behind relationships)
- Process step sequences (only document mentions, not validated workflows)
- Temporal knowledge (what changed when)
- Which documents are current vs outdated
- Who owns specific decisions

## Status

**VALIDATED.** Entity quality scoring active, cross-team relationships built, brain snapshot functional. Not committed — awaiting approval.
