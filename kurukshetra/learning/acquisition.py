"""
Knowledge Acquisition / Organizational Learning Loop.

Turns genuine knowledge insufficiency into a controlled,
auditable knowledge-question lifecycle.
"""

from __future__ import annotations

import uuid
from typing import Optional

from kurukshetra.learning.models import KnowledgeQuestion
from kurukshetra.learning.repository import KnowledgeQuestionRepository


class KnowledgeAcquisitionManager:
    """Coordinates knowledge-question acquisition."""

    def __init__(
        self,
        repository: Optional[KnowledgeQuestionRepository] = None,
    ) -> None:
        self.repository = repository or KnowledgeQuestionRepository()

    def create_question(
        self,
        question: str,
        *,
        original_query: str = "",
        reason: str = "insufficient_evidence",
        evidence_count: int = 0,
        retrieval_rounds: int = 0,
        metadata: Optional[dict] = None,
    ) -> KnowledgeQuestion:
        """
        Create a persistent knowledge question.

        This records the fact that SANJAYA could not establish
        sufficient evidence for the question. It does not answer,
        publish, or modify organizational knowledge.
        """
        if not question.strip():
            raise ValueError("question must not be empty")

        knowledge_question = KnowledgeQuestion(
            question_id=f"KQ-{uuid.uuid4().hex[:12]}",
            question=question.strip(),
            original_query=original_query.strip(),
            reason=reason,
            evidence_count=evidence_count,
            retrieval_rounds=retrieval_rounds,
            metadata=metadata or {},
        )

        return self.repository.create(knowledge_question)