# Graph Quality Audit — Real Corpus

**Date:** 2026-08-24
**Corpus:** 23 documents from ICS/Omkar/Process Documents
**After cleanup:** 3,956 entities, 17,516 relationships, 8,309 evidence records

---

## Entity Distribution

| Type | Count | With Description |
|------|------:|:----------------:|
| knowledge_article | 2,163 | 100% |
| process | 836 | 100% |
| document | 375 | 100% |
| job | 220 | 100% |
| incident | 213 | 100% |
| configuration | 73 | 100% |
| client | 26 | 100% |
| system | 24 | 96% |
| property | 19 | 100% |
| team | 7 | 100% |

**Observation:** Knowledge articles dominate (55%). Processes (21%) are the second largest group. Systems (24 total) are underrepresented relative to the actual systems mentioned in the documents (G3 RMS, SFDC, NGI, Datadog, EDF, SFTP, etc.).

---

## Relationship Distribution

| Type | Count | Avg Confidence | Quality Assessment |
|------|------:|:--------------:|-------------------|
| generated_from | 5,146 | 0.350 | LOW — inferred co-occurrence |
| uses | 5,102 | 0.480 | LOW-MEDIUM — inferred co-occurrence |
| references | 3,331 | 0.706 | MEDIUM — direct text reference |
| contains | 2,160 | 1.000 | HIGH — document contains chunk |
| triggers | 652 | 0.350 | LOW — inferred co-occurrence |
| configures | 442 | 0.521 | MEDIUM — configuration relationship |
| owned_by | 376 | 0.900 | HIGH — team ownership |
| resolves | 329 | 0.700 | MEDIUM — incident resolution |

---

## Key Findings

### 1. High-Value Relationships (confidence >= 0.7)

**owned_by (376):** Document-to-team ownership. High confidence because team classification is deterministic.

**contains (2,160):** Document-to-chunk containment. Structural, always correct.

**resolves (329):** Document-to-incident resolution. Medium-high confidence from direct text mentions.

**references (3,331):** Document-to-process/system references. Medium confidence from direct pattern matches.

### 2. Low-Value Relationships (confidence < 0.5)

**generated_from (5,146):** Job-to-process inferred from co-occurrence. Low confidence (0.35). These are the most numerous but least reliable.

**uses (5,102):** Process-to-system inferred from co-occurrence. Low-medium confidence (0.48). More useful than generated_from but still inferred.

**triggers (652):** System-to-incident inferred from co-occurrence. Low confidence (0.35).

### 3. Evidence Coverage

- **100% of entities** have at least one evidence record
- Every relationship has at least one evidence source
- Evidence includes source document ID and source text snippet

### 4. Duplicate Relationships

**None found.** The deduplication cache works correctly.

### 5. Artifact Cleanup

After cleaning NaN/empty/newline entities:
- Entities: 5,056 → 3,956 (-1,100 artifacts)
- Relationships: 26,991 → 17,516 (-9,475 orphaned)
- Evidence: 11,738 → 8,309 (-3,429 orphaned)

---

## Quality Assessment

| Metric | Value | Assessment |
|--------|-------|-----------|
| Entity coverage | 100% | EXCELLENT |
| Evidence coverage | 100% | EXCELLENT |
| High-confidence relationships | 5,538 (32%) | GOOD |
| Low-confidence relationships | 10,145 (58%) | NEEDS IMPROVEMENT |
| Duplicate relationships | 0 | EXCELLENT |
| Artifact entities | 0 (after cleanup) | GOOD |

---

## Recommendations

1. **Filter low-confidence inferred relationships** — The 10,145 relationships with confidence < 0.5 are mostly noise from co-occurrence inference. Consider only persisting relationships with confidence >= 0.5.

2. **Expand SYSTEM_PATTERNS** — Only 24 system entities exist despite 23 documents mentioning many more systems (EDF, SFTP, BMR, CCFG, Optix, Delphi, OCIM, RPM, RSS, Datadog).

3. **Improve process extraction** — The 836 process entities include many low-quality extractions. The regex patterns capture too much text from spreadsheet cells.

4. **Graph is functional but noisy** — The quantity (17,516 relationships) exceeds quality. About 32% are high-confidence, 30% medium, and 38% low-confidence inferred relationships.
