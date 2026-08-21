# KURUKSHETRA Engineering Charter

## Identity

KURUKSHETRA is the enterprise AI command center for IDeaS Service Delivery.

SANJAYA is the communication and orchestration layer.
SEAL is the adaptive organizational learning framework.

The repository is the source of truth.

---

## Architecture First

- Preserve the existing modular architecture.
- Extend existing modules before creating new ones.
- Never rename or move files unless explicitly instructed.
- Never create duplicate implementations of existing functionality.
- Maintain backward compatibility whenever practical.

---

## Development Workflow

Every task must be suitable for a single Git commit.

Preferred scope:

- One responsibility
- 2–4 files modified
- Under ~300 lines of new code
- No unrelated refactoring

If a request exceeds this scope, propose phased implementation.

Never perform Git commits automatically.

Always suggest a Conventional Commit message.

---

## Code Standards

- Python 3.13
- Type hints required
- Dataclasses where appropriate
- Enum for constants
- Logging instead of print
- Configuration separated from code
- Public methods require docstrings

---

## Existing Stack

Use existing technologies unless instructed otherwise.

- DuckDB → persistence
- Hybrid Retrieval → BM25 + BGE-M3
- BGE Reranker → reranking
- SANJAYA → planner
- Executors → specialized tools

Do not introduce SQLite, Neo4j, or new databases without approval.

---

## Deliverables

After implementation always provide:

1. Files changed
2. What was implemented
3. Manual testing command
4. Suggested Conventional Commit