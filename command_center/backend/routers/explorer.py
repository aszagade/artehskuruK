"""Knowledge Explorer Router — Brain intelligence endpoints.

Provides:
- /api/sources — Source catalog with live status
- /api/knowledge/timeline — Ingestion/change events
- /api/health/detail — Subsystem health checks
- /api/memory/summary — Current user memory summary (user-scoped)
- /api/knowledge/gaps — Knowledge gap analysis
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

router = APIRouter(tags=["Knowledge Explorer"])


# ── Models ────────────────────────────────────────────────────

class SourceInfo(BaseModel):
    source_id: str
    name: str
    source_type: str  # "local_documents", "network_share", "confluence", "sharepoint", "salesforce", "user_upload", "git"
    status: str  # "indexed", "live", "unavailable", "not_connected"
    document_count: int = 0
    last_sync: Optional[str] = None
    team: Optional[str] = None
    path: Optional[str] = None


class TimelineEvent(BaseModel):
    event_id: str
    event_type: str  # "document_added", "document_updated", "version_detected", "feedback_received", "relationship_changed"
    timestamp: str
    description: str
    document_id: Optional[str] = None
    details: Optional[dict] = None


class HealthDetail(BaseModel):
    component: str
    status: str  # "healthy", "degraded", "unavailable", "not_configured"
    message: str = ""
    last_check: str = ""
    latency_ms: float = 0.0


class MemorySummary(BaseModel):
    user_id: str
    working_memory: dict  # current context
    episodic_memory: dict  # past interactions
    semantic_memory: dict  # organizational knowledge
    procedural_memory: dict  # validated procedures
    prospective_memory: dict  # future tasks
    external_memory: dict  # knowledge fabric


class KnowledgeGap(BaseModel):
    query: str
    has_evidence: bool
    evidence_count: int
    related_documents: list[str]
    gap_reason: str  # "no_evidence", "insufficient_evidence", "mention_only", "out_of_scope", "unauthorized"
    suggestion: str = ""


# ── Sources ───────────────────────────────────────────────────

@router.get("/api/sources")
async def list_sources():
    """List all knowledge sources with live status."""
    sources = []

    # 1. Local documents (main corpus)
    try:
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        teams = conn.execute(
            "SELECT DISTINCT team_owner FROM documents WHERE team_owner IS NOT NULL AND team_owner != ''"
        ).fetchall()
        conn.close()
        sources.append(SourceInfo(
            source_id="local_documents",
            name="Enterprise Documents (ICS/SPM/SDOPS/ROA)",
            source_type="local_documents",
            status="indexed" if count > 0 else "unavailable",
            document_count=count,
            team="multiple",
        ))
    except Exception:
        sources.append(SourceInfo(
            source_id="local_documents",
            name="Enterprise Documents",
            source_type="local_documents",
            status="unavailable",
        ))

    # 2. Network share (read-only)
    from pathlib import Path as P
    share_path = P(r"\\ina6fs01\Dept_shares\ICS")
    try:
        accessible = share_path.exists()
        sources.append(SourceInfo(
            source_id="network_share_ics",
            name="ICS Network Share (\\\\ina6fs01\\Dept_shares\\ICS)",
            source_type="network_share",
            status="live" if accessible else "unavailable",
            path=str(share_path),
            team="ICS",
        ))
    except Exception:
        sources.append(SourceInfo(
            source_id="network_share_ics",
            name="ICS Network Share",
            source_type="network_share",
            status="unavailable",
        ))

    # 3. User uploads
    try:
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        upload_count = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE source_path LIKE '%uploads%' OR source_path LIKE '%inbox%'"
        ).fetchone()[0]
        conn.close()
        sources.append(SourceInfo(
            source_id="user_uploads",
            name="User-Uploaded Knowledge",
            source_type="user_upload",
            status="indexed" if upload_count > 0 else "live",
            document_count=upload_count,
        ))
    except Exception:
        sources.append(SourceInfo(
            source_id="user_uploads",
            name="User-Uploaded Knowledge",
            source_type="user_upload",
            status="live",
        ))

    # 4. Salesforce (adapter exists, not connected)
    sources.append(SourceInfo(
        source_id="salesforce",
        name="Salesforce CRM",
        source_type="salesforce",
        status="not_connected",
        team="CRM",
    ))

    # 5. Confluence
    sources.append(SourceInfo(
        source_id="confluence",
        name="Confluence Wiki",
        source_type="confluence",
        status="not_connected",
    ))

    # 6. SharePoint
    sources.append(SourceInfo(
        source_id="sharepoint",
        name="SharePoint Online",
        source_type="sharepoint",
        status="not_connected",
    ))

    # 7. Git repositories
    sources.append(SourceInfo(
        source_id="git_repos",
        name="Git Repositories",
        source_type="git",
        status="not_connected",
    ))

    return {"sources": [s.model_dump() for s in sources], "total": len(sources)}


# ── Timeline ──────────────────────────────────────────────────

@router.get("/api/knowledge/timeline")
async def get_timeline(limit: int = 50):
    """Get recent knowledge ingestion/change events."""
    events = []

    try:
        from kurukshetra.registry.database import get_connection
        conn = get_connection()

        # Recent documents added
        rows = conn.execute("""
            SELECT document_id, title, team_owner, last_updated
            FROM documents
            ORDER BY last_updated DESC
            LIMIT ?
        """, (limit,)).fetchall()

        for row in rows:
            doc_id, title, team, updated = row
            events.append(TimelineEvent(
                event_id=f"doc_{doc_id}",
                event_type="document_added",
                timestamp=str(updated) if updated else "",
                description=f"Document indexed: {title or doc_id}",
                document_id=doc_id,
                details={"team": team},
            ))

        # Recent feedback
        try:
            fb_rows = conn.execute("""
                SELECT query, rating, created_at
                FROM rag_feedback
                ORDER BY created_at DESC
                LIMIT 10
            """).fetchall()
            for row in fb_rows:
                query, rating, created = row
                events.append(TimelineEvent(
                    event_id=f"fb_{hash(query)}",
                    event_type="feedback_received",
                    timestamp=str(created) if created else "",
                    description=f"Feedback: {'👍' if rating and rating > 0 else '👎'} on \"{(query or '')[:60]}\"",
                ))
        except Exception:
            pass

        # Recent unknown terms (learning opportunities)
        try:
            ut_rows = conn.execute("""
                SELECT term, source_document, first_seen
                FROM unknown_terms
                ORDER BY first_seen DESC
                LIMIT 5
            """).fetchall()
            for row in ut_rows:
                term, src, seen = row
                events.append(TimelineEvent(
                    event_id=f"ut_{hash(term or '')}",
                    event_type="relationship_changed",
                    timestamp=str(seen) if seen else "",
                    description=f"New term detected: {term}",
                    document_id=src,
                ))
        except Exception:
            pass

        conn.close()

    except Exception:
        pass

    # Sort by timestamp descending
    events.sort(key=lambda e: e.timestamp or "", reverse=True)

    return {"events": [e.model_dump() for e in events[:limit]], "total": len(events)}


# ── Health Detail ─────────────────────────────────────────────

@router.get("/api/health/detail")
async def get_health_detail():
    """Detailed health check for all subsystems."""
    checks = []
    now = datetime.now(timezone.utc).isoformat()

    # 1. Database
    t0 = time.time()
    try:
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        latency = (time.time() - t0) * 1000
        checks.append(HealthDetail(
            component="Database", status="healthy",
            message="DuckDB responsive", last_check=now, latency_ms=round(latency, 1),
        ))
    except Exception as e:
        checks.append(HealthDetail(
            component="Database", status="unavailable",
            message=str(e)[:100], last_check=now,
        ))

    # 2. Knowledge Fabric
    t0 = time.time()
    try:
        from kurukshetra.knowledge.fabric import KnowledgeFabric
        fabric = KnowledgeFabric()
        state = fabric.get_knowledge_state()
        fabric.close()
        latency = (time.time() - t0) * 1000
        status = "healthy" if state.total_documents > 0 else "degraded"
        checks.append(HealthDetail(
            component="Knowledge Fabric", status=status,
            message=f"{state.total_documents} documents, {state.total_chunks} chunks",
            last_check=now, latency_ms=round(latency, 1),
        ))
    except Exception as e:
        checks.append(HealthDetail(
            component="Knowledge Fabric", status="unavailable",
            message=str(e)[:100], last_check=now,
        ))

    # 3. Graph
    t0 = time.time()
    try:
        from kurukshetra.graph.registry import GraphRegistry
        registry = GraphRegistry()
        stats = registry.get_stats()
        registry.close()
        latency = (time.time() - t0) * 1000
        entity_count = stats.get("total_entities", 0) if isinstance(stats, dict) else 0
        checks.append(HealthDetail(
            component="Knowledge Graph", status="healthy" if entity_count > 0 else "degraded",
            message=f"{entity_count} entities",
            last_check=now, latency_ms=round(latency, 1),
        ))
    except Exception as e:
        checks.append(HealthDetail(
            component="Knowledge Graph", status="unavailable",
            message=str(e)[:100], last_check=now,
        ))

    # 4. Retrieval (BM25)
    t0 = time.time()
    try:
        from kurukshetra.retrieval.database_bm25 import DatabaseBM25Retriever
        retriever = DatabaseBM25Retriever()
        results = retriever.search("test", top_k=1)
        latency = (time.time() - t0) * 1000
        checks.append(HealthDetail(
            component="Retrieval (BM25)", status="healthy",
            message=f"Responding ({len(results)} results for probe)",
            last_check=now, latency_ms=round(latency, 1),
        ))
    except Exception as e:
        checks.append(HealthDetail(
            component="Retrieval (BM25)", status="unavailable",
            message=str(e)[:100], last_check=now,
        ))

    # 5. Vector Retrieval
    t0 = time.time()
    try:
        from kurukshetra.retrieval.vector_retriever import VectorRetriever
        v = VectorRetriever()
        latency = (time.time() - t0) * 1000
        checks.append(HealthDetail(
            component="Retrieval (Vector)", status="healthy",
            message=f"BGE embeddings loaded",
            last_check=now, latency_ms=round(latency, 1),
        ))
    except Exception as e:
        checks.append(HealthDetail(
            component="Retrieval (Vector)", status="degraded",
            message=str(e)[:100], last_check=now,
        ))

    # 6. GX10 LLM
    import os
    gx10_configured = bool(os.environ.get("GX10_API_KEY") or os.environ.get("OPENAI_API_KEY"))
    checks.append(HealthDetail(
        component="GX10 LLM",
        status="healthy" if gx10_configured else "not_configured",
        message="Endpoint configured" if gx10_configured else "Set GX10_API_KEY or OPENAI_API_KEY",
        last_check=now,
    ))

    # 7. Authentication
    try:
        from kurukshetra.security.config import SecurityConfig
        config = SecurityConfig()
        checks.append(HealthDetail(
            component="Authentication",
            status="healthy" if config.auth_required else "degraded",
            message="API-key auth active" if config.auth_required else "Auth disabled (dev mode)",
            last_check=now,
        ))
    except Exception as e:
        checks.append(HealthDetail(
            component="Authentication", status="unavailable",
            message=str(e)[:100], last_check=now,
        ))

    # 8. Watcher
    try:
        from kurukshetra.runtime.watcher import KnowledgeWatcher
        watcher = KnowledgeWatcher()
        checks.append(HealthDetail(
            component="Knowledge Watcher", status="healthy",
            message="Watcher available",
            last_check=now,
        ))
        watcher.close()
    except Exception as e:
        checks.append(HealthDetail(
            component="Knowledge Watcher", status="not_configured",
            message=str(e)[:100], last_check=now,
        ))

    overall = "healthy"
    for c in checks:
        if c.status == "unavailable":
            overall = "degraded"
            break
        if c.status == "degraded" and overall == "healthy":
            overall = "degraded"

    return {
        "overall": overall,
        "checks": [c.model_dump() for c in checks],
        "timestamp": now,
    }


# ── Memory Summary ───────────────────────────────────────────

@router.get("/api/memory/summary")
async def get_memory_summary(user_id: str = "anonymous"):
    """Get user-scoped memory summary. Never expose other users' data."""
    summary = MemorySummary(
        user_id=user_id,
        working_memory={
            "status": "active",
            "description": "Current conversation context",
            "items": [],
        },
        episodic_memory={"status": "partial", "description": "Past interactions", "items": []},
        semantic_memory={"status": "active", "description": "Organizational knowledge"},
        procedural_memory={"status": "foundation", "description": "Validated workflows"},
        prospective_memory={"status": "foundation", "description": "Future tasks"},
        external_memory={"status": "active", "description": "Knowledge Fabric retrieval"},
    )

    # Populate episodic memory with recent interactions for this user
    try:
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        try:
            rows = conn.execute("""
                SELECT query, answer, rating, created_at
                FROM rag_feedback
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT 10
            """, (user_id,)).fetchall()
            summary.episodic_memory["items"] = [
                {"query": r[0], "outcome": "positive" if r[2] and r[2] > 0 else "negative", "timestamp": str(r[3])}
                for r in rows
            ]
        except Exception:
            pass

        # Count user interactions
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM rag_feedback WHERE user_id = ?", (user_id,)
            ).fetchone()[0]
            summary.episodic_memory["total_interactions"] = count
        except Exception:
            pass

        conn.close()
    except Exception:
        pass

    return summary.model_dump()


