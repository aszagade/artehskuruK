"""Graph Intelligence Router — Knowledge Graph endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from kurukshetra.security.deps import get_current_user, require_team
from kurukshetra.security.identity import UserIdentity

router = APIRouter(prefix="/api/graph", tags=["Knowledge Graph"])

# Relationship types to skip in visualization (ingestion artifacts)
_SKIP_RELATION_TYPES = {"contains", "generated_from"}


def _get_conn():
    """Get a DuckDB connection using the shared registry connection."""
    from kurukshetra.registry.database import get_connection
    return get_connection()


def _resolve_team_id(raw_team: str, node_ids: set[str]) -> str:
    """Resolve a team ID to its canonical form in the graph.

    Teams exist as: TEAM-SPM, team:TEAM-SPM, team:spm, TEAM-ICS, etc.
    Returns the first matching canonical ID.
    """
    candidates = [
        f"TEAM-{raw_team.upper()}",
        f"team:{raw_team}",
        f"team:TEAM-{raw_team.upper()}",
        raw_team,
        raw_team.upper(),
    ]
    for c in candidates:
        if c in node_ids:
            return c
    # Not found — use first canonical form
    return f"TEAM-{raw_team.upper()}"


# ─── Original endpoints (preserved) ──────────────────────────────────────────


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
    user: UserIdentity = Depends(
        require_team("spm", "ics", "sdops", "cpm", "roa", "hr", "it")
    ),
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


# ─── New visualization endpoints ─────────────────────────────────────────────


@router.get("/visualization")
async def get_graph_visualization(
    entity_type: Optional[str] = None,
    team_id: Optional[str] = None,
    quality_min: float = 0.0,
    exclude_noise: bool = True,
    limit: int = Query(default=200, le=500),
):
    """Canonical graph API for frontend visualization.

    Returns quality-filtered nodes and derived entity-to-entity edges.
    The graph derives system-team / system-system / team-team relationships
    from document co-occurrence (DOC uses SYS + DOC owned_by TEAM → SYS ↔ TEAM).
    """
    try:
        conn = _get_conn()

        # ── Build entity query ────────────────────────────────────────────
        eq = ["1=1"]
        params: list = []
        if entity_type:
            eq.append("ge.entity_type = ?")
            params.append(entity_type)
        if team_id:
            eq.append("gem.team_id = ?")
            params.append(team_id)
        if exclude_noise:
            eq.append("ge.quality_label != 'NOISE'")
        if quality_min > 0:
            eq.append("COALESCE(ge.quality_score, 0) >= ?")
            params.append(quality_min)
        ew = " AND ".join(eq)

        entity_rows = conn.execute(
            f"""
            SELECT ge.id, ge.name, ge.entity_type, ge.description,
                   ge.quality_score, ge.quality_label, ge.owner,
                   gem.team_id, gem.average_confidence
            FROM graph_entities ge
            LEFT JOIN graph_entity_meta gem ON ge.id = gem.entity_id
            WHERE {ew}
            ORDER BY COALESCE(ge.quality_score, 0) DESC,
                     COALESCE(gem.average_confidence, 0) DESC
            LIMIT ?
            """,
            params + [min(limit, 500)],
        ).fetchall()

        node_ids: set[str] = set()
        nodes: list[dict] = []
        for r in entity_rows:
            node_ids.add(r[0])
            nodes.append(
                {
                    "id": r[0],
                    "label": r[1],
                    "type": r[2],
                    "description": r[3] or "",
                    "quality": round(r[4] or 0, 3),
                    "qualityLabel": r[5] or "MEDIUM",
                    "owner": r[6],
                    "teamId": r[7],
                    "confidence": round(r[8] or 0, 3),
                }
            )

        # ── Direct entity-entity edges (non-DOC/CHUNK) ────────────────────
        rel_rows = conn.execute(
            """
            SELECT source_id, target_id, relation_type, description, confidence
            FROM graph_relationships
            WHERE relation_type NOT IN ('contains', 'generated_from')
        """
        ).fetchall()

        edges: list[dict] = []
        seen_edges: set[tuple] = set()
        for r in rel_rows:
            if r[0] == r[1]:
                continue  # skip self-loops
            key = (r[0], r[1], r[2])
            if r[0] in node_ids and r[1] in node_ids and key not in seen_edges:
                seen_edges.add(key)
                edges.append(
                    {
                        "source": r[0],
                        "target": r[1],
                        "relationship": r[2],
                        "description": r[3] or "",
                        "confidence": round(r[4] or 0, 3),
                    }
                )

        # ── Derive entity co-occurrence edges ─────────────────────────────
        # If DOC uses SYS_A and DOC uses SYS_B → SYS_A ↔ SYS_B (co-occurrence)
        # If DOC uses SYS and DOC owned_by TEAM → SYS ↔ TEAM (association)
        doc_sys_rows = conn.execute(
            """
            SELECT source_id, target_id, relation_type
            FROM graph_relationships
            WHERE relation_type = 'uses'
              AND source_id LIKE 'DOC-%'
              AND target_id LIKE 'SYS-%'
        """
        ).fetchall()

        doc_team_rows = conn.execute(
            """
            SELECT source_id, target_id, relation_type
            FROM graph_relationships
            WHERE relation_type = 'owned_by'
              AND source_id LIKE 'DOC-%'
              AND target_id LIKE 'TEAM-%'
        """
        ).fetchall()

        # DOC → set of SYS it uses
        doc_to_sys: dict[str, list[str]] = {}
        for r in doc_sys_rows:
            doc_to_sys.setdefault(r[0], []).append(r[1])

        # DOC → TEAM it belongs to
        doc_to_team: dict[str, str] = {}
        for r in doc_team_rows:
            doc_to_team[r[0]] = r[1]

        # Build co-occurrence edges
        sys_sys_count: dict[tuple, int] = {}
        sys_team_count: dict[tuple, int] = {}

        for doc_id, sys_list in doc_to_sys.items():
            team_id_val = doc_to_team.get(doc_id)
            # SYS ↔ SYS co-occurrence
            for i in range(len(sys_list)):
                for j in range(i + 1, len(sys_list)):
                    key = tuple(sorted([sys_list[i], sys_list[j]]))
                    sys_sys_count[key] = sys_sys_count.get(key, 0) + 1
            # SYS ↔ TEAM association
            if team_id_val:
                for sys_id in sys_list:
                    key = (sys_id, team_id_val)
                    sys_team_count[key] = sys_team_count.get(key, 0) + 1

        # Add derived SYS ↔ SYS edges
        for (s1, s2), count in sys_sys_count.items():
            if s1 in node_ids and s2 in node_ids:
                key = (s1, s2, "co_occurs")
                if key not in seen_edges:
                    seen_edges.add(key)
                    conf = min(1.0, 0.3 + count * 0.05)
                    edges.append(
                        {
                            "source": s1,
                            "target": s2,
                            "relationship": "co_occurs",
                            "description": f"Appears together in {count} document(s)",
                            "confidence": round(conf, 3),
                            "derived": True,
                        }
                    )

        # Add derived SYS ↔ TEAM edges
        for (sys_id, tm_id), count in sys_team_count.items():
            # tm_id is like "TEAM-SPM" from graph_relationships
            team_canonical = _resolve_team_id(tm_id.replace("TEAM-", "").lower(), node_ids)
            if team_canonical not in node_ids:
                # Create synthetic team node
                node_ids.add(team_canonical)
                nodes.append(
                    {
                        "id": team_canonical,
                        "label": tm_id.replace("TEAM-", "").upper(),
                        "type": "team",
                        "description": f"Team: {tm_id}",
                        "quality": 0.9,
                        "qualityLabel": "HIGH",
                        "owner": tm_id,
                        "teamId": tm_id,
                        "confidence": 0.9,
                    }
                )
            if sys_id in node_ids:
                key = (sys_id, team_canonical, "used_by_team")
                if key not in seen_edges:
                    seen_edges.add(key)
                    conf = min(1.0, 0.4 + count * 0.03)
                    edges.append(
                        {
                            "source": sys_id,
                            "target": team_canonical,
                            "relationship": "used_by_team",
                            "description": f"Used in {count} document(s) owned by {tm_id.upper()}",
                            "confidence": round(conf, 3),
                            "derived": True,
                        }
                    )

        # ── Concept-team synthetic edges ──────────────────────────────────
        ct_rows = conn.execute(
            """
            SELECT concept_name, team_id, confidence
            FROM concept_teams
            WHERE team_id IS NOT NULL
              AND concept_name NOT LIKE 'tmp%'
              AND LENGTH(concept_name) > 2
        """
        ).fetchall()

        for r in ct_rows:
            # Find matching entity
            match = [n for n in nodes if n["label"].lower() == r[0].lower()]
            # Normalize team_id: try TEAM-{id}, team:{id}, lowercase
            canonical_team = _resolve_team_id(r[1], node_ids)
            if match and match[0]["id"] != canonical_team:
                key = (match[0]["id"], canonical_team, "associated_with")
                if key not in seen_edges:
                    seen_edges.add(key)
                    edges.append(
                        {
                            "source": match[0]["id"],
                            "target": canonical_team,
                            "relationship": "associated_with",
                            "description": f"Concept-team association",
                            "confidence": round(r[2] or 0.5, 3),
                            "derived": True,
                        }
                    )

        conn.close()

        # ── Statistics ────────────────────────────────────────────────────
        type_counts: dict[str, int] = {}
        for n in nodes:
            t = n["type"]
            type_counts[t] = type_counts.get(t, 0) + 1

        return {
            "nodes": nodes,
            "edges": edges,
            "meta": {
                "totalNodes": len(nodes),
                "totalEdges": len(edges),
                "nodesByType": type_counts,
                "filtered": exclude_noise,
                "qualityMin": quality_min,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/neighborhood/{entity_id}")
async def get_entity_neighborhood(
    entity_id: str,
    depth: int = Query(default=1, le=3),
    limit: int = Query(default=50, le=200),
):
    """Get one-hop or two-hop neighborhood for a specific entity."""
    try:
        conn = _get_conn()

        def _get_entity(eid: str) -> Optional[dict]:
            row = conn.execute(
                """
                SELECT ge.id, ge.name, ge.entity_type, ge.description,
                       ge.quality_score, ge.quality_label, ge.owner,
                       gem.team_id, gem.average_confidence
                FROM graph_entities ge
                LEFT JOIN graph_entity_meta gem ON ge.id = gem.entity_id
                WHERE ge.id = ?
            """,
                [eid],
            ).fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "label": row[1],
                "type": row[2],
                "description": row[3] or "",
                "quality": round(row[4] or 0, 3),
                "qualityLabel": row[5] or "MEDIUM",
                "owner": row[6],
                "teamId": row[7],
                "confidence": round(row[8] or 0, 3),
            }

        center = _get_entity(entity_id)
        if not center:
            conn.close()
            raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")

        # BFS expansion
        visited: set[str] = {entity_id}
        frontier: set[str] = {entity_id}
        all_nodes: list[dict] = [center]
        all_edges: list[dict] = []
        seen_edges: set[tuple] = set()

        for _ in range(depth):
            next_frontier: set[str] = set()
            for eid in frontier:
                rels = conn.execute(
                    """
                    SELECT source_id, target_id, relation_type, description, confidence
                    FROM graph_relationships
                    WHERE (source_id = ? OR target_id = ?)
                      AND relation_type NOT IN ('contains', 'generated_from')
                    LIMIT 100
                """,
                    [eid, eid],
                ).fetchall()
                for r in rels:
                    other = r[1] if r[0] == eid else r[0]
                    key = (r[0], r[1], r[2])
                    if key not in seen_edges:
                        seen_edges.add(key)
                        all_edges.append(
                            {
                                "source": r[0],
                                "target": r[1],
                                "relationship": r[2],
                                "description": r[3] or "",
                                "confidence": round(r[4] or 0, 3),
                            }
                        )
                    if other not in visited and len(all_nodes) < limit:
                        visited.add(other)
                        next_frontier.add(other)
                        entity = _get_entity(other)
                        if entity:
                            all_nodes.append(entity)
            frontier = next_frontier

        conn.close()
        return {
            "center": center,
            "nodes": all_nodes,
            "edges": all_edges[:500],
            "meta": {
                "depth": depth,
                "totalNodes": len(all_nodes),
                "totalEdges": len(all_edges),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entity-types")
async def get_entity_type_counts():
    """Get entity counts by type with quality breakdown."""
    try:
        conn = _get_conn()
        rows = conn.execute(
            """
            SELECT entity_type, quality_label, COUNT(*) as cnt
            FROM graph_entities
            GROUP BY entity_type, quality_label
            ORDER BY entity_type, cnt DESC
        """
        ).fetchall()
        conn.close()

        result: dict[str, dict] = {}
        for r in rows:
            if r[0] not in result:
                result[r[0]] = {}
            result[r[0]][r[1]] = r[2]
        return {"types": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/teams")
async def get_teams_summary():
    """Get all teams with their entity counts and systems."""
    try:
        conn = _get_conn()
        rows = conn.execute(
            """
            SELECT gem.team_id, COUNT(*) as entity_count,
                   GROUP_CONCAT(DISTINCT ge.entity_type) as entity_types
            FROM graph_entity_meta gem
            JOIN graph_entities ge ON gem.entity_id = ge.id
            WHERE gem.team_id IS NOT NULL AND gem.team_id != ''
            GROUP BY gem.team_id
            ORDER BY entity_count DESC
        """
        ).fetchall()
        conn.close()

        teams = []
        for r in rows:
            teams.append(
                {
                    "teamId": r[0],
                    "entityCount": r[1],
                    "entityTypes": r[2].split(",") if r[2] else [],
                }
            )
        return {"teams": teams, "total": len(teams)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sanjaya-context")
async def get_sanjaya_context(entity_id: str):
    """Get SANJAYA-ready context for a selected graph entity.

    Returns the entity plus a suggested question the user can ask.
    Does NOT bypass authorization — the question must still go through
    the normal retrieval pipeline.
    """
    try:
        conn = _get_conn()
        row = conn.execute(
            """
            SELECT ge.id, ge.name, ge.entity_type, ge.description
            FROM graph_entities ge WHERE ge.id = ?
        """,
            [entity_id],
        ).fetchone()
        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")

        entity_name = row[1]
        entity_type = row[2]

        # Build suggested question
        if entity_type == "system":
            question = f"What do you know about {entity_name}?"
        elif entity_type == "team":
            question = f"What does the {entity_name} team work on?"
        elif entity_type == "process":
            question = f"How does {entity_name} work?"
        elif entity_type == "configuration":
            question = f"What is the configuration for {entity_name}?"
        else:
            question = f"What is {entity_name}?"

        return {
            "entity": {
                "id": row[0],
                "label": row[1],
                "type": row[2],
                "description": row[3] or "",
            },
            "suggestedQuestion": question,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
