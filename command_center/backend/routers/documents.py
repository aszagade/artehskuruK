"""Documents Router — Ingestion, metrics, status, and document management."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api", tags=["Documents"])


# -----------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------

class IngestRequest(BaseModel):
    """Document ingestion request."""
    file_path: str = Field(..., description="Path to document file")


class IngestResponse(BaseModel):
    """Document ingestion response."""
    document_id: str
    title: str
    status: str
    chunks_stored: int
    entities_extracted: int
    relationships_extracted: int
    unknown_terms: int
    team_id: str
    stages: dict
    execution_time_ms: float


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


class ActivityResponse(BaseModel):
    """Ingestion activity response."""
    pending: list[dict]
    recent: list[dict]
    stats: dict


# -----------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------

@router.post("/ingest", response_model=IngestResponse)
async def ingest_document(request: IngestRequest):
    """Ingest a document into the knowledge base."""
    start = time.time()

    try:
        from kurukshetra.pipeline.ingest import IngestionPipeline

        pipeline = IngestionPipeline(use_semantic_chunking=False)
        file_path = Path(request.file_path)
        result = pipeline.ingest(file_path)
        pipeline.close()

        execution_time = (time.time() - start) * 1000

        return IngestResponse(
            document_id=result.document_id,
            title=result.title,
            status="error" if result.error else "ok",
            chunks_stored=result.chunks_stored,
            entities_extracted=result.entities_extracted,
            relationships_extracted=result.relationships_extracted,
            unknown_terms=result.unknown_terms,
            team_id=result.team_id,
            stages=result.stages,
            execution_time_ms=round(execution_time, 1),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics():
    """Get system metrics."""
    try:
        from kurukshetra.registry.database import get_connection

        conn = get_connection()

        docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        vectors = conn.execute("SELECT COUNT(*) FROM vectors").fetchone()[0]

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


@router.get("/activity", response_model=ActivityResponse)
async def get_activity():
    """Get ingestion activity status."""
    from kurukshetra.runtime.status import get_tracker

    tracker = get_tracker()
    return ActivityResponse(
        pending=[a.to_dict() for a in tracker.get_pending()],
        recent=tracker.get_recent(),
        stats=tracker.get_stats(),
    )


@router.get("/activity/{filename}")
async def get_document_activity(filename: str):
    """Get status for a specific document."""
    from kurukshetra.runtime.status import get_tracker

    tracker = get_tracker()
    activity = tracker.get_activity(filename)
    if activity is None:
        raise HTTPException(status_code=404, detail=f"No activity for {filename}")
    return activity.to_dict()


@router.post("/ingest/inbox")
async def ingest_from_inbox():
    """Ingest all documents from the knowledge inbox."""
    from kurukshetra.runtime.watcher import InboxWatcher

    start = time.time()
    watcher = InboxWatcher()
    results = watcher.ingest_all()
    watcher.close()

    return {
        "documents_processed": len(results),
        "successful": sum(1 for r in results if not r.error),
        "failed": sum(1 for r in results if r.error),
        "execution_time_ms": round((time.time() - start) * 1000, 1),
        "results": [
            {
                "document_id": r.document_id,
                "title": r.title,
                "status": "error" if r.error else "ok",
                "chunks_stored": r.chunks_stored,
                "entities_extracted": r.entities_extracted,
                "unknown_terms": r.unknown_terms,
            }
            for r in results
        ],
    }
