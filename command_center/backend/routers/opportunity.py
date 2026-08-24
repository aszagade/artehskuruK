"""Opportunity Engine Router — Enterprise pattern analysis endpoints.

Currently a placeholder. Endpoints will be added when the UI
requires them (Mission 3.1 backend API completion).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/opportunities", tags=["Opportunity Engine"])


@router.get("")
async def list_opportunities():
    """List all detected opportunities."""
    try:
        from kurukshetra.opportunity.repository import OpportunityRepository

        repo = OpportunityRepository()
        opps = repo.get_opportunities()
        return {"opportunities": opps, "total": len(opps)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run")
async def run_detection():
    """Run the opportunity detector against stored events."""
    try:
        from kurukshetra.opportunity.detector import OpportunityDetector

        detector = OpportunityDetector()
        result = detector.run()
        return {
            "opportunities_found": result.opportunities_found,
            "events_analyzed": result.events_analyzed,
            "categories": result.categories,
            "elapsed_seconds": result.elapsed_seconds,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
