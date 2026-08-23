# SEAL — Self-Evolving Adaptive Learning

Human-in-the-loop learning system. Processes unknown terms discovered during ingestion and presents them for human definition.

---

## Design Principles

1. **Never overwrite original documents.** SEAL stores knowledge as overlay decisions.
2. **All learning is human-verified.** No auto-acceptance, no LLM guessing.
3. **Decisions carry provenance.** Who decided, when, from which documents.
4. **Decisions can be superseded but never deleted.** Full audit trail.

---

## Lifecycle

```
Document Ingestion
    |
    v
GlossaryManager.detect_unknown_terms()
    |
    v
unknown_terms table (status: pending)
    |
    v
InterviewSession.run() (python sanjaya_developer.py)
    |
    +--[answer]--> DecisionStore.record() + GlossaryManager.confirm_term()
    |                 -> seal_decisions table
    |                 -> glossary table
    |
    +--[skip]----> GlossaryManager.reject_term()
    |                 -> unknown_terms.status = "rejected"
    |
    +--[ambiguous]-> term stays pending for future review
    |
    v
Session Summary (answered / skipped / ambiguous)
```

---

## Components

### UnknownLoader (`seal/unknowns.py`)

Loads pending unknown terms from DuckDB and enriches with evidence:

- **Documents:** Which documents contain this term
- **Graph entities:** Matching entities in the Knowledge Graph
- **Similar glossary terms:** Existing glossary entries that partially match

```python
from kurukshetra.seal.unknowns import UnknownLoader

loader = UnknownLoader()
terms = loader.load_pending()  # List[UnknownTermWithEvidence]
single = loader.load_one("CP-Admin")
count = loader.count_pending()
```

### DecisionStore (`seal/decisions.py`)

Persists human-verified answers:

```python
from kurukshetra.seal.decisions import DecisionStore

store = DecisionStore()
decision = store.record(
    term="CP-Admin",
    definition="Configuration parameter admin interface for G3 RMS",
    category="glossary",
    source_documents=["DOC-001", "DOC-042"],
    decided_by="developer",
)
# decision.confidence == 1.0 (human-verified)
```

### InterviewSession (`seal/interview.py`)

Interactive Q&A loop:

```python
from kurukshetra.seal.interview import InterviewSession

session = InterviewSession()
stats = session.run()
# stats = {"total": 15, "answered": 8, "skipped": 5, "ambiguous": 2}
```

---

## CLI

```bash
# Show statistics (pending terms, total decisions)
python sanjaya_developer.py --stats

# Inspect a specific term with evidence
python sanjaya_developer.py --term "CP-Admin"

# Run interactive interview session
python sanjaya_developer.py
```

### Interactive Commands

| Input | Action |
|-------|--------|
| `[definition text]` | Store as glossary entry (confidence 1.0) |
| `s` | Skip term (mark rejected, will not appear again) |
| `a` | Mark ambiguous (stays pending for future review) |
| `q` | Quit session |
| `[enter]` | Empty = skip |

---

## Schema

### seal_decisions
```sql
CREATE TABLE seal_decisions (
    decision_id TEXT PRIMARY KEY,     -- DEC-{timestamp}
    term TEXT,                        -- the unknown term
    definition TEXT,                  -- human-provided definition
    category TEXT,                    -- glossary, process, correction, clarification
    source_term TEXT,                 -- the term that triggered this decision
    source_documents TEXT,            -- JSON array of document IDs
    decided_by TEXT,                  -- human identifier
    decided_at TIMESTAMP,             -- when the decision was made
    confidence DOUBLE,                -- always 1.0 for human-verified
    status TEXT DEFAULT 'active'      -- active, superseded
);
```

### unknown_terms (used by SEAL)
```sql
CREATE TABLE unknown_terms (
    term TEXT PRIMARY KEY,
    status TEXT DEFAULT 'pending',    -- pending, confirmed, rejected
    occurrence_count INTEGER,
    context_snippet TEXT,
    suggested_category TEXT,
    first_seen_doc TEXT,
    created_at TEXT
);
```

### glossary (written by SEAL)
```sql
CREATE TABLE glossary (
    term TEXT PRIMARY KEY,
    definition TEXT,
    category TEXT,
    confidence DOUBLE,                -- 1.0 for human-verified
    source TEXT,                      -- 'seal_interview' or 'auto'
    created_at TEXT,
    updated_at TEXT
);
```

---

## Integration Points

| System | Connection |
|--------|-----------|
| **GlossaryManager** | SEAL confirms/rejects terms into the glossary |
| **GraphRegistry** | Confirmed terms create KNOWLEDGE_ARTICLE entities |
| **SANJAYA** | Glossary improves intent classification accuracy |
| **Opportunity Engine** | Unknown term frequency signals knowledge gaps |

---

## What SEAL Does NOT Do

- Does not auto-define terms (human provides all definitions)
- Does not modify original documents
- Does not make retrieval decisions
- Does not execute any actions
- Does not call any LLM
