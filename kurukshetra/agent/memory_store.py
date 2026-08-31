"""
SANJAYA Memory Foundation
==========================

Implements the seven memory categories mapped to real architectural needs:

1. WORKING MEMORY — current conversation state (extends ConversationMemory)
2. EPISODIC MEMORY — persistent interaction history (DuckDB)
3. SEMANTIC MEMORY — durable organizational knowledge (wraps existing graph)
4. PROCEDURAL MEMORY — validated workflows from documents
5. PROSPECTIVE MEMORY — explicit future tasks/reminders
6. EXTERNAL MEMORY — Knowledge Fabric (unchanged)
7. PARAMETRIC MEMORY — GX10 model knowledge (untouched)

Design principles:
- Do NOT create autonomous self-learning
- Do NOT change production behavior without evidence/approval
- SANJAYA must distinguish knowledge sources in answers
- Each memory type maps to an existing or minimal new component
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from kurukshetra.registry.database import get_connection


# ==================================================================
# Knowledge Source Attribution
# ==================================================================

class KnowledgeSource(Enum):
    """Where a piece of knowledge came from."""
    ORGANIZATION = "organization"     # From ingested documents (Knowledge Fabric)
    CONVERSATION = "conversation"     # From current conversation context
    PROCEDURE = "procedure"           # From validated workflow/procedure document
    EPISODIC = "episodic"             # From a previous interaction
    PROSPECTIVE = "prospective"       # From an explicit future task/reminder
    MODEL = "model"                   # From GX10's pretrained knowledge
    UNKNOWN = "unknown"               # Cannot determine source


@dataclass(slots=True)
class AttributedClaim:
    """A claim with its knowledge source clearly identified."""
    claim: str
    source: KnowledgeSource
    confidence: float  # 0.0 to 1.0
    evidence_ids: list[str] = field(default_factory=list)  # document/chunk IDs
    reasoning: str = ""  # Why this source attribution


# ==================================================================
# Working Memory — current conversation state
# ==================================================================

@dataclass
class WorkingMemoryState:
    """Current active conversation state."""
    current_query: str = ""
    retrieved_evidence: list[dict] = field(default_factory=list)
    active_claims: list[AttributedClaim] = field(default_factory=list)
    reasoning_trace: list[str] = field(default_factory=list)
    current_task: str = ""
    conversation_id: str = ""
    started_at: float = 0.0

    def reset(self) -> None:
        """Reset working memory for a new query."""
        self.current_query = ""
        self.retrieved_evidence = []
        self.active_claims = []
        self.reasoning_trace = []
        self.current_task = ""
        self.started_at = time.time()

    def add_reasoning_step(self, step: str) -> None:
        """Record a reasoning step."""
        self.reasoning_trace.append(f"[{len(self.reasoning_trace)+1}] {step}")

    def set_evidence(self, evidence: list[dict]) -> None:
        """Set the current retrieved evidence."""
        self.retrieved_evidence = evidence

    def add_claim(self, claim: AttributedClaim) -> None:
        """Add an attributed claim."""
        self.active_claims.append(claim)


# ==================================================================
# Episodic Memory — persistent interaction history
# ==================================================================

@dataclass(slots=True)
class Episode:
    """A single past interaction."""
    episode_id: str
    conversation_id: str
    query: str
    answer: str
    confidence: float
    abstained: bool
    evidence_doc_ids: list[str]
    knowledge_sources: list[str]  # KnowledgeSource values
    feedback: Optional[bool]  # True=correct, False=incorrect, None=no feedback
    user_id: str
    timestamp: float
    duration_ms: float


class EpisodicMemory:
    """
    Persistent memory of past SANJAYA interactions.

    Stores query→answer→feedback cycles in DuckDB for:
    - Learning from past interactions
    - Detecting repeated questions
    - Measuring answer quality over time
    """

    def __init__(self) -> None:
        self._ensure_table()

    def _ensure_table(self) -> None:
        conn = get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS episodic_memory (
                episode_id TEXT PRIMARY KEY,
                conversation_id TEXT,
                query TEXT,
                answer TEXT,
                confidence DOUBLE,
                abstained BOOLEAN,
                evidence_doc_ids TEXT,
                knowledge_sources TEXT,
                feedback BOOLEAN,
                user_id TEXT,
                timestamp DOUBLE,
                duration_ms DOUBLE
            )
        """)
        conn.close()

    def record_episode(
        self,
        query: str,
        answer: str,
        confidence: float,
        abstained: bool,
        evidence_doc_ids: list[str],
        knowledge_sources: list[KnowledgeSource],
        user_id: str = "system",
        duration_ms: float = 0.0,
        conversation_id: str = "",
    ) -> Episode:
        """Record a completed interaction."""
        episode = Episode(
            episode_id=f"EP-{uuid.uuid4().hex[:12]}",
            conversation_id=conversation_id,
            query=query,
            answer=answer[:500],  # Truncate for storage
            confidence=confidence,
            abstained=abstained,
            evidence_doc_ids=evidence_doc_ids,
            knowledge_sources=[s.value for s in knowledge_sources],
            feedback=None,
            user_id=user_id,
            timestamp=time.time(),
            duration_ms=duration_ms,
        )

        conn = get_connection()
        conn.execute(
            """INSERT INTO episodic_memory
            (episode_id, conversation_id, query, answer, confidence,
             abstained, evidence_doc_ids, knowledge_sources, feedback,
             user_id, timestamp, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                episode.episode_id, episode.conversation_id,
                episode.query, episode.answer, episode.confidence,
                episode.abstained, json.dumps(episode.evidence_doc_ids),
                json.dumps(episode.knowledge_sources), episode.feedback,
                episode.user_id, episode.timestamp, episode.duration_ms,
            ),
        )
        conn.close()
        return episode

    def record_feedback(self, episode_id: str, is_correct: bool) -> bool:
        """Record user feedback for an episode."""
        conn = get_connection()
        conn.execute(
            "UPDATE episodic_memory SET feedback = ? WHERE episode_id = ?",
            (is_correct, episode_id),
        )
        conn.close()
        return True

    def find_similar_queries(self, query: str, limit: int = 5) -> list[Episode]:
        """Find past episodes with similar queries."""
        conn = get_connection()
        # Simple keyword matching for now
        keywords = [w.lower() for w in query.split() if len(w) > 3]
        if not keywords:
            conn.close()
            return []

        conditions = " OR ".join(["LOWER(query) LIKE ?" for _ in keywords])
        params = [f"%{kw}%" for kw in keywords]

        rows = conn.execute(
            f"""SELECT episode_id, conversation_id, query, answer,
                confidence, abstained, evidence_doc_ids, knowledge_sources,
                feedback, user_id, timestamp, duration_ms
            FROM episodic_memory
            WHERE {conditions}
            ORDER BY timestamp DESC
            LIMIT ?""",
            params + [limit],
        ).fetchall()
        conn.close()

        return [self._row_to_episode(r) for r in rows]

    def get_recent_episodes(self, limit: int = 10) -> list[Episode]:
        """Get recent episodes."""
        conn = get_connection()
        rows = conn.execute(
            """SELECT episode_id, conversation_id, query, answer,
                confidence, abstained, evidence_doc_ids, knowledge_sources,
                feedback, user_id, timestamp, duration_ms
            FROM episodic_memory
            ORDER BY timestamp DESC
            LIMIT ?""",
            (limit,),
        ).fetchall()
        conn.close()
        return [self._row_to_episode(r) for r in rows]

    def get_feedback_stats(self) -> dict:
        """Get feedback statistics."""
        conn = get_connection()
        row = conn.execute(
            """SELECT
                COUNT(*) as total,
                SUM(CASE WHEN feedback = TRUE THEN 1 ELSE 0 END) as correct,
                SUM(CASE WHEN feedback = FALSE THEN 1 ELSE 0 END) as incorrect,
                SUM(CASE WHEN feedback IS NULL THEN 1 ELSE 0 END) as no_feedback,
                AVG(confidence) as avg_confidence
            FROM episodic_memory"""
        ).fetchone()
        conn.close()
        return {
            "total": row[0], "correct": row[1], "incorrect": row[2],
            "no_feedback": row[3], "avg_confidence": row[4],
        }

    def _row_to_episode(self, row) -> Episode:
        return Episode(
            episode_id=row[0], conversation_id=row[1],
            query=row[2], answer=row[3], confidence=row[4],
            abstained=row[5], evidence_doc_ids=json.loads(row[6] or "[]"),
            knowledge_sources=json.loads(row[7] or "[]"),
            feedback=row[8], user_id=row[9],
            timestamp=row[10], duration_ms=row[11],
        )


# ==================================================================
# Semantic Memory — organizational knowledge wrapper
# ==================================================================

class SemanticMemory:
    """
    Durable organizational knowledge: concepts, teams, relationships.

    Wraps the existing Knowledge Graph (graph_entities, graph_relationships,
    graph_evidence, glossary) to provide a clean semantic memory interface.
    """

    def get_known_concepts(self, concept_type: Optional[str] = None) -> list[dict]:
        """Get known organizational concepts."""
        conn = get_connection()
        if concept_type:
            rows = conn.execute(
                """SELECT ge.name, ge.entity_type, ge.description, gem.team_id
                FROM graph_entities ge
                LEFT JOIN graph_entity_meta gem ON ge.id = gem.entity_id
                WHERE ge.entity_type = ?
                ORDER BY ge.name""",
                (concept_type,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT ge.name, ge.entity_type, ge.description, gem.team_id
                FROM graph_entities ge
                LEFT JOIN graph_entity_meta gem ON ge.id = gem.entity_id
                ORDER BY ge.name"""
            ).fetchall()
        conn.close()
        return [{"name": r[0], "type": r[1], "description": r[2], "team": r[3]} for r in rows]

    def get_teams(self) -> list[dict]:
        """Get known organizational teams."""
        conn = get_connection()
        rows = conn.execute(
            """SELECT DISTINCT team_owner, COUNT(*) as doc_count
            FROM documents
            WHERE team_owner IS NOT NULL AND team_owner != '' AND team_owner != 'UNKNOWN'
            GROUP BY team_owner
            ORDER BY doc_count DESC"""
        ).fetchall()
        conn.close()
        return [{"team": r[0], "document_count": r[1]} for r in rows]

    def get_team_concepts(self, team: str) -> list[dict]:
        """Get concepts associated with a team."""
        conn = get_connection()
        rows = conn.execute(
            """SELECT ge.name, ge.entity_type
            FROM graph_entities ge
            JOIN graph_entity_meta gem ON ge.id = gem.entity_id
            WHERE gem.team_id = ?
            ORDER BY ge.name""",
            (team.lower(),),
        ).fetchall()
        conn.close()
        return [{"name": r[0], "type": r[1]} for r in rows]

    def get_cross_team_concepts(self) -> list[dict]:
        """Get concepts that belong to multiple teams."""
        conn = get_connection()
        rows = conn.execute(
            """SELECT ge.name, ge.entity_type,
                GROUP_CONCAT(DISTINCT gem.team_id) as teams,
                COUNT(DISTINCT gem.team_id) as team_count
            FROM graph_entities ge
            JOIN graph_entity_meta gem ON ge.id = gem.entity_id
            GROUP BY ge.name, ge.entity_type
            HAVING COUNT(DISTINCT gem.team_id) > 1
            ORDER BY team_count DESC"""
        ).fetchall()
        conn.close()
        return [{"name": r[0], "type": r[1], "teams": r[2], "team_count": r[3]} for r in rows]

    def get_glossary(self) -> list[dict]:
        """Get confirmed glossary terms."""
        conn = get_connection()
        rows = conn.execute(
            "SELECT term, definition, confirmed FROM glossary ORDER BY term"
        ).fetchall()
        conn.close()
        return [{"term": r[0], "definition": r[1], "confirmed": r[2]} for r in rows]

    def knows(self, concept: str) -> bool:
        """Check if SANJAYA knows about a concept."""
        conn = get_connection()
        row = conn.execute(
            "SELECT COUNT(*) FROM graph_entities WHERE LOWER(name) = LOWER(?)",
            (concept,),
        ).fetchone()
        conn.close()
        return row[0] > 0


