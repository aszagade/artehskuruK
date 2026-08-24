"""Documents Router — Ingestion, metrics, and document management."""

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
    team_owner: str = Field(default="UNKNOWN", description="Team owner")
    auto_classify: bool = Field(default=True, description="Auto-classify document")


class IngestResponse(BaseModel):
    """Document ingestion response."""
    document_id: str
    title: str
    chunks_created: int
    metadata: dict
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


# -----------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------

@router.post("/ingest", response_model=IngestResponse)
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


@router.get("/metrics", response_model=MetricsResponse)
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
