"""
Automated Improvement Pipeline
==============================

Generates improvement proposals from data analysis and tracks
implementation status. Human approval required before changes.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from kurukshetra.registry.database import get_connection


class ProposalStatus(Enum):
    """Status of an improvement proposal."""
    PROPOSED = "proposed"
    APPROVED = "approved"
    IMPLEMENTED = "implemented"
    REJECTED = "rejected"


class ProposalCategory(Enum):
    """Categories of improvement proposals."""
    CHUNKING = "chunking"
    RETRIEVAL = "retrieval"
    INGESTION = "ingestion"
    GLOSSARY = "glossary"
    GRAPH = "graph"
    AGENT = "agent"


@dataclass(slots=True)
class ImprovementProposal:
    """A proposed improvement with implementation details."""
    proposal_id: str
    title: str
    description: str
    category: ProposalCategory
    priority: str
    status: ProposalStatus
    evidence: dict
    action_steps: list[str]
    created_at: str
    implemented_at: Optional[str] = None


class ImprovementPipeline:
    """
    Manages improvement proposals from discovery to implementation.
    """

    def __init__(self) -> None:
        self._ensure_table()

    def _ensure_table(self) -> None:
        conn = get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS improvement_proposals (
                proposal_id TEXT PRIMARY KEY,
                title TEXT,
                description TEXT,
                category TEXT,
                priority TEXT,
                status TEXT,
                evidence TEXT,
                action_steps TEXT,
                created_at TIMESTAMP,
                implemented_at TIMESTAMP
            )
        """)
        conn.close()

    def create_proposal(
        self,
        title: str,
        description: str,
        category: ProposalCategory,
        priority: str = "medium",
        evidence: Optional[dict] = None,
        action_steps: Optional[list[str]] = None,
    ) -> ImprovementProposal:
        """Create a new improvement proposal."""
        proposal_id = f"PROP-{int(time.time())}"
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        proposal = ImprovementProposal(
            proposal_id=proposal_id,
            title=title,
            description=description,
            category=category,
            priority=priority,
            status=ProposalStatus.PROPOSED,
            evidence=evidence or {},
            action_steps=action_steps or [],
            created_at=timestamp,
        )

        conn = get_connection()
        conn.execute(
            """
            INSERT INTO improvement_proposals
            (proposal_id, title, description, category, priority, status,
             evidence, action_steps, created_at, implemented_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                proposal_id,
                title,
                description,
                category.value,
                priority,
                ProposalStatus.PROPOSED.value,
                json.dumps(evidence or {}),
                json.dumps(action_steps or []),
                timestamp,
            ),
        )
        conn.close()

        return proposal

    def approve_proposal(self, proposal_id: str) -> None:
        """Approve a proposal for implementation."""
        conn = get_connection()
        conn.execute(
            "UPDATE improvement_proposals SET status = ? WHERE proposal_id = ?",
            (ProposalStatus.APPROVED.value, proposal_id),
        )
        conn.close()

    def implement_proposal(self, proposal_id: str) -> None:
        """Mark a proposal as implemented."""
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        conn = get_connection()
        conn.execute(
            """
            UPDATE improvement_proposals
            SET status = ?, implemented_at = ?
            WHERE proposal_id = ?
            """,
            (ProposalStatus.IMPLEMENTED.value, timestamp, proposal_id),
        )
        conn.close()

    def get_proposals(
        self, status: Optional[ProposalStatus] = None
    ) -> list[ImprovementProposal]:
        """Get proposals with optional status filter."""
        conn = get_connection()
        query = "SELECT * FROM improvement_proposals"
        params: list = []

        if status:
            query += " WHERE status = ?"
            params.append(status.value)

        query += " ORDER BY created_at DESC"
        rows = conn.execute(query, params).fetchall()
        conn.close()

        return [
            ImprovementProposal(
                proposal_id=r[0],
                title=r[1],
                description=r[2],
                category=ProposalCategory(r[3]),
                priority=r[4],
                status=ProposalStatus(r[5]),
                evidence=json.loads(r[6]) if r[6] else {},
                action_steps=json.loads(r[7]) if r[7] else [],
                created_at=r[8],
                implemented_at=r[9],
            )
            for r in rows
        ]

    def generate_auto_proposals(self) -> list[ImprovementProposal]:
        """
        Automatically generate improvement proposals based on system analysis.
        """
        proposals: list[ImprovementProposal] = []

        try:
            # 1. Check for low-feedback chunks
            conn = get_connection()
            low_score_rows = conn.execute(
                """
                SELECT chunk_id, AVG(score) as avg_s, COUNT(*) as cnt
                FROM chunk_score_history
                GROUP BY chunk_id
                HAVING AVG(score) < 0.25 AND COUNT(*) >= 3
                """
            ).fetchall()
            conn.close()

            if low_score_rows:
                proposals.append(
                    self.create_proposal(
                        title="Re-chunk low-relevance content",
                        description=(
                            f"{len(low_score_rows)} chunks consistently return with "
                            "very low relevance scores. Consider re-chunking or "
                            "replacing these documents."
                        ),
                        category=ProposalCategory.CHUNKING,
                        priority="high",
                        evidence={"low_score_chunks": len(low_score_rows)},
                        action_steps=[
                            "Review the affected chunks for content quality",
                            "Test alternative chunking strategies",
                            "Replace or update source documents if outdated",
                        ],
                    )
                )
        except Exception:
            pass

        try:
            # 2. Check for unverified documents
            conn = get_connection()
            unverified = conn.execute(
                """
                SELECT COUNT(*) FROM documents
                WHERE document_id NOT IN (
                    SELECT DISTINCT document_id FROM chunks
                    WHERE chunk_id IN (SELECT DISTINCT chunk_id FROM chunk_score_history)
                )
                """
            ).fetchone()[0]
            conn.close()

            if unverified > 5:
                proposals.append(
                    self.create_proposal(
                        title="Verify untested documents",
                        description=(
                            f"{unverified} documents have never been part of a query result. "
                            "Run verification questions against them to ensure quality."
                        ),
                        category=ProposalCategory.INGESTION,
                        priority="medium",
                        evidence={"untested_documents": unverified},
                        action_steps=[
                            "Generate verification questions for untested documents",
                            "Run verification against the knowledge base",
                            "Update or remove documents that fail verification",
                        ],
                    )
                )
        except Exception:
            pass

        return proposals