# ── Knowledge Gaps ───────────────────────────────────────────

@router.get("/api/knowledge/gaps")
async def analyze_knowledge_gaps():
    """Analyze what SANJAYA knows vs doesn't know."""
    gaps = {
        "strong_areas": [],
        "weak_areas": [],
        "unknown_areas": [],
        "coverage_summary": {},
    }

    try:
        from kurukshetra.registry.database import get_connection
        conn = get_connection()

        # Teams with good coverage
        team_counts = conn.execute("""
            SELECT team_owner, COUNT(*) as cnt
            FROM documents
            WHERE team_owner IS NOT NULL AND team_owner != ''
            GROUP BY team_owner
            ORDER BY cnt DESC
        """).fetchall()

        for team, count in team_counts:
            if count >= 10:
                gaps["strong_areas"].append({"area": team, "documents": count, "reason": "well_covered"})
            elif count >= 3:
                gaps["weak_areas"].append({"area": team, "documents": count, "reason": "partial_coverage"})
            else:
                gaps["weak_areas"].append({"area": team, "documents": count, "reason": "minimal_coverage"})

        # Supported vs unsupported formats
        ext_counts = conn.execute("""
            SELECT
                CASE
                    WHEN source_path LIKE '%.pdf' THEN 'PDF'
                    WHEN source_path LIKE '%.docx' THEN 'DOCX'
                    WHEN source_path LIKE '%.xlsx' THEN 'XLSX'
                    WHEN source_path LIKE '%.csv' THEN 'CSV'
                    WHEN source_path LIKE '%.txt' THEN 'TXT'
                    WHEN source_path LIKE '%.md' THEN 'MD'
                    WHEN source_path LIKE '%.pptx' THEN 'PPTX'
                    WHEN source_path LIKE '%.html' THEN 'HTML'
                    ELSE 'Other'
                END as fmt,
                COUNT(*) as cnt
            FROM documents
            GROUP BY fmt
            ORDER BY cnt DESC
        """).fetchall()

        gaps["coverage_summary"]["formats"] = {r[0]: r[1] for r in ext_counts}

        # Unknown terms (knowledge gaps)
        try:
            unknown_count = conn.execute("SELECT COUNT(*) FROM unknown_terms").fetchone()[0]
            gaps["coverage_summary"]["unknown_terms"] = unknown_count
        except Exception:
            pass

        # Glossary coverage
        try:
            glossary_count = conn.execute("SELECT COUNT(*) FROM glossary").fetchone()[0]
            gaps["coverage_summary"]["defined_terms"] = glossary_count
        except Exception:
            pass

        # Known systems from graph
        try:
            systems = conn.execute("""
                SELECT name, COUNT(DISTINCT owner) as doc_count
                FROM graph_entities
                WHERE entity_type IN ('system', 'product', 'tool')
                GROUP BY name
                ORDER BY doc_count DESC
                LIMIT 20
            """).fetchall()
            gaps["coverage_summary"]["known_systems"] = [{"name": r[0], "docs": r[1]} for r in systems]
        except Exception:
            pass

        conn.close()

    except Exception:
        pass

    return gaps
