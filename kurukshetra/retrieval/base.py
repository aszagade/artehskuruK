from __future__ import annotations

from abc import ABC, abstractmethod

from .models import RetrievalResult


class BaseRetriever(ABC):
    """
    Contract implemented by every retrieval engine.
    """

    @abstractmethod
    def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        """
        Return the most relevant knowledge chunks.
        """
        raise NotImplementedError