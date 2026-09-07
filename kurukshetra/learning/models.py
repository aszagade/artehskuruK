"""
Knowledge Acquisition domain models.

Represents organizational knowledge questions that SANJAYA
cannot answer from currently available verified evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class KnowledgeQuestionStatus(Enum):
    """Lifecycle status of a knowledge acquisition question."""

    OPEN = "open"
    ANSWERED = "answered"
    VERIFIED = "verified"
    PUBLISHED = "published"
    RESOLVED = "resolved"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class KnowledgeQuestion:
    """
    A persistent organizational knowledge acquisition request.

    The question records what SANJAYA could not establish from
    available evidence. It does not itself represent authoritative
    organizational knowledge.
    """

    question_id: str
    question: str
    original_query: str
    reason: str
    status: KnowledgeQuestionStatus = KnowledgeQuestionStatus.OPEN

    # Retrieval context at the time the gap was detected.
    evidence_count: int = 0
    retrieval_rounds: int = 0

    # Human/source answer.
    answer: str = ""
    answered_by: str = ""

    # Published KnowledgeFabric document.
    source_document_id: str = ""

    # Lifecycle timestamps, stored as ISO-8601 strings by the repository.
    created_at: str = ""
    updated_at: str = ""
    answered_at: str = ""
    verified_at: str = ""
    published_at: str = ""
    resolved_at: str = ""

    # Extensible context without changing the schema.
    metadata: dict = field(default_factory=dict)