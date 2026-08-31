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
    """Submit feedback for a retrieval result.

    This is the PRIMARY feedback entry point for the closed-loop learning system.
    Feedback is recorded in:
    1. FeedbackLoop (rag_feedback + chunk_score_history) — drives retrieval adjustment
    2. EvaluationSignalTracker (query_signals + document_signals) — drives evaluation
    3. EpisodicMemory (if applicable) — drives conversation memory
    """
    try:
        from kurukshetra.services.feedback import FeedbackLoop
        from kurukshetra.retrieval.evaluation_tracker import EvaluationSignalTracker

        # 1. Record in FeedbackLoop (drives retrieval score adjustment)
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

        # 2. Record in EvaluationSignalTracker (drives evaluation patterns)
        try:
            tracker = EvaluationSignalTracker()
            tracker.record_feedback_signal(
                query=request.query,
                document_id=request.document_id,
                is_correct=request.is_correct,
                confidence=request.score,
                user_id=request.user_id,
            )
        except Exception:
            pass  # Evaluation tracking is non-critical

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
    retrieval_rounds: int = 1
    unique_documents: int = 1
    mention_vs_answer_detected: bool = False
    verification_passed: bool = True


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
        from kurukshetra.agent.orchestrator import AgenticSANJAYA
        from kurukshetra.agent.planner import SANJAYAPlanner

        # 1. Set up authorized retrieval
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
        retriever_obj = vf.wrap(HybridRetriever())

        # 2. Optionally use GX10 LLM for natural-language answer
        llm_client = None
        try:
            from kurukshetra.llm.client import get_llm_client
            llm_client = get_llm_client()
            if not llm_client.is_available:
                llm_client = None
        except Exception:
            pass

        # 3. Agentic SANJAYA: iterative retrieval + multi-document synthesis
        agentic = AgenticSANJAYA(
            retriever=retriever_obj,
            llm_client=llm_client,
            max_rounds=2,
        )
        agentic_result = agentic.ask(request.query)
        answer_result = agentic_result.answer_result
        strategy = agentic_result.rounds[0].strategy if agentic_result.rounds else "hybrid"

        execution_time = (time.time() - start) * 1000

        # 4. Build response with agentic diagnostics
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
            retrieval_strategy=f"{strategy} (agentic)",
            authorization_status=answer_result.authorization_status,
            limitations=answer_result.limitations,
            conflicts=answer_result.conflicts,
            evidence_count=answer_result.evidence_count,
            evidence_quality=answer_result.evidence_quality,
            execution_time_ms=round(execution_time, 1),
            retrieval_rounds=len(agentic_result.rounds),
            unique_documents=agentic_result.unique_documents,
            mention_vs_answer_detected=agentic_result.mention_vs_answer_detected,
            verification_passed=agentic_result.verification_passed,
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
