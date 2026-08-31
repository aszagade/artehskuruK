"""Knowledge Fabric Router — SANJAYA Brain endpoints."""
from __future__ import annotations

import hashlib
import os
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/knowledge", tags=["Knowledge Fabric"])

# Upload configuration
UPLOAD_DIR = Path.cwd() / "knowledge" / "inbox" / "uploads"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "text/csv",
    "text/plain",
    "text/markdown",
    "text/html",
    "application/json",
    "application/xml",
    "text/xml",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
ALLOWED_EXTENSIONS = {
    ".pdf", ".docx", ".xlsx", ".xls", ".csv",
    ".txt", ".md", ".rst", ".html", ".htm",
    ".json", ".xml", ".pptx",
}
DANGEROUS_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".sh", ".ps1", ".vbs",
    ".js", ".py", ".rb", ".php", ".jsp", ".asp",
    ".com", ".scr", ".pif", ".msi", ".dll",
    ".pyc", ".pyo", ",so", ".dylib",
}


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


class UploadResponse(BaseModel):
    """Document upload response."""
    document_id: str
    filename: str
    status: str  # "ok", "duplicate", "error"
    message: str
    chunks_stored: int = 0
    entities_extracted: int = 0
    team_id: str = "unknown"
    execution_time_ms: float = 0.0


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


@router.post("/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)):
    """
    Upload a document for ingestion into the knowledge base.

    Accepts files via multipart/form-data upload. The file is saved
    to a safe internal directory, then routed through KnowledgeFabric
    for extraction, chunking, embedding, and graph ingestion.

    Security:
    - Validates file extension and MIME type
    - Rejects dangerous extensions (exe, bat, etc.)
    - Enforces 50 MB file size limit
    - Prevents path traversal in filename
    - Saves to safe internal directory only
    - Preserves user/source identity via provenance
    """
    start = time.time()

    try:
        # 1. Validate filename
        original_name = file.filename or "unknown"
        safe_name = Path(original_name).name  # Strip any path components
        if not safe_name or safe_name.startswith("."):
            raise HTTPException(
                status_code=400,
                detail="Invalid filename"
            )

        # 2. Check extension
        ext = Path(safe_name).suffix.lower()
        if ext in DANGEROUS_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File type '{ext}' is not allowed for security reasons"
            )
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
            detail=(
                    f"Unsupported file type '{ext}'. "
                    f"Supported: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
                ),
            )

        # 3. Check MIME type (if provided)
        if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
            # Allow if extension is valid (some clients send wrong MIME)
            if ext not in ALLOWED_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported content type: {file.content_type}"
                )

        # 4. Read file content
        content = await file.read()

        # 5. Check file size
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large: {len(content)} bytes (max {MAX_FILE_SIZE} bytes)"
            )

        if len(content) == 0:
            raise HTTPException(
                status_code=400,
                detail="Empty file not accepted"
            )

        # 6. Ensure upload directory exists
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

        # 7. Generate unique filename to prevent overwrites
        content_hash = hashlib.sha256(content).hexdigest()[:12]
        upload_name = f"{content_hash}_{safe_name}"
        upload_path = UPLOAD_DIR / upload_name

        # 8. Save file
        upload_path.write_bytes(content)

        # 9. Validate the saved file exists and is readable
        if not upload_path.exists() or upload_path.stat().st_size == 0:
            raise HTTPException(
                status_code=500,
                detail="Failed to save uploaded file"
            )

        # 10. Route through KnowledgeFabric
        from kurukshetra.knowledge.fabric import KnowledgeFabric
        fabric = KnowledgeFabric()
        try:
            result = fabric.ingest_file(upload_path)
        finally:
            fabric.close()

        execution_time = (time.time() - start) * 1000
        team_id = result.teams_detected[0] if result.teams_detected else "unknown"

        if result.error:
            return UploadResponse(
                document_id=result.document_id or "",
                filename=safe_name,
                status="error",
                message=str(result.error),
                execution_time_ms=round(execution_time, 1),
            )

        return UploadResponse(
            document_id=result.document_id,
            filename=safe_name,
            status="ok",
            message=f"Document ingested successfully: {result.chunks_stored} chunks, "
                    f"{result.entities_extracted} entities",
            chunks_stored=result.chunks_stored,
            entities_extracted=result.entities_extracted,
            team_id=team_id,
            execution_time_ms=round(execution_time, 1),
        )

    except HTTPException:
        raise
    except Exception as e:
        execution_time = (time.time() - start) * 1000
        return UploadResponse(
            document_id="",
            filename=file.filename or "unknown",
            status="error",
            message=str(e),
            execution_time_ms=round(execution_time, 1),
        )


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
