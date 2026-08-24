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

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


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
# Include routers
# -----------------------------------------------------------------------

from command_center.backend.routers import (
    chat,
    documents,
    graph,
    seal,
    opportunity,
    connectors,
    org,
)

app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(graph.router)
app.include_router(seal.router)
app.include_router(opportunity.router)
app.include_router(connectors.router)
app.include_router(org.router)


# -----------------------------------------------------------------------
# Health endpoint (stays in main — no domain-specific router)
# -----------------------------------------------------------------------

START_TIME = time.time()


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    uptime_seconds: float


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """System health check endpoint."""
    return HealthResponse(
        status="healthy",
        version="2.1.0",
        uptime_seconds=round(time.time() - START_TIME, 1),
    )


# -----------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