# ==================================================================
# Procedural Memory — validated workflows
# ==================================================================

class ProceduralMemory:
    """
    Validated organizational workflows and procedures.

    Extracts and stores reusable procedures from authoritative documents.
    Procedures are extracted during ingestion from documents that contain
    workflow/process steps.
    """

    def __init__(self) -> None:
        self._ensure_table()

    def _ensure_table(self) -> None:
        conn = get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS procedural_memory (
                procedure_id TEXT PRIMARY KEY,
                name TEXT,
                description TEXT,
                source_document_id TEXT,
                source_path TEXT,
                team TEXT,
                steps TEXT,
                validated BOOLEAN DEFAULT FALSE,
                confidence DOUBLE DEFAULT 0.0,
                created_at DOUBLE,
                updated_at DOUBLE
            )
        """)
        conn.close()

    def store_procedure(
        self,
        name: str,
        description: str,
        source_document_id: str,
        source_path: str,
        team: str,
        steps: list[str],
        validated: bool = False,
        confidence: float = 0.5,
    ) -> str:
        """Store a procedure extracted from a document."""
        proc_id = f"PROC-{uuid.uuid4().hex[:12]}"
        now = time.time()
        conn = get_connection()
        conn.execute(
            """INSERT OR REPLACE INTO procedural_memory
            (procedure_id, name, description, source_document_id, source_path,
             team, steps, validated, confidence, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (proc_id, name, description, source_document_id, source_path,
             team, json.dumps(steps), validated, confidence, now, now),
        )
        conn.close()
        return proc_id

    def find_procedure(self, query: str) -> list[dict]:
        """Find procedures matching a query."""
        conn = get_connection()
        keywords = [w.lower() for w in query.split() if len(w) > 3]
        if not keywords:
            conn.close()
            return []

        conditions = " OR ".join(["LOWER(name) LIKE ? OR LOWER(description) LIKE ?" for _ in keywords])
        params = []
        for kw in keywords:
            params.extend([f"%{kw}%", f"%{kw}%"])

        rows = conn.execute(
            f"""SELECT procedure_id, name, description, source_document_id,
                team, steps, validated, confidence
            FROM procedural_memory
            WHERE {conditions}
            ORDER BY confidence DESC
            LIMIT 5""",
            params,
        ).fetchall()
        conn.close()
        return [
            {"id": r[0], "name": r[1], "description": r[2],
             "source": r[3], "team": r[4], "steps": json.loads(r[5] or "[]"),
             "validated": r[6], "confidence": r[7]}
            for r in rows
        ]

    def get_all_procedures(self) -> list[dict]:
        """Get all stored procedures."""
        conn = get_connection()
        rows = conn.execute(
            """SELECT procedure_id, name, description, source_document_id,
                team, steps, validated, confidence
            FROM procedural_memory
            ORDER BY confidence DESC"""
        ).fetchall()
        conn.close()
        return [
            {"id": r[0], "name": r[1], "description": r[2],
             "source": r[3], "team": r[4], "steps": json.loads(r[5] or "[]"),
             "validated": r[6], "confidence": r[7]}
            for r in rows
        ]


