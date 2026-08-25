"""Chat & Query Router — SANJAYA interaction endpoints."""

from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from kurukshetra.security.deps import get_current_user
from kurukshetra.security.identity import UserIdentity

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
async def query_knowledge(
    request: QueryRequest,
    user: UserIdentity = Depends(get_current_user),
):
    """Query the knowledge base using multi-strategy RAG."""
    start = time.time()

    try:
        from kurukshetra.retrieval.hybrid import HybridRetriever
        from kurukshetra.retrieval.access_control import (
            VisibilityFilter, VisibilityLevel,
        )
        from kurukshetra.reranking import BGEReranker
        from kurukshetra.registry.documents import DocumentRepository

        vf = VisibilityFilter(max_level=VisibilityLevel.INTERNAL)
        retriever = vf.wrap(HybridRetriever())
        reranker = BGEReranker()
        doc_repo = DocumentRepository()

        # Retrieve (with visibility filtering)
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


# -----------------------------------------------------------------------
# Evidence-Grounded Answer Endpoint
# -----------------------------------------------------------------------


class AskRequest(BaseModel):
    """Evidence-grounded question request."""
    query: str = Field(..., description="Question to answer")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of evidence items")
    max_level: str = Field(
        default="internal",
        description="Maximum visibility level: public, internal, confidential, restricted",
    )


class CitationResponse(BaseModel):
    """A citation linking an answer to its source."""
    chunk_id: str
    document_id: str
    source_path: str
    text_snippet: str
    score: float
    rank: int


class EvidenceResponse(BaseModel):
    """A piece of evidence from a retrieved chunk."""
    chunk_id: str
    document_id: str
    source_path: str
    text: str
    score: float
    rank: int


class AskResponse(BaseModel):
    """Evidence-grounded answer response."""
    query: str
    answer: str
    confidence: float
    abstained: bool
    abstention_reason: str
    evidence: list[EvidenceResponse]
    citations: list[CitationResponse]
    source_documents: list[str]
    retrieval_strategy: str
    authorization_status: str
    limitations: list[str]
    conflicts: list[str]
    evidence_count: int
    evidence_quality: str
    execution_time_ms: float


@router.post("/ask", response_model=AskResponse)
async def ask_evidence_grounded(
    request: AskRequest,
    user: UserIdentity = Depends(get_current_user),
):
    """
    Ask a question and receive an evidence-grounded answer.

    SANJAYA flow:
    1. Classify query intent and type
    2. Select optimal retrieval strategy
    3. Retrieve authorized evidence
    4. Assemble grounded answer with citations
    5. Detect conflicts and abstain if insufficient
    """
    start = time.time()

    try:
        from kurukshetra.retrieval.hybrid import HybridRetriever
        from kurukshetra.retrieval.database_bm25 import DatabaseBM25Retriever
        from kurukshetra.retrieval.vector import VectorRetriever
        from kurukshetra.retrieval.access_control import (
            VisibilityFilter, VisibilityLevel,
        )
        from kurukshetra.agent.answer_generator import AnswerGenerator
        from kurukshetra.agent.planner import SANJAYAPlanner

        # 1. SANJAYA plan: classify query type and select strategy
        planner = SANJAYAPlanner()
        plan = planner.create_plan(request.query)

        # 2. Set up authorized retrieval with SANJAYA-selected strategy
        # SECURITY: In open mode (anonymous), use request max_level.
        # In auth mode, use min(user clearance, request max).
        user_max = VisibilityLevel.from_string(user.max_visibility)
        request_max = VisibilityLevel.from_string(request.max_level)
        if user.is_authenticated:
            max_level = min(user_max, request_max)
        else:
            # Open mode: use request max_level (default INTERNAL)
            max_level = request_max
        vf = VisibilityFilter(max_level=max_level)

        strategy = plan.recommended_strategy
        if strategy == "bm25":
            retriever_obj = vf.wrap(DatabaseBM25Retriever())
        elif strategy == "vector":
            retriever_obj = vf.wrap(VectorRetriever())
        elif strategy == "graph_aug":
            try:
                from kurukshetra.retrieval.graph_retriever import GraphAugmentedRetriever
                retriever_obj = GraphAugmentedRetriever()
            except Exception:
                retriever_obj = vf.wrap(HybridRetriever())
                strategy = "hybrid_fallback"
        else:
            retriever_obj = vf.wrap(HybridRetriever())

        # 3. Retrieve authorized evidence
        results = retriever_obj.search(request.query, top_k=request.top_k * 2)

        # 4. Check authorization status
        auth_status = "authorized"
        if not results:
            auth_status = "no_evidence"

        # 5. Generate evidence-grounded answer
        generator = AnswerGenerator()
        answer_result = generator.generate(
            query=request.query,
            results=results,
            strategy=strategy,
            authorization_status=auth_status,
        )

        execution_time = (time.time() - start) * 1000

        # 6. Build response with SANJAYA plan info
        return AskResponse(
            query=answer_result.query,
            answer=answer_result.answer,
            confidence=answer_result.confidence,
            abstained=answer_result.abstained,
            abstention_reason=answer_result.abstention_reason,
            evidence=[
                EvidenceResponse(
                    chunk_id=e.chunk_id,
                    document_id=e.document_id,
                    source_path=e.source_path,
                    text=e.text[:500],
                    score=round(e.score, 4),
                    rank=e.rank,
                )
                for e in answer_result.evidence
            ],
            citations=[
                CitationResponse(
                    chunk_id=c.chunk_id,
                    document_id=c.document_id,
                    source_path=c.source_path,
                    text_snippet=c.text_snippet,
                    score=round(c.score, 4),
                    rank=c.rank,
                )
                for c in answer_result.citations
            ],
            source_documents=answer_result.source_documents,
            retrieval_strategy=f"{strategy} (query_type={plan.query_type})",
            authorization_status=answer_result.authorization_status,
            limitations=answer_result.limitations,
            conflicts=answer_result.conflicts,
            evidence_count=answer_result.evidence_count,
            evidence_quality=answer_result.evidence_quality,
            execution_time_ms=round(execution_time, 1),
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
