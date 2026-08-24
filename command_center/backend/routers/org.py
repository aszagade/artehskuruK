"""Org Map Router — Organizational hierarchy endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/org", tags=["Org Map"])


@router.get("/map")
async def get_org_map():
    """Get the full organizational hierarchy."""
    try:
        from kurukshetra.agent.org_map import OrgMap

        org = OrgMap()
        teams = org.get_all_teams()

        return {
            "organization": "IDeaS Service Delivery",
            "teams": [
                {
                    "team_id": t.team_id,
                    "name": t.name,
                    "full_name": t.full_name,
                    "type": t.team_type.value,
                    "description": t.description,
                    "products": t.product_scope,
                    "sub_teams": [
                        {"id": s.sub_team_id, "name": s.name, "focus": s.agent_focus}
                        for s in t.sub_teams
                    ],
                    "related_teams": t.related_teams,
                    "capabilities": t.agent_capabilities,
                }
                for t in teams
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/classify")
async def classify_document_team(file_path: str):
    """Classify which team a document belongs to."""
    try:
        from kurukshetra.services.team_classifier import TeamClassifier
        from kurukshetra.extractors import PDFExtractor

        classifier = TeamClassifier()
        extractor = PDFExtractor()

        path = Path(file_path)
        text = extractor.extract(path)

        result = classifier.classify_document(
            text=text,
            filename=path.name,
            document_id="",
        )

        return {
            "filename": path.name,
            "primary_team": result.primary_team_name,
            "primary_team_id": result.primary_team_id,
            "confidence": result.confidence,
            "is_cross_team": result.is_cross_team,
            "all_matches": result.all_team_matches[:5],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/classify-query")
async def classify_query_team(body: dict):
    """Classify which team a query should route to."""
    try:
        from kurukshetra.services.team_classifier import TeamClassifier

        classifier = TeamClassifier()
        query = body.get("query", "")

        results = classifier.classify_query(query)

        return {
            "query": query,
            "team_matches": results[:5],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/team/{team_id}/documents")
async def get_team_documents(team_id: str):
    """Get all documents belonging to a specific team."""
    try:
        from kurukshetra.services.team_classifier import TeamClassifier

        classifier = TeamClassifier()
        docs = classifier.get_documents_by_team(team_id)

        return {
            "team_id": team_id,
            "documents": docs,
            "total": len(docs),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cross-team")
async def get_cross_team_documents():
    """Get documents that belong to multiple teams."""
    try:
        from kurukshetra.services.team_classifier import TeamClassifier

        classifier = TeamClassifier()
        docs = classifier.get_cross_team_documents()

        return {
            "cross_team_documents": docs,
            "total": len(docs),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_org_stats():
    """Get team classification statistics."""
    try:
        from kurukshetra.services.team_classifier import TeamClassifier

        classifier = TeamClassifier()
        stats = classifier.get_team_stats()

        return {
            "team_stats": stats,
            "total_classified": sum(s["document_count"] for s in stats.values()),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
