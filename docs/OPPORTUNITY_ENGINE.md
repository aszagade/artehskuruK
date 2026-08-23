# Opportunity Engine

Deterministic pattern analysis across enterprise systems. Discovers automation, monitoring, documentation, and risk opportunities. Never executes actions.

---

## Lifecycle

```
Enterprise Events (structured)
    |
    v
OpportunityRepository.insert_events()
    |
    v
OpportunityDetector.run()
    |
    +--[Automation]----------> repeated identical events (3+)
    +--[Monitoring]----------> errors without monitoring setup
    +--[Documentation]--------> config changes without docs
    +--[Process Improvement]--> cross-team friction signals
    +--[Knowledge Gap]--------> queries without documentation
    +--[Duplicate Work]------> same events across teams
    +--[Risk Detection]------> critical errors on production systems
    |
    v
OpportunityRepository.upsert_opportunity()
    |
    v
opportunity_store table (status: proposed)
    |
    v
Human Review -> approve / reject
```

---

## Categories

| Category | Signal | Example |
|----------|--------|---------|
| **Automation** | Same event 3+ times from same source/team | "G3 RMS timeout" alert fires 12 times daily |
| **Monitoring** | Error events with no monitoring setup | SPM team has errors but no Datadog monitors |
| **Documentation** | Config/process events without doc updates | Deployment happened but Confluence page not updated |
| **Process Improvement** | Same subject across 2+ teams | "Rate upload failure" affects both SPM and ICS |
| **Knowledge Gap** | Queries with no matching documentation | "CP-Admin config" searched 5 times, no docs exist |
| **Duplicate Work** | Same event type/subject across teams | Both SPM and SDOPS handle identical incidents |
| **Risk Detection** | Critical errors on production systems | SPM + ICS have critical failures (high severity) |

---

## Event Model

```python
@dataclass
class Event:
    event_id: str
    source: SourceSystem      # datadog, salesforce, confluence, teams, outlook, sql, smartsheet, internal
    event_type: str            # alert, error, config_change, search, query, deployment, etc.
    subject: str               # what the event is about
    team: str                  # affected team
    timestamp: str             # ISO timestamp
    details: str               # human-readable description
    source_url: str            # link to original event
    quantity: int              # for aggregated events
    metadata: dict             # extensible (severity, etc.)
```

---

## Opportunity Model

```python
@dataclass
class Opportunity:
    opportunity_id: str        # OPP-{CATEGORY}-{hash}
    title: str                 # human-readable title
    category: OpportunityCategory
    source_system: SourceSystem
    affected_team: str
    frequency: int             # events that triggered this
    evidence: str              # WHY this was detected (mandatory)
    confidence: float          # 0.0-1.0
    status: OpportunityStatus  # proposed, approved, rejected
    first_seen: str
    last_seen: str
    event_ids: list[str]       # source event IDs
    metadata: dict
```

---

## Schema

### opportunity_events
```sql
CREATE TABLE opportunity_events (
    event_id TEXT PRIMARY KEY,
    source TEXT,
    event_type TEXT,
    subject TEXT,
    team TEXT,
    timestamp TEXT,
    details TEXT,
    source_url TEXT,
    quantity INTEGER DEFAULT 1,
    metadata TEXT              -- JSON
);
```

### opportunity_store
```sql
CREATE TABLE opportunity_store (
    opportunity_id TEXT PRIMARY KEY,
    title TEXT,
    category TEXT,
    source_system TEXT,
    affected_team TEXT,
    frequency INTEGER,
    evidence TEXT,
    confidence DOUBLE,
    status TEXT DEFAULT 'proposed',
    first_seen TEXT,
    last_seen TEXT,
    event_ids TEXT,            -- JSON array
    metadata TEXT              -- JSON
);
```

---

## Detection Rules

### Automation Detection
- Groups events by (source, event_type, subject, team)
- Threshold: 3+ identical events
- Confidence: 0.5 + (count * 0.05), max 0.95

### Monitoring Detection
- Finds error/alert/failure events per team
- Checks if monitoring events exist for same team
- If no monitoring → creates opportunity

### Documentation Detection
- Finds config_change, process_update, deployment events
- Checks for corresponding document_update/wiki_edit events
- If no docs → creates opportunity

### Process Improvement Detection
- Groups events by subject
- If 2+ different teams reference same subject → cross-team friction
- Suggests shared runbook or RACI matrix

### Knowledge Gap Detection
- Groups search/query/question events by subject
- Checks if corresponding documentation exists
- If no docs + 2+ queries → knowledge gap

### Duplicate Work Detection
- Groups events by type + normalized subject
- If 2+ teams have same events → duplicate work
- Suggests unified solution

### Risk Detection
- Filters error/failure/incident/security events
- Applies severity threshold (critical/high) or team criticality (sdops, spm, ics)
- If 2+ risk events → creates risk opportunity

---

## Usage

### CLI Demo
```bash
python -m kurukshetra.opportunity.demo
```
Runs 22 sample events through all 7 detectors. Shows opportunities found.

### Programmatic
```python
from kurukshetra.opportunity.detector import OpportunityDetector
from kurukshetra.opportunity.models import Event, SourceSystem

# Insert events
repo = OpportunityRepository()
repo.insert_events([
    Event(
        event_id="EVT-001",
        source=SourceSystem.DATADOG,
        event_type="error",
        subject="G3 RMS timeout",
        team="spm",
        timestamp="2024-01-15T10:00:00Z",
        details="G3 RMS API timeout after 30s",
    ),
    # ... more events
])

# Run detection
detector = OpportunityDetector(repo)
result = detector.run()
print(f"Found {result.opportunities_found} opportunities")
```

---

## Validation

```bash
# Run 22 unit tests
python -m pytest tests/test_opportunity.py -v

# Expected: 22 passed
```

---

## What Opportunity Engine Does NOT Do

- Does not execute automations
- Does not modify RAG, Graph, SANJAYA, or SEAL
- Does not call any LLM
- Does not make decisions (only proposes)
- Does not connect to external systems (events must be inserted programmatically)
