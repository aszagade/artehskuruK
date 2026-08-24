"""Chat & Query Router — SANJAYA interaction endpoints."""

from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api", tags=["Chat & Query"])


# -----------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------

class QueryRequest(BaseModel):
    """RAG query request."""
    query: str = Field(..., description="Search query")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results")
    strategies: Optional[list[str]] = Field(
        default=None,
        description="Retrieval strategies to use (default: all)",
    )


class QueryResult(BaseModel):
    """Single query result."""
    chunk_id: str
    document_id: str
    score: float
    text: str
    metadata: dict = {}


class QueryResponse(BaseModel):
    """RAG query response."""
    query: str
    results: list[QueryResult]
    total_results: int
    execution_time_ms: float
    strategies_used: list[str]


class FeedbackRequest(BaseModel):
    """Feedback submission request."""
    query: str
    document_id: str
    chunk_id: str
    score: float
    is_correct: bool
    user_id: str = "api-user"
    comments: str = ""


class FeedbackResponse(BaseModel):
    """Feedback submission response."""
    feedback_id: str
    status: str


# -----------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------

@router.post("/query", response_model=QueryResponse)
async def query_knowledge(request: QueryRequest):
    """Query the knowledge base using multi-strategy RAG."""
    start = time.time()

    try:
        from kurukshetra.retrieval.hybrid import HybridRetriever
        from kurukshetra.reranking import BGEReranker
        from kurukshetra.registry.documents import DocumentRepository

        retriever = HybridRetriever()
        reranker = BGEReranker()
        doc_repo = DocumentRepository()

        # Retrieve
        results = retriever.search(request.query, top_k=request.top_k * 2)

        # Rerank
        results = reranker.rerank(request.query, results, top_k=request.top_k)

        # Build response
        query_results = []
        for r in results:
            doc = doc_repo.get(r.document_id)
            query_results.append(
                QueryResult(
                    chunk_id=r.chunk_id,
                    document_id=r.document_id,
                    score=round(r.score, 4),
                    text=r.text[:500],
                    metadata=r.metadata,
                )
            )

        execution_time = (time.time() - start) * 1000

        return QueryResponse(
            query=request.query,
            results=query_results,
            total_results=len(query_results),
            execution_time_ms=round(execution_time, 1),
            strategies_used=["hybrid", "rerank"],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(request: FeedbackRequest):
    """Submit feedback for a retrieval result."""
    try:
        from kurukshetra.services.feedback import FeedbackLoop

        loop = FeedbackLoop()
        entry = loop.record_feedback(
            query=request.query,
            document_id=request.document_id,
            chunk_id=request.chunk_id,
            score=request.score,
            is_correct=request.is_correct,
            user_id=request.user_id,
            comments=request.comments,
        )

        return FeedbackResponse(
            feedback_id=entry.feedback_id,
            status="recorded",
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recommendations")
async def get_recommendations():
    """Get self-improvement recommendations."""
    try:
        from kurukshetra.services.self_recommender import SelfRecommender

        recommender = SelfRecommender()
        recs = recommender.analyze_and_recommend()

        return [
            {
                "id": r.recommendation_id,
                "category": r.category,
                "priority": r.priority,
                "title": r.title,
                "description": r.description,
                "action_items": r.action_items,
            }
            for r in recs
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
