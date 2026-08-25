"""Knowledge Fabric Router — SANJAYA Brain endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/knowledge", tags=["Knowledge Fabric"])


class KnowledgeStateResponse(BaseModel):
    """Machine-readable knowledge state."""
    total_documents: int
    total_chunks: int
    total_entities: int
    total_relationships: int
    total_evidence: int
    total_glossary_terms: int
    total_unknown_terms: int
    total_concepts: int
    total_conflicts: int
    total_versions: int
    teams_represented: list[str]
    documents_by_state: dict[str, int]
    documents_by_team: dict[str, int]
    recent_changes: list[dict]
    active_conflicts: list[dict]
    last_scan_time: str | None
    freshness_summary: dict[str, int]


class ScanRequest(BaseModel):
    """Request to scan a source directory."""
    source_path: str = Field(..., description="Directory path to scan")


class ScanResponse(BaseModel):
    """Result of scanning a source directory."""
    source_path: str
    scan_time: float
    files_found: int
    new_files: int
    changed_files: int
    unchanged_files: int
    removed_files: int
    errors: list[str]


class ConceptTeamsResponse(BaseModel):
    """Multi-team associations for a concept."""
    concept_name: str
    teams: list[dict]


@router.get("/state", response_model=KnowledgeStateResponse)
async def get_knowledge_state():
    """Get the machine-readable knowledge state for SANJAYA Brain."""
    try:
        from kurukshetra.knowledge.fabric import KnowledgeFabric

        fabric = KnowledgeFabric()
        state = fabric.get_knowledge_state()
        fabric.close()

        return KnowledgeStateResponse(
            total_documents=state.total_documents,
            total_chunks=state.total_chunks,
            total_entities=state.total_entities,
            total_relationships=state.total_relationships,
            total_evidence=state.total_evidence,
            total_glossary_terms=state.total_glossary_terms,
            total_unknown_terms=state.total_unknown_terms,
            total_concepts=state.total_concepts,
            total_conflicts=state.total_conflicts,
            total_versions=state.total_versions,
            teams_represented=state.teams_represented,
            documents_by_state=state.documents_by_state,
            documents_by_team=state.documents_by_team,
            recent_changes=state.recent_changes,
            active_conflicts=state.active_conflicts,
            last_scan_time=state.last_scan_time,
            freshness_summary=state.freshness_summary,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scan", response_model=ScanResponse)
async def scan_source(request: ScanRequest):
    """Scan a source directory for new/changed documents."""
    try:
        from kurukshetra.knowledge.fabric import KnowledgeFabric

        fabric = KnowledgeFabric()
        result = fabric.scan_source(request.source_path)
        fabric.close()

        return ScanResponse(
            source_path=result.source_path,
            scan_time=result.scan_time,
            files_found=result.files_found,
            new_files=result.new_files,
            changed_files=result.changed_files,
            unchanged_files=result.unchanged_files,
            removed_files=result.removed_files,
            errors=result.errors,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/concept/{concept_name}/teams", response_model=ConceptTeamsResponse)
async def get_concept_teams(concept_name: str):
    """Get all team associations for a concept."""
    try:
        from kurukshetra.knowledge.fabric import KnowledgeFabric

        fabric = KnowledgeFabric()
        teams = fabric.get_concept_teams(concept_name)
        fabric.close()

        return ConceptTeamsResponse(
            concept_name=concept_name,
            teams=teams,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{document_id}")
async def get_document_history(document_id: str):
    """Get version history for a document."""
    try:
        from kurukshetra.knowledge.fabric import KnowledgeFabric

        fabric = KnowledgeFabric()
        history = fabric.get_document_history(document_id)
        fabric.close()

        return {"document_id": document_id, "versions": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conflicts")
async def get_conflicts():
    """Get all unresolved knowledge conflicts."""
    try:
        from kurukshetra.registry.database import get_connection

        conn = get_connection()
        rows = conn.execute(
            """SELECT conflict_id, conflict_type, entity_name,
            source_a, source_b, description, detected_at
            FROM knowledge_conflicts WHERE resolved = FALSE"""
        ).fetchall()
        conn.close()

        return {
            "conflicts": [
                {"conflict_id": r[0], "type": r[1], "entity": r[2],
                 "source_a": r[3], "source_b": r[4],
                 "description": r[5], "detected_at": str(r[6])}
                for r in rows
            ],
            "total": len(rows),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------------------------------------------------
# Watcher endpoints
# -----------------------------------------------------------------------

@router.get("/watcher/status")
async def get_watcher_status():
    """Get the current watcher status."""
    try:
        from kurukshetra.runtime.watcher_manager import get_watcher_manager
        manager = get_watcher_manager()
        return manager.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/watcher/trigger")
async def trigger_watcher():
    """Manually trigger a scan-and-ingest cycle."""
    try:
        from kurukshetra.runtime.watcher_manager import get_watcher_manager
        manager = get_watcher_manager()
        return manager.trigger()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
