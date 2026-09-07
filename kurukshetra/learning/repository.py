"""
Persistent repository for SANJAYA knowledge acquisition questions.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from kurukshetra.registry.database import get_connection

from .models import KnowledgeQuestion, KnowledgeQuestionStatus


class KnowledgeQuestionRepository:
    """DuckDB persistence for organizational knowledge questions."""

    _ALLOWED_TRANSITIONS = {
        KnowledgeQuestionStatus.OPEN: {
            KnowledgeQuestionStatus.ANSWERED,
            KnowledgeQuestionStatus.REJECTED,
            KnowledgeQuestionStatus.DUPLICATE,
            KnowledgeQuestionStatus.CANCELLED,
        },
        KnowledgeQuestionStatus.ANSWERED: {
            KnowledgeQuestionStatus.VERIFIED,
            KnowledgeQuestionStatus.REJECTED,
            KnowledgeQuestionStatus.CANCELLED,
        },
        KnowledgeQuestionStatus.VERIFIED: {
            KnowledgeQuestionStatus.PUBLISHED,
            KnowledgeQuestionStatus.CANCELLED,
        },
        KnowledgeQuestionStatus.PUBLISHED: {
            KnowledgeQuestionStatus.RESOLVED,
        },
        KnowledgeQuestionStatus.RESOLVED: set(),
        KnowledgeQuestionStatus.REJECTED: set(),
        KnowledgeQuestionStatus.DUPLICATE: set(),
        KnowledgeQuestionStatus.CANCELLED: set(),
    }

    def __init__(self) -> None:
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Create the knowledge-question table if it does not exist."""
        conn = get_connection()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_questions (
                question_id TEXT PRIMARY KEY,
                question TEXT NOT NULL,
                original_query TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT DEFAULT 'open',

                evidence_count INTEGER DEFAULT 0,
                retrieval_rounds INTEGER DEFAULT 0,

                answer TEXT DEFAULT '',
                answered_by TEXT DEFAULT '',

                source_document_id TEXT DEFAULT '',

                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                answered_at TEXT DEFAULT '',
                verified_at TEXT DEFAULT '',
                published_at TEXT DEFAULT '',
                resolved_at TEXT DEFAULT '',

                metadata TEXT DEFAULT '{}'
            )
            """
        )
        conn.close()

    @staticmethod
    def _now() -> str:
        """Return a UTC ISO-8601 timestamp."""
        return datetime.utcnow().isoformat()

    @staticmethod
    def _row_to_model(row) -> KnowledgeQuestion:
        """Convert a database row into a KnowledgeQuestion."""
        metadata = {}
        if row[16]:
            try:
                metadata = json.loads(row[16])
            except (TypeError, json.JSONDecodeError):
                metadata = {}

        return KnowledgeQuestion(
            question_id=row[0],
            question=row[1],
            original_query=row[2],
            reason=row[3],
            status=KnowledgeQuestionStatus(row[4]),
            evidence_count=row[5] or 0,
            retrieval_rounds=row[6] or 0,
            answer=row[7] or "",
            answered_by=row[8] or "",
            source_document_id=row[9] or "",
            created_at=row[10] or "",
            updated_at=row[11] or "",
            answered_at=row[12] or "",
            verified_at=row[13] or "",
            published_at=row[14] or "",
            resolved_at=row[16] or "",
            metadata=metadata,
        )

    def create(self, question: KnowledgeQuestion) -> KnowledgeQuestion:
        """Persist a new knowledge question."""
        now = self._now()

        if not question.created_at:
            question.created_at = now
        question.updated_at = now

        conn = get_connection()
        try:
            conn.execute(
                """
                INSERT INTO knowledge_questions (
                    question_id,
                    question,
                    original_query,
                    reason,
                    status,
                    evidence_count,
                    retrieval_rounds,
                    answer,
                    answered_by,
                    source_document_id,
                    created_at,
                    updated_at,
                    answered_at,
                    verified_at,
                    published_at,
                    resolved_at,
                    metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    question.question_id,
                    question.question,
                    question.original_query,
                    question.reason,
                    question.status.value,
                    question.evidence_count,
                    question.retrieval_rounds,
                    question.answer,
                    question.answered_by,
                    question.source_document_id,
                    question.created_at,
                    question.updated_at,
                    question.answered_at,
                    question.verified_at,
                    question.published_at,
                    question.resolved_at,
                    json.dumps(question.metadata),
                ],
            )
        finally:
            conn.close()

        return question

    def get(self, question_id: str) -> Optional[KnowledgeQuestion]:
        """Retrieve one knowledge question by ID."""
        conn = get_connection()
        try:
            row = conn.execute(
                """
                SELECT
                    question_id,
                    question,
                    original_query,
                    reason,
                    status,
                    evidence_count,
                    retrieval_rounds,
                    answer,
                    answered_by,
                    source_document_id,
                    created_at,
                    updated_at,
                    answered_at,
                    verified_at,
                    published_at,
                    resolved_at,
                    metadata
                FROM knowledge_questions
                WHERE question_id = ?
                """,
                [question_id],
            ).fetchone()
        finally:
            conn.close()

        return self._row_to_model(row) if row else None

    def list(
        self,
        status: Optional[KnowledgeQuestionStatus] = None,
    ) -> list[KnowledgeQuestion]:
        """List knowledge questions, optionally filtered by status."""
        conn = get_connection()
        try:
            if status is not None:
                rows = conn.execute(
                    """
                    SELECT
                        question_id,
                        question,
                        original_query,
                        reason,
                        status,
                        evidence_count,
                        retrieval_rounds,
                        answer,
                        answered_by,
                        source_document_id,
                        created_at,
                        updated_at,
                        answered_at,
                        verified_at,
                        published_at,
                        resolved_at,
                        metadata
                    FROM knowledge_questions
                    WHERE status = ?
                    ORDER BY created_at DESC
                    """,
                    [status.value],
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT
                        question_id,
                        question,
                        original_query,
                        reason,
                        status,
                        evidence_count,
                        retrieval_rounds,
                        answer,
                        answered_by,
                        source_document_id,
                        created_at,
                        updated_at,
                        answered_at,
                        verified_at,
                        published_at,
                        resolved_at,
                        metadata
                    FROM knowledge_questions
                    ORDER BY created_at DESC
                    """
                ).fetchall()
        finally:
            conn.close()

        return [self._row_to_model(row) for row in rows]

    def update_status(
        self,
        question_id: str,
        new_status: KnowledgeQuestionStatus,
    ) -> KnowledgeQuestion:
        """Move a question through a valid lifecycle transition."""
        question = self.get(question_id)

        if question is None:
            raise ValueError(f"Knowledge question not found: {question_id}")

        allowed = self._ALLOWED_TRANSITIONS[question.status]

        if new_status not in allowed:
            raise ValueError(
                f"Invalid knowledge-question transition: "
                f"{question.status.value} -> {new_status.value}"
            )

        now = self._now()

        timestamp_field = {
            KnowledgeQuestionStatus.ANSWERED: "answered_at",
            KnowledgeQuestionStatus.VERIFIED: "verified_at",
            KnowledgeQuestionStatus.PUBLISHED: "published_at",
            KnowledgeQuestionStatus.RESOLVED: "resolved_at",
        }.get(new_status)

        conn = get_connection()
        try:
            if timestamp_field:
                conn.execute(
                    f"""
                    UPDATE knowledge_questions
                    SET status = ?, updated_at = ?, {timestamp_field} = ?
                    WHERE question_id = ?
                    """,
                    [new_status.value, now, now, question_id],
                )
            else:
                conn.execute(
                    """
                    UPDATE knowledge_questions
                    SET status = ?, updated_at = ?
                    WHERE question_id = ?
                    """,
                    [new_status.value, now, question_id],
                )
        finally:
            conn.close()

        updated = self.get(question_id)
        if updated is None:
            raise RuntimeError(
                f"Knowledge question disappeared after update: {question_id}"
            )

        return updated

    def record_answer(
        self,
        question_id: str,
        answer: str,
        answered_by: str,
    ) -> KnowledgeQuestion:
        """Record a human/source answer and move OPEN -> ANSWERED."""
        question = self.get(question_id)

        if question is None:
            raise ValueError(f"Knowledge question not found: {question_id}")

        if question.status != KnowledgeQuestionStatus.OPEN:
            raise ValueError(
                f"Cannot record an answer while question is "
                f"{question.status.value}"
            )

        if not answer.strip():
            raise ValueError("Answer cannot be empty")

        now = self._now()

        conn = get_connection()
        try:
            conn.execute(
                """
                UPDATE knowledge_questions
                SET answer = ?,
                    answered_by = ?,
                    answered_at = ?,
                    status = ?,
                    updated_at = ?
                WHERE question_id = ?
                """,
                [
                    answer,
                    answered_by,
                    now,
                    KnowledgeQuestionStatus.ANSWERED.value,
                    now,
                    question_id,
                ],
            )
        finally:
            conn.close()

        updated = self.get(question_id)
        if updated is None:
            raise RuntimeError(
                f"Knowledge question disappeared after answer: {question_id}"
            )

        return updated

    def record_publication(
        self,
        question_id: str,
        source_document_id: str,
    ) -> KnowledgeQuestion:
        """
        Record the KnowledgeFabric document created from the answer.

        This method only records the publication reference. It does not
        perform ingestion itself.
        """
        question = self.get(question_id)

        if question is None:
            raise ValueError(f"Knowledge question not found: {question_id}")

        if question.status != KnowledgeQuestionStatus.VERIFIED:
            raise ValueError(
                "Knowledge can only be published after verification"
            )

        if not source_document_id.strip():
            raise ValueError("source_document_id cannot be empty")

        now = self._now()

        conn = get_connection()
        try:
            conn.execute(
                """
                UPDATE knowledge_questions
                SET source_document_id = ?,
                    status = ?,
                    published_at = ?,
                    updated_at = ?
                WHERE question_id = ?
                """,
                [
                    source_document_id,
                    KnowledgeQuestionStatus.PUBLISHED.value,
                    now,
                    now,
                    question_id,
                ],
            )
        finally:
            conn.close()

        updated = self.get(question_id)
        if updated is None:
            raise RuntimeError(
                f"Knowledge question disappeared after publication: {question_id}"
            )

        return updated