# ==================================================================
# Prospective Memory — future tasks/reminders
# ==================================================================

@dataclass(slots=True)
class FutureTask:
    """An explicitly requested future task or reminder."""
    task_id: str
    description: str
    requested_by: str
    created_at: float
    due_at: Optional[float]
    completed: bool
    completed_at: Optional[float]
    source_query: str  # The query that requested this task


class ProspectiveMemory:
    """
    Manages explicitly requested future tasks and reminders.

    CRITICAL: This memory NEVER invents tasks. It only stores tasks
    that a user has explicitly requested.
    """

    def __init__(self) -> None:
        self._ensure_table()

    def _ensure_table(self) -> None:
        conn = get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS prospective_memory (
                task_id TEXT PRIMARY KEY,
                description TEXT,
                requested_by TEXT,
                created_at DOUBLE,
                due_at DOUBLE,
                completed BOOLEAN DEFAULT FALSE,
                completed_at DOUBLE,
                source_query TEXT
            )
        """)
        conn.close()

    def add_task(
        self,
        description: str,
        requested_by: str = "user",
        due_at: Optional[float] = None,
        source_query: str = "",
    ) -> FutureTask:
        """Add an explicitly requested future task."""
        task = FutureTask(
            task_id=f"TASK-{uuid.uuid4().hex[:12]}",
            description=description,
            requested_by=requested_by,
            created_at=time.time(),
            due_at=due_at,
            completed=False,
            completed_at=None,
            source_query=source_query,
        )
        conn = get_connection()
        conn.execute(
            """INSERT INTO prospective_memory
            (task_id, description, requested_by, created_at, due_at,
             completed, completed_at, source_query)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (task.task_id, task.description, task.requested_by,
             task.created_at, task.due_at, task.completed,
             task.completed_at, task.source_query),
        )
        conn.close()
        return task

    def get_pending_tasks(self) -> list[FutureTask]:
        """Get all pending (not completed) tasks."""
        conn = get_connection()
        rows = conn.execute(
            """SELECT task_id, description, requested_by, created_at,
                due_at, completed, completed_at, source_query
            FROM prospective_memory
            WHERE completed = FALSE
            ORDER BY created_at DESC"""
        ).fetchall()
        conn.close()
        return [self._row_to_task(r) for r in rows]

    def complete_task(self, task_id: str) -> bool:
        """Mark a task as completed."""
        conn = get_connection()
        conn.execute(
            "UPDATE prospective_memory SET completed = TRUE, completed_at = ? WHERE task_id = ?",
            (time.time(), task_id),
        )
        conn.close()
        return True

    def detect_reminder_request(self, query: str) -> Optional[str]:
        """Detect if a query is requesting a future reminder/task."""
        import re
        reminder_patterns = [
            re.compile(r"\b(remind me|remember to|don't forget|schedule|set a reminder)\b", re.IGNORECASE),
            re.compile(r"\b(next time|later|tomorrow|next week|next month)\b", re.IGNORECASE),
            re.compile(r"\b(follow up|check back|come back to)\b", re.IGNORECASE),
        ]
        for pattern in reminder_patterns:
            if pattern.search(query):
                # Extract the task description
                task_match = re.search(
                    r"(?:remind me to|remember to|don't forget to|schedule)\s+(.+?)(?:\.|$)",
                    query, re.IGNORECASE,
                )
                if task_match:
                    return task_match.group(1).strip()
                return query  # Use full query as task description
        return None

    def _row_to_task(self, row) -> FutureTask:
        return FutureTask(
            task_id=row[0], description=row[1], requested_by=row[2],
            created_at=row[3], due_at=row[4], completed=row[5],
            completed_at=row[6], source_query=row[7],
        )


