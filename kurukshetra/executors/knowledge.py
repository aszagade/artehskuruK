from __future__ import annotations

from kurukshetra.registry.documents import DocumentRepository
from kurukshetra.retrieval.hybrid import HybridRetriever
from kurukshetra.reranking import BGEReranker


class KnowledgeExecutor:
    """
    Executes Hybrid RAG searches.

    Planner -> KnowledgeExecutor -> HybridRetriever -> Reranker
    """

    def __init__(self):
        self.retriever = HybridRetriever()
        self.reranker = BGEReranker()
        self.documents = DocumentRepository()

    def execute(self, question: str) -> dict:

        results = self.retriever.search(question, top_k=10)
        results = self.reranker.rerank(question, results, top_k=3)

        if not results:
            return {
                "success": False,
                "message": "No relevant knowledge found.",
            }

        best = results[0]
        doc = self.documents.get(best.document_id)

        return {
            "success": True,
            "source": doc[1],
            "document_id": best.document_id,
            "chunk_id": best.chunk_id,
            "score": best.score,
            "text": best.text,
        }