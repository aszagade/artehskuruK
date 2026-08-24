"""Connectors & Agents Router — System integration endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api", tags=["Connectors & Agents"])


@router.get("/agents")
async def list_agents():
    """List all registered agents."""
    try:
        from kurukshetra.agent.registry import AgentRegistry

        registry = AgentRegistry()
        agents = registry.list_agents()

        return [
            {
                "agent_id": a.agent_id,
                "name": a.name,
                "domain": a.domain,
                "role": a.role.value,
                "status": a.status.value,
                "team_owner": a.team_owner,
            }
            for a in agents
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/graph/connectors")
async def list_graph_connectors():
    """List available future connectors."""
    try:
        from kurukshetra.graph.connectors import list_connectors

        return {"connectors": list_connectors()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
