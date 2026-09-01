"""Process Intelligence Router — process discovery and analysis endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/processes", tags=["Process Intelligence"])


@router.get("")
async def list_all_processes(
    team: Optional[str] = None,
    quality: Optional[str] = None,
    limit: int = Query(default=50, le=200),
):
    """List discovered processes with optional filters."""
    try:
        from kurukshetra.process.intelligence import list_processes
        return {"processes": list_processes(team=team, quality=quality, limit=limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def process_stats():
    """Get process intelligence statistics."""
    try:
        from kurukshetra.process.intelligence import get_process_stats
        return get_process_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{process_id}")
async def get_process_detail(process_id: str):
    """Get a process with all its steps and gaps."""
    try:
        from kurukshetra.process.intelligence import get_process
        proc = get_process(process_id)
        if not proc:
            raise HTTPException(status_code=404, detail=f"Process {process_id} not found")
        return proc
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{process_id}/steps")
async def get_process_steps(process_id: str):
    """Get steps for a specific process."""
    try:
        from kurukshetra.process.intelligence import get_process
        proc = get_process(process_id)
        if not proc:
            raise HTTPException(status_code=404, detail=f"Process {process_id} not found")
        return {"process_id": process_id, "steps": proc.get("steps", [])}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{process_id}/evidence")
async def get_process_evidence(process_id: str):
    """Get evidence for a process — why SANJAYA believes these steps exist."""
    try:
        from kurukshetra.process.intelligence import get_process
        proc = get_process(process_id)
        if not proc:
            raise HTTPException(status_code=404, detail=f"Process {process_id} not found")

        evidence = []
        for step in proc.get("steps", []):
            if step.get("evidence_text"):
                evidence.append({
                    "step_id": step["step_id"],
                    "sequence": step["sequence"],
                    "description": step["description"],
                    "evidence_text": step["evidence_text"],
                    "evidence_level": step["evidence_level"],
                    "confidence": step["confidence"],
                    "source_document": step["source_document"],
                    "evidence_chunk": step["evidence_chunk"],
                })
        return {"process_id": process_id, "evidence": evidence}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{process_id}/gaps")
async def get_process_gaps(process_id: str):
    """Get detected structural gaps in a process."""
    try:
        from kurukshetra.process.intelligence import get_process
        proc = get_process(process_id)
        if not proc:
            raise HTTPException(status_code=404, detail=f"Process {process_id} not found")
        return {"process_id": process_id, "gaps": proc.get("gaps", [])}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/discover")
async def discover_processes_from_corpus(
    limit: int = Query(default=50, le=500),
    dry_run: bool = False,
):
    """Run process discovery across the document corpus.

    Extracts processes from documents that contain process language.
    """
    try:
        import duckdb
        from kurukshetra.process.intelligence import (
            ProcessExtractor,
            ProcessGapDetector,
            ensure_process_tables,
            persist_process,
            persist_gaps,
        )

        ensure_process_tables()

        conn = duckdb.connect("kurukshetra_registry.duckdb", read_only=True)

        # Find documents with process-like titles
        rows = conn.execute("""
            SELECT document_id, title, team_owner
            FROM documents
            WHERE LOWER(title) LIKE '%process%'
               OR LOWER(title) LIKE '%workflow%'
               OR LOWER(title) LIKE '%procedure%'
               OR LOWER(title) LIKE '%step%'
               OR LOWER(title) LIKE '%handoff%'
               OR LOWER(title) LIKE '%installation%'
               OR LOWER(title) LIKE '%audit%'
               OR LOWER(title) LIKE '%upload%'
               OR LOWER(title) LIKE '%recovery%'
               OR LOWER(title) LIKE '%communication%'
               OR LOWER(title) LIKE '%handling%'
               OR LOWER(title) LIKE '%guide%'
               OR LOWER(title) LIKE '%charter%'
               OR LOWER(title) LIKE '%integration%'
            LIMIT ?
        """, [limit]).fetchall()
        conn.close()

        extractor = ProcessExtractor()
        detector = ProcessGapDetector()
        discovered = []
        total_steps = 0
        total_gaps = 0

        for doc_id, title, team in rows:
            try:
                processes = extractor.extract_processes_from_document(
                    document_id=doc_id,
                    document_title=title or "",
                    team_id=team,
                )
                for proc in processes:
                    if not dry_run:
                        persist_process(proc)
                        gaps = detector.detect_gaps(proc)
                        if gaps:
                            persist_gaps(gaps)
                            total_gaps += len(gaps)
                    discovered.append({
                        "process_id": proc.process_id,
                        "name": proc.name,
                        "steps": len(proc.steps),
                        "quality": proc.quality,
                        "team": proc.team,
                    })
                    total_steps += len(proc.steps)
            except Exception:
                continue

        return {
            "documents_scanned": len(rows),
            "processes_discovered": len(discovered),
            "total_steps": total_steps,
            "total_gaps": total_gaps,
            "dry_run": dry_run,
            "processes": discovered,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
