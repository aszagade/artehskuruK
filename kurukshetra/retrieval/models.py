from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class RetrievalResult:
    """
    Standard result returned by every retrieval strategy.
    """

    chunk_id: str
    document_id: str
    score: float
    text: str
    metadata: dict[str, Any]