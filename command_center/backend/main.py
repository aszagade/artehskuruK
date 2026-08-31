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
- Continuous knowledge watching
"""

from __future__ import annotations

import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from kurukshetra.security.config import SecurityConfig
from kurukshetra.security.middleware import APIKeyAuth, AuditLog, PathTraversalGuard

logger = logging.getLogger("kurukshetra.app")


# -----------------------------------------------------------------------
# Security configuration
# -----------------------------------------------------------------------

_security = SecurityConfig()


# -----------------------------------------------------------------------
# Application lifespan (startup / shutdown)
# -----------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: start watcher on startup, stop on shutdown."""
    # --- STARTUP ---
    from kurukshetra.runtime.watcher_manager import get_watcher_manager
    manager = get_watcher_manager()
    manager.start()
    logger.info("KURUKSHETRA Command Center started")

    yield  # Application runs

    # --- SHUTDOWN ---
    manager.stop()
    logger.info("KURUKSHETRA Command Center stopped")


# -----------------------------------------------------------------------
# App initialization
# -----------------------------------------------------------------------

app = FastAPI(
    title="KURUKSHETRA Command Center",
    description="Enterprise AI Command Center for IDeaS Service Delivery",
    version="2.1.0",
    lifespan=lifespan,
)

# CORS — uses configured origins (default: ["*"] for development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_security.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tier-1 security middleware (order matters: outermost runs first)
# 1. Audit logging — records every request
# 2. Path traversal — blocks dangerous file paths
# 3. API-key auth — validates credentials
app.add_middleware(AuditLog, config=_security)
app.add_middleware(PathTraversalGuard, config=_security)
app.add_middleware(APIKeyAuth, config=_security)


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
    knowledge,
    auth,
    explorer,
)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(graph.router)
app.include_router(seal.router)
app.include_router(opportunity.router)
app.include_router(connectors.router)
app.include_router(org.router)
app.include_router(knowledge.router)
app.include_router(explorer.router)


# -----------------------------------------------------------------------
# Health endpoint (stays in main — no domain-specific router)
# -----------------------------------------------------------------------

START_TIME = time.time()


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    uptime_seconds: float


class ConfigResponse(BaseModel):
    """Public configuration for the frontend."""
    version: str
    auth_required: bool
    entra_configured: bool
    public_url: str


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """System health check endpoint."""
    return HealthResponse(
        status="healthy",
        version="2.1.0",
        uptime_seconds=round(time.time() - START_TIME, 1),
    )


@app.get("/api/config", response_model=ConfigResponse)
async def get_config():
    """Public configuration endpoint for the frontend."""
    from kurukshetra.security.entra_provider import EntraConfig
    entra = EntraConfig.from_env()
    return ConfigResponse(
        version="2.1.0",
        auth_required=_security.auth_required,
        entra_configured=entra.is_configured,
        public_url=os.environ.get("SANJAYA_PUBLIC_URL", ""),
    )


# -----------------------------------------------------------------------
# Frontend — serve the SANJAYA UI from the same origin
# -----------------------------------------------------------------------

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@app.get("/", include_in_schema=False)
async def serve_frontend():
    """Serve the SANJAYA Knowledge Command Center UI."""
    from fastapi.responses import FileResponse
    return FileResponse(FRONTEND_DIR / "index.html")


# -----------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------

if __name__ == "__main__":
    import os
    import uvicorn
    host = os.environ.get("SANJAYA_HOST", "0.0.0.0")
    port = int(os.environ.get("SANJAYA_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
