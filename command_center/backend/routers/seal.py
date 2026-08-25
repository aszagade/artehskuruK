"""SEAL Router — Self-Evolving Adaptive Learning endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from kurukshetra.security.deps import get_current_user
from kurukshetra.security.identity import UserIdentity

router = APIRouter(prefix="/api/glossary", tags=["SEAL Learning"])


@router.get("/pending")
async def get_pending_glossary_terms(
    user: UserIdentity = Depends(get_current_user),
):
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