# ==================================================================
# Unified Memory Interface
# ==================================================================

class SANJAYAMemory:
    """
    Unified memory interface for SANJAYA.

    Provides a single entry point to all memory types with
    knowledge-source attribution.
    """

    def __init__(self) -> None:
        self.working = WorkingMemoryState()
        self.episodic = EpisodicMemory()
        self.semantic = SemanticMemory()
        self.procedural = ProceduralMemory()
        self.prospective = ProspectiveMemory()

    def start_query(self, query: str, conversation_id: str = "") -> None:
        """Initialize working memory for a new query."""
        self.working.reset()
        self.working.current_query = query
        self.working.conversation_id = conversation_id
        self.working.started_at = time.time()

        # Check for prospective memory triggers
        task_desc = self.prospective.detect_reminder_request(query)
        if task_desc:
            self.prospective.add_task(
                description=task_desc,
                source_query=query,
            )
            self.working.add_reasoning_step(
                f"Detected future task request: {task_desc}"
            )

        # Check episodic memory for similar past queries
        similar = self.episodic.find_similar_queries(query, limit=3)
        if similar:
            self.working.add_reasoning_step(
                f"Found {len(similar)} similar past interactions"
            )

    def record_evidence(self, evidence: list[dict]) -> None:
        """Record retrieved evidence in working memory."""
        self.working.set_evidence(evidence)
        self.working.add_reasoning_step(
            f"Retrieved {len(evidence)} evidence items from Knowledge Fabric"
        )

    def add_claim(self, claim: str, source: KnowledgeSource,
                  confidence: float, evidence_ids: list[str] = None) -> None:
        """Add an attributed claim to working memory."""
        self.working.add_claim(AttributedClaim(
            claim=claim,
            source=source,
            confidence=confidence,
            evidence_ids=evidence_ids or [],
        ))

    def record_episode(
        self,
        answer: str,
        confidence: float,
        abstained: bool,
        user_id: str = "system",
    ) -> None:
        """Record the completed interaction as an episode."""
        evidence_doc_ids = list(set(
            e.get("document_id", "") for e in self.working.retrieved_evidence
        ))
        sources = list(set(
            c.source.value for c in self.working.active_claims
        ))

        duration_ms = (time.time() - self.working.started_at) * 1000

        self.episodic.record_episode(
            query=self.working.current_query,
            answer=answer[:500],
            confidence=confidence,
            abstained=abstained,
            evidence_doc_ids=evidence_doc_ids,
            knowledge_sources=[KnowledgeSource(s) for s in sources] if sources else [KnowledgeSource.ORGANIZATION],
            user_id=user_id,
            duration_ms=duration_ms,
            conversation_id=self.working.conversation_id,
        )

    def get_knowledge_source_summary(self) -> dict:
        """Get a summary of what knowledge sources contributed to the current answer."""
        sources = {}
        for claim in self.working.active_claims:
            src = claim.source.value
            if src not in sources:
                sources[src] = {"count": 0, "avg_confidence": 0.0, "claims": []}
            sources[src]["count"] += 1
            sources[src]["avg_confidence"] += claim.confidence
            sources[src]["claims"].append(claim.claim[:100])

        for src in sources:
            if sources[src]["count"] > 0:
                sources[src]["avg_confidence"] /= sources[src]["count"]

        return sources
