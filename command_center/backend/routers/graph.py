"""Graph Intelligence Router — Knowledge Graph endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from kurukshetra.security.deps import get_current_user, require_team
from kurukshetra.security.identity import UserIdentity

router = APIRouter(prefix="/api/graph", tags=["Knowledge Graph"])


@router.get("/stats")
async def get_graph_stats():
    """Get Knowledge Graph statistics."""
    try:
        from kurukshetra.graph.registry import GraphRegistry

        registry = GraphRegistry()
        stats = registry.get_stats()
        registry.close()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entities")
async def search_graph_entities(
    query: str = "",
    entity_type: Optional[str] = None,
    team_id: Optional[str] = None,
    limit: int = 50,
):
    """Search graph entities with optional filters."""
    try:
        from kurukshetra.graph.registry import GraphRegistry

        registry = GraphRegistry()
        entities = registry.search_entities(
            query=query, entity_type=entity_type, team_id=team_id, limit=limit
        )
        registry.close()
        return {"entities": entities, "total": len(entities)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entity/{entity_id}")
async def get_entity_context(entity_id: str, depth: int = 2):
    """Get full context for an entity (metadata + neighborhood)."""
    try:
        from kurukshetra.graph.registry import GraphRegistry

        registry = GraphRegistry()
        context = registry.get_entity_context(entity_id, depth=depth)
        registry.close()

        if context is None:
            raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")
        return context
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/path")
async def find_graph_path(source_id: str, target_id: str):
    """Find shortest path between two entities."""
    try:
        from kurukshetra.graph.registry import GraphRegistry

        registry = GraphRegistry()
        path = registry.find_path(source_id, target_id)
        registry.close()

        if path is None:
            return {"path": None, "message": "No path found"}
        return path
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/impact/{entity_id}")
async def analyze_entity_impact(entity_id: str, max_depth: int = 3):
    """Analyze the impact of an entity change."""
    try:
        from kurukshetra.graph.registry import GraphRegistry

        registry = GraphRegistry()
        impact = registry.analyze_impact(entity_id, max_depth=max_depth)
        registry.close()
        return impact
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/communities")
async def get_graph_communities():
    """Detect communities (clusters) in the knowledge graph."""
    try:
        from kurukshetra.graph.registry import GraphRegistry

        registry = GraphRegistry()
        communities = registry.get_communities()
        registry.close()
        return {"communities": communities, "total": len(communities)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/team/{team_id}")
async def get_team_subgraph(team_id: str):
    """Get the subgraph for a specific team."""
    try:
        from kurukshetra.graph.registry import GraphRegistry

        registry = GraphRegistry()
        subgraph = registry.get_team_graph(team_id)
        registry.close()
        return subgraph
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/entity/{entity_id}/confirm")
async def confirm_entity(
    entity_id: str,
    user: UserIdentity = Depends(require_team("spm", "ics", "sdops", "cpm", "roa", "hr", "it")),
):
    """Mark an entity as human-confirmed (for SEAL learning)."""
    try:
        from kurukshetra.graph.registry import GraphRegistry

        registry = GraphRegistry()
        registry.confirm_entity(entity_id)
        registry.close()
        return {"status": "confirmed", "entity_id": entity_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
