"""
KURUKSHETRA Command Center Backend
==================================

FastAPI application providing REST API for:
- RAG query endpoint
- Document ingestion
- Feedback submission
- Knowledge graph queries
- Agent management
- System metrics
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# -----------------------------------------------------------------------
# App initialization
# -----------------------------------------------------------------------

app = FastAPI(
    title="KURUKSHETRA Command Center",
    description="Enterprise AI Command Center for IDeaS Service Delivery",
    version="2.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------------
# Request/Response models
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


class IngestRequest(BaseModel):
    """Document ingestion request."""
    file_path: str = Field(..., description="Path to document file")
    team_owner: str = Field(default="UNKNOWN", description="Team owner")
    auto_classify: bool = Field(default=True, description="Auto-classify document")


class IngestResponse(BaseModel):
    """Document ingestion response."""
    document_id: str
    title: str
    chunks_created: int
    metadata: dict
    execution_time_ms: float


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


class GraphEntityResponse(BaseModel):
    """Knowledge graph entity response."""
    entity: dict
    related_entities: list[dict]
    total_relationships: int


class MetricsResponse(BaseModel):
    """System metrics response."""
    documents: int
    chunks: int
    vectors: int
    glossary_terms: int
    unknown_terms: int
    feedback_entries: int
    agents: int
    graph_entities: int
    graph_relationships: int


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    uptime_seconds: float


# -----------------------------------------------------------------------
# Startup time tracking
# -----------------------------------------------------------------------

START_TIME = time.time()


# -----------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------

@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """System health check endpoint."""
    return HealthResponse(
        status="healthy",
        version="2.1.0",
        uptime_seconds=round(time.time() - START_TIME, 1),
    )


@app.post("/api/query", response_model=QueryResponse)
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


@app.post("/api/ingest", response_model=IngestResponse)
async def ingest_document(request: IngestRequest):
    """Ingest a document into the knowledge base."""
    start = time.time()

    try:
        from kurukshetra.pipeline.ingest import IngestionPipeline
        from kurukshetra.services.content_enricher import ContentEnricher

        pipeline = IngestionPipeline()
        enricher = ContentEnricher()

        file_path = Path(request.file_path)
        result = pipeline.ingest(file_path)

        # Enrich metadata if auto_classify
        metadata = {}
        if request.auto_classify:
            # Read text for classification
            text = "\n".join(c.text for c in result["chunks"])
            content_meta = enricher.enrich(text, file_path.name)
            metadata = {
                "team_owner": content_meta.team_owner.value,
                "product": content_meta.product.value,
                "classification": content_meta.doc_classification.value,
                "confidence": content_meta.confidence,
            }

        execution_time = (time.time() - start) * 1000

        return IngestResponse(
            document_id=result["document"].document_id,
            title=file_path.name,
            chunks_created=len(result["chunks"]),
            metadata=metadata,
            execution_time_ms=round(execution_time, 1),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/feedback", response_model=FeedbackResponse)
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


@app.get("/api/graph/entity/{entity_id}", response_model=GraphEntityResponse)
async def get_graph_entity(entity_id: str):
    """Get knowledge graph entity and its relationships."""
    try:
        from kurukshetra.graph.builder import GraphBuilder

        builder = GraphBuilder()
        context = builder.get_entity_context(entity_id)

        if "error" in context:
            raise HTTPException(status_code=404, detail=context["error"])

        return GraphEntityResponse(
            entity=context["entity"],
            related_entities=context["related_entities"],
            total_relationships=context["total_relationships"],
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/agents")
async def list_agents():
    """List all registered agents."""
    try:
        from kurukshetra.agent.registry import AgentRegistry

        registry = AgentRegistry()
        agents = registry.list_agents()

        return [
            {
                "agent_id": a.agent_id,
                "name": a.name,
                "domain": a.domain,
                "role": a.role.value,
                "status": a.status.value,
                "team_owner": a.team_owner,
            }
            for a in agents
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/metrics", response_model=MetricsResponse)
async def get_metrics():
    """Get system metrics."""
    try:
        from kurukshetra.registry.database import get_connection

        conn = get_connection()

        docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        vectors = conn.execute("SELECT COUNT(*) FROM vectors").fetchone()[0]

        # Optional tables that may not exist yet
        try:
            glossary = conn.execute("SELECT COUNT(*) FROM glossary").fetchone()[0]
        except Exception:
            glossary = 0
        try:
            unknown = conn.execute(
                "SELECT COUNT(*) FROM unknown_terms WHERE status = 'pending'"
            ).fetchone()[0]
        except Exception:
            unknown = 0
        try:
            feedback = conn.execute("SELECT COUNT(*) FROM rag_feedback").fetchone()[0]
        except Exception:
            feedback = 0
        try:
            agents = conn.execute("SELECT COUNT(*) FROM agent_registry").fetchone()[0]
        except Exception:
            agents = 0
        try:
            graph_e = conn.execute("SELECT COUNT(*) FROM graph_entities").fetchone()[0]
            graph_r = conn.execute("SELECT COUNT(*) FROM graph_relationships").fetchone()[0]
        except Exception:
            graph_e = 0
            graph_r = 0

        conn.close()

        return MetricsResponse(
            documents=docs,
            chunks=chunks,
            vectors=vectors,
            glossary_terms=glossary,
            unknown_terms=unknown,
            feedback_entries=feedback,
            agents=agents,
            graph_entities=graph_e,
            graph_relationships=graph_r,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/glossary/pending")
async def get_pending_glossary_terms():
    """Get unknown terms awaiting confirmation."""
    try:
        from kurukshetra.services.glossary import GlossaryManager

        manager = GlossaryManager()
        terms = manager.get_pending_terms()

        return [
            {
                "term": t.term,
                "first_seen_doc": t.first_seen_doc,
                "occurrence_count": t.occurrence_count,
                "suggested_category": t.suggested_category,
                "context_snippet": t.context_snippet[:200],
            }
            for t in terms
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/recommendations")
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


# -----------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


# -----------------------------------------------------------------------
# OrgMap Routes
# -----------------------------------------------------------------------

@app.get("/api/org/map")
async def get_org_map():
    """Get the full organizational hierarchy."""
    try:
        from kurukshetra.agent.org_map import OrgMap

        org = OrgMap()
        teams = org.get_all_teams()

        return {
            "organization": "IDeaS Service Delivery",
            "teams": [
                {
                    "team_id": t.team_id,
                    "name": t.name,
                    "full_name": t.full_name,
                    "type": t.team_type.value,
                    "description": t.description,
                    "products": t.product_scope,
                    "sub_teams": [
                        {"id": s.sub_team_id, "name": s.name, "focus": s.agent_focus}
                        for s in t.sub_teams
                    ],
                    "related_teams": t.related_teams,
                    "capabilities": t.agent_capabilities,
                }
                for t in teams
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/org/classify")
async def classify_document_team(file_path: str):
    """Classify which team a document belongs to."""
    try:
        from kurukshetra.services.team_classifier import TeamClassifier
        from kurukshetra.extractors import PDFExtractor

        classifier = TeamClassifier()
        extractor = PDFExtractor()

        path = Path(file_path)
        text = extractor.extract(path)

        result = classifier.classify_document(
            text=text,
            filename=path.name,
            document_id="",
        )

        return {
            "filename": path.name,
            "primary_team": result.primary_team_name,
            "primary_team_id": result.primary_team_id,
            "confidence": result.confidence,
            "is_cross_team": result.is_cross_team,
            "all_matches": result.all_team_matches[:5],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/org/classify-query")
async def classify_query_team(body: dict):
    """Classify which team a query should route to."""
    try:
        from kurukshetra.services.team_classifier import TeamClassifier

        classifier = TeamClassifier()
        query = body.get("query", "")

        results = classifier.classify_query(query)

        return {
            "query": query,
            "team_matches": results[:5],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/org/team/{team_id}/documents")
async def get_team_documents(team_id: str):
    """Get all documents belonging to a specific team."""
    try:
        from kurukshetra.services.team_classifier import TeamClassifier

        classifier = TeamClassifier()
        docs = classifier.get_documents_by_team(team_id)

        return {
            "team_id": team_id,
            "documents": docs,
            "total": len(docs),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/org/cross-team")
async def get_cross_team_documents():
    """Get documents that belong to multiple teams."""
    try:
        from kurukshetra.services.team_classifier import TeamClassifier

        classifier = TeamClassifier()
        docs = classifier.get_cross_team_documents()

        return {
            "cross_team_documents": docs,
            "total": len(docs),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/org/stats")
async def get_org_stats():
    """Get team classification statistics."""
    try:
        from kurukshetra.services.team_classifier import TeamClassifier

        classifier = TeamClassifier()
        stats = classifier.get_team_stats()

        return {
            "team_stats": stats,
            "total_classified": sum(s["document_count"] for s in stats.values()),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------------------------------------------------
# Graph Intelligence endpoints
# -----------------------------------------------------------------------

@app.get("/api/graph/stats")
async def get_graph_stats():
    """Get Knowledge Graph statistics."""
    try:
        from kurukshetra.graph.registry import GraphRegistry

        registry = GraphRegistry()
        stats = registry.get_stats()
        registry.close()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/graph/entities")
async def search_graph_entities(
    query: str = "",
    entity_type: Optional[str] = None,
    team_id: Optional[str] = None,
    limit: int = 50,
):
    """Search graph entities with optional filters."""
    try:
        from kurukshetra.graph.registry import GraphRegistry

        registry = GraphRegistry()
        entities = registry.search_entities(
            query=query, entity_type=entity_type, team_id=team_id, limit=limit
        )
        registry.close()
        return {"entities": entities, "total": len(entities)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/graph/entity/{entity_id}")
async def get_entity_context(entity_id: str, depth: int = 2):
    """Get full context for an entity (metadata + neighborhood)."""
    try:
        from kurukshetra.graph.registry import GraphRegistry

        registry = GraphRegistry()
        context = registry.get_entity_context(entity_id, depth=depth)
        registry.close()

        if context is None:
            raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")
        return context
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/graph/path")
async def find_graph_path(source_id: str, target_id: str):
    """Find shortest path between two entities."""
    try:
        from kurukshetra.graph.registry import GraphRegistry

        registry = GraphRegistry()
        path = registry.find_path(source_id, target_id)
        registry.close()

        if path is None:
            return {"path": None, "message": "No path found"}
        return path
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/graph/impact/{entity_id}")
async def analyze_entity_impact(entity_id: str, max_depth: int = 3):
    """Analyze the impact of an entity change."""
    try:
        from kurukshetra.graph.registry import GraphRegistry

        registry = GraphRegistry()
        impact = registry.analyze_impact(entity_id, max_depth=max_depth)
        registry.close()
        return impact
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/graph/communities")
async def get_graph_communities():
    """Detect communities (clusters) in the knowledge graph."""
    try:
        from kurukshetra.graph.registry import GraphRegistry

        registry = GraphRegistry()
        communities = registry.get_communities()
        registry.close()
        return {"communities": communities, "total": len(communities)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/graph/team/{team_id}")
async def get_team_subgraph(team_id: str):
    """Get the subgraph for a specific team."""
    try:
        from kurukshetra.graph.registry import GraphRegistry

        registry = GraphRegistry()
        subgraph = registry.get_team_graph(team_id)
        registry.close()
        return subgraph
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/graph/entity/{entity_id}/confirm")
async def confirm_entity(entity_id: str):
    """Mark an entity as human-confirmed (for SEAL learning)."""
    try:
        from kurukshetra.graph.registry import GraphRegistry

        registry = GraphRegistry()
        registry.confirm_entity(entity_id)
        registry.close()
        return {"status": "confirmed", "entity_id": entity_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/graph/connectors")
async def list_graph_connectors():
    """List available future connectors."""
    try:
        from kurukshetra.graph.connectors import list_connectors

        return {"connectors": list_connectors()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
