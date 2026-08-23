"""
Graph Traversal Engine
======================

Provides intelligent traversal of the Knowledge Graph:
  - Pathfinding between any two entities
  - Impact analysis (what is affected by an entity)
  - Context expansion (multi-hop neighborhood)
  - Community detection (clusters of related entities)
  - Distance computation

This is the reasoning layer that sits on top of the Graph Repository.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Optional

from .models import Entity, Relationship, EntityType, RelationType
from .repository import GraphRepository
from .entity_types import ExtendedRelationType


# =====================================================================
# Traversal result types
# =====================================================================

@dataclass(slots=True)
class PathResult:
    """Result of a pathfinding query."""
    source_id: str
    target_id: str
    path: list[str]                  # entity_ids in order
    path_names: list[str]            # entity names in order
    path_types: list[str]            # entity types in order
    path_relations: list[str]        # relationship types in order
    total_confidence: float          # product of edge confidences
    hops: int                        # number of edges traversed


@dataclass(slots=True)
class ImpactResult:
    """Result of an impact analysis."""
    source_id: str
    source_name: str
    affected_entities: list[dict]    # [{id, name, type, distance, confidence}]
    total_affected: int
    impact_score: float              # 0.0–1.0, higher = more impact


@dataclass(slots=True)
class ContextResult:
    """Result of a context expansion query."""
    entity_id: str
    entity_name: str
    entity_type: str
    neighborhood: list[dict]         # [{id, name, type, relation, confidence}]
    depth: int                       # traversal depth used
    total_neighbors: int


@dataclass(slots=True)
class CommunityResult:
    """A detected community (cluster) of related entities."""
    community_id: int
    entity_ids: list[str]
    entity_names: list[str]
    entity_types: list[str]
    internal_edges: int
    cohesion_score: float            # internal edges / possible edges


# =====================================================================
# Graph Traversal Engine
# =====================================================================

class GraphTraversalEngine:
    """
    Intelligent traversal of the Knowledge Graph.

    Operates on the DuckDB-backed GraphRepository and provides:
    - BFS/DFS traversal
    - Shortest path finding
    - Impact analysis (forward traversal from a source)
    - Context expansion (neighborhood at depth N)
    - Simple community detection (connected components)
    """

    def __init__(self, repository: Optional[GraphRepository] = None) -> None:
        self.repository = repository or GraphRepository()
        self._adjacency_cache: Optional[dict[str, list[dict]]] = None

    # -----------------------------------------------------------------
    # Core traversal primitives
    # -----------------------------------------------------------------

    def _build_adjacency(self) -> dict[str, list[dict]]:
        """Build adjacency list from graph_relationships table."""
        if self._adjacency_cache is not None:
            return self._adjacency_cache

        conn = self.repository.get_connection()
        rows = conn.execute("""
            SELECT source_id, target_id, relation_type, confidence, description
            FROM graph_relationships
        """).fetchall()

        adj: dict[str, list[dict]] = defaultdict(list)

        for row in rows:
            source_id, target_id, rel_type, conf, desc = row
            # Forward edge
            adj[source_id].append({
                "target": target_id,
                "relation": rel_type,
                "confidence": conf or 0.5,
                "description": desc,
            })
            # Reverse edge (bidirectional traversal)
            adj[target_id].append({
                "target": source_id,
                "relation": rel_type,
                "confidence": conf or 0.5,
                "description": desc,
            })

        self._adjacency_cache = dict(adj)
        return self._adjacency_cache

    def invalidate_cache(self) -> None:
        """Clear the adjacency cache (call after graph mutations)."""
        self._adjacency_cache = None

    # -----------------------------------------------------------------
    # Pathfinding
    # -----------------------------------------------------------------

    def find_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 6,
    ) -> Optional[PathResult]:
        """
        Find the shortest path between two entities using BFS.

        Args:
            source_id: starting entity ID
            target_id: destination entity ID
            max_depth: maximum hops to search

        Returns:
            PathResult if a path exists, None otherwise
        """
        adj = self._build_adjacency()

        if source_id not in adj or target_id not in adj:
            return None

        # BFS with parent tracking
        visited: set[str] = {source_id}
        queue: deque[tuple[str, list[str], list[str], list[str], float]] = deque()
        queue.append((source_id, [source_id], [], [], 1.0))

        while queue:
            current, path, rels, confs, total_conf = queue.popleft()

            if current == target_id:
                # Build result
                path_names = []
                path_types = []
                for eid in path:
                    entity = self.repository.get_entity(eid)
                    path_names.append(entity.name if entity else eid)
                    path_types.append(entity.entity_type.value if entity else "unknown")

                return PathResult(
                    source_id=source_id,
                    target_id=target_id,
                    path=path,
                    path_names=path_names,
                    path_types=path_types,
                    path_relations=rels,
                    total_confidence=round(total_conf, 4),
                    hops=len(path) - 1,
                )

            if len(path) > max_depth:
                continue

            for edge in adj.get(current, []):
                next_id = edge["target"]
                if next_id not in visited:
                    visited.add(next_id)
                    queue.append((
                        next_id,
                        path + [next_id],
                        rels + [edge["relation"]],
                        confs + [edge["confidence"]],
                        total_conf * edge["confidence"],
                    ))

        return None

    # -----------------------------------------------------------------
    # Impact analysis
    # -----------------------------------------------------------------

    def analyze_impact(
        self,
        entity_id: str,
        max_depth: int = 3,
        min_confidence: float = 0.3,
    ) -> ImpactResult:
        """
        Analyze the impact of an entity by traversing forward.

        Finds all entities reachable from the source and calculates
        an aggregate impact score.

        Args:
            entity_id: entity to analyze
            max_depth: maximum traversal depth
            min_confidence: minimum confidence to include an edge

        Returns:
            ImpactResult with affected entities and impact score
        """
        adj = self._build_adjacency()
        source_entity = self.repository.get_entity(entity_id)

        if not source_entity:
            return ImpactResult(
                source_id=entity_id,
                source_name="UNKNOWN",
                affected_entities=[],
                total_affected=0,
                impact_score=0.0,
            )

        # BFS traversal with depth and confidence tracking
        visited: dict[str, tuple[int, float]] = {entity_id: (0, 1.0)}
        queue: deque[tuple[str, int, float]] = deque()
        queue.append((entity_id, 0, 1.0))

        affected: list[dict] = []

        while queue:
            current, depth, path_conf = queue.popleft()

            if depth >= max_depth:
                continue

            for edge in adj.get(current, []):
                next_id = edge["target"]
                edge_conf = edge["confidence"]

                if edge_conf < min_confidence:
                    continue

                new_depth = depth + 1
                new_conf = path_conf * edge_conf

                if next_id not in visited or visited[next_id][1] < new_conf:
                    visited[next_id] = (new_depth, new_conf)
                    queue.append((next_id, new_depth, new_conf))

                    # Don't include self in affected
                    if next_id != entity_id:
                        entity = self.repository.get_entity(next_id)
                        if entity:
                            affected.append({
                                "id": next_id,
                                "name": entity.name,
                                "type": entity.entity_type.value,
                                "distance": new_depth,
                                "confidence": round(new_conf, 4),
                            })

        # Sort by distance then confidence
        affected.sort(key=lambda x: (x["distance"], -x["confidence"]))

        # Calculate impact score
        if affected:
            # Score = f(number of affected, depth diversity, confidence)
            count_signal = min(len(affected) / 10.0, 0.4)
            depth_signal = min(max(a["distance"] for a in affected) / max_depth, 0.3)
            conf_signal = sum(a["confidence"] for a in affected) / len(affected)
            impact_score = count_signal + depth_signal + 0.3 * conf_signal
        else:
            impact_score = 0.0

        return ImpactResult(
            source_id=entity_id,
            source_name=source_entity.name,
            affected_entities=affected,
            total_affected=len(affected),
            impact_score=round(min(impact_score, 1.0), 4),
        )

    # -----------------------------------------------------------------
    # Context expansion
    # -----------------------------------------------------------------

    def expand_context(
        self,
        entity_id: str,
        depth: int = 2,
        max_neighbors: int = 20,
        min_confidence: float = 0.2,
    ) -> Optional[ContextResult]:
        """
        Expand the neighborhood context of an entity.

        BFS up to specified depth, collecting all reachable entities
        with their relationship information.

        Args:
            entity_id: entity to expand
            depth: traversal depth
            max_neighbors: maximum neighbors to return
            min_confidence: minimum confidence to include

        Returns:
            ContextResult with neighborhood information
        """
        adj = self._build_adjacency()
        entity = self.repository.get_entity(entity_id)

        if not entity:
            return None

        visited: set[str] = {entity_id}
        queue: deque[tuple[str, int]] = deque()
        queue.append((entity_id, 0))

        neighbors: list[dict] = []

        while queue:
            current, current_depth = queue.popleft()

            if current_depth >= depth:
                continue

            for edge in adj.get(current, []):
                next_id = edge["target"]

                if edge["confidence"] < min_confidence:
                    continue

                if next_id not in visited:
                    visited.add(next_id)
                    queue.append((next_id, current_depth + 1))

                    neighbor_entity = self.repository.get_entity(next_id)
                    if neighbor_entity and len(neighbors) < max_neighbors:
                        neighbors.append({
                            "id": next_id,
                            "name": neighbor_entity.name,
                            "type": neighbor_entity.entity_type.value,
                            "relation": edge["relation"],
                            "confidence": edge["confidence"],
                            "distance": current_depth + 1,
                        })

        return ContextResult(
            entity_id=entity_id,
            entity_name=entity.name,
            entity_type=entity.entity_type.value,
            neighborhood=neighbors,
            depth=depth,
            total_neighbors=len(neighbors),
        )

    # -----------------------------------------------------------------
    # Community detection
    # -----------------------------------------------------------------

    def detect_communities(self) -> list[CommunityResult]:
        """
        Detect communities using connected components (BFS).

        Returns a list of communities, each being a set of
        strongly connected entities.
        """
        adj = self._build_adjacency()
        all_entities = self.repository.search_entities()
        visited: set[str] = set()
        communities: list[CommunityResult] = []
        community_id = 0

        for entity in all_entities:
            if entity.id in visited:
                continue

            # BFS to find connected component
            component: list[str] = []
            queue: deque[str] = deque([entity.id])
            visited.add(entity.id)

            while queue:
                current = queue.popleft()
                component.append(current)

                for edge in adj.get(current, []):
                    next_id = edge["target"]
                    if next_id not in visited:
                        visited.add(next_id)
                        queue.append(next_id)

            if len(component) < 2:
                continue

            # Count internal edges
            internal_edges = 0
            for node in component:
                for edge in adj.get(node, []):
                    if edge["target"] in component:
                        internal_edges += 1

            # Cohesion = actual edges / possible edges
            n = len(component)
            possible_edges = n * (n - 1) if n > 1 else 1
            cohesion = internal_edges / possible_edges

            # Get entity details
            entity_names = []
            entity_types = []
            for eid in component:
                e = self.repository.get_entity(eid)
                entity_names.append(e.name if e else eid)
                entity_types.append(e.entity_type.value if e else "unknown")

            communities.append(CommunityResult(
                community_id=community_id,
                entity_ids=component,
                entity_names=entity_names,
                entity_types=entity_types,
                internal_edges=internal_edges,
                cohesion_score=round(cohesion, 4),
            ))
            community_id += 1

        # Sort by size descending
        communities.sort(key=lambda c: len(c.entity_ids), reverse=True)

        return communities

    # -----------------------------------------------------------------
    # Distance computation
    # -----------------------------------------------------------------

    def shortest_distance(
        self, source_id: str, target_id: str, max_depth: int = 10
    ) -> int:
        """
        Compute shortest distance (number of hops) between two entities.

        Returns -1 if no path exists within max_depth.
        """
        path = self.find_path(source_id, target_id, max_depth)
        return path.hops if path else -1

    def get_entity_degree(self, entity_id: str) -> int:
        """Get the degree (number of connections) of an entity."""
        adj = self._build_adjacency()
        return len(adj.get(entity_id, []))

    def get_strongest_connections(
        self, entity_id: str, top_k: int = 5
    ) -> list[dict]:
        """Get the top-k strongest connections of an entity by confidence."""
        adj = self._build_adjacency()
        edges = adj.get(entity_id, [])

        # Sort by confidence descending
        edges.sort(key=lambda e: e["confidence"], reverse=True)

        results = []
        for edge in edges[:top_k]:
            entity = self.repository.get_entity(edge["target"])
            if entity:
                results.append({
                    "id": edge["target"],
                    "name": entity.name,
                    "type": entity.entity_type.value,
                    "relation": edge["relation"],
                    "confidence": edge["confidence"],
                })

        return results
