"""
Graph Registry
==============

Unified query service for the Knowledge Graph.

Combines:
  - Entity extraction (from SmartEntityExtractor)
  - Entity resolution (deduplication, canonical form)
  - Graph traversal (pathfinding, impact, context)
  - Graph querying (search, filter, aggregate)
  - DuckDB persistence (extended schema)

This is the single entry point for all graph intelligence operations.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

import duckdb

from .models import Entity, Relationship, EntityType, RelationType
from .repository import GraphRepository
from .entity_types import (
    Evidence,
    ExtendedEntity,
    ExtendedEntityType,
    ExtendedRelationship,
    ExtendedRelationType,
)
from .extractor import SmartEntityExtractor, ExtractionResult
from .traversal import (
    GraphTraversalEngine,
    PathResult,
    ImpactResult,
    ContextResult,
    CommunityResult,
)


# =====================================================================
# Query types
# =====================================================================

@dataclass(slots=True)
class GraphQueryResult:
    """Result of a graph query."""
    query: str
    entities: list[dict]
    relationships: list[dict]
    total_entities: int
    total_relationships: int


@dataclass(slots=True)
class GraphStats:
    """Statistics about the knowledge graph."""
    total_entities: int
    total_relationships: int
    entities_by_type: dict[str, int]
    relationships_by_type: dict[str, int]
    avg_confidence: float
    teams_represented: list[str]


# =====================================================================
# Graph Registry
# =====================================================================

class GraphRegistry:
    """
    Unified service for all Knowledge Graph operations.

    Provides:
    1. Document ingestion → entity extraction → graph population
    2. Entity search and resolution
    3. Graph traversal and reasoning
    4. Query interface for SANJAYA and agents
    5. Statistics and health monitoring

    This is the primary interface for interacting with the Knowledge Graph.
    """

    def __init__(self, db_path: str = "kurukshetra_registry.duckdb") -> None:
        self.repository = GraphRepository(db_path)
        self.repository.create_tables()
        self.extractor = SmartEntityExtractor()
        self.traversal = GraphTraversalEngine(self.repository)
        self._ensure_extended_schema()

    def _ensure_extended_schema(self) -> None:
        """Create extended tables for evidence and entity metadata."""
        conn = self.repository.get_connection()

        # Evidence table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS graph_evidence (
                evidence_id VARCHAR PRIMARY KEY,
                entity_id VARCHAR,
                source_document VARCHAR,
                source_chunk VARCHAR,
                source_text VARCHAR,
                confidence DOUBLE,
                human_confirmed BOOLEAN DEFAULT FALSE,
                created_at VARCHAR,
                updated_at VARCHAR
            )
        """)

        # Extended entity metadata
        conn.execute("""
            CREATE TABLE IF NOT EXISTS graph_entity_meta (
                entity_id VARCHAR PRIMARY KEY,
                team_id VARCHAR,
                product_scope JSON,
                visibility VARCHAR,
                average_confidence DOUBLE,
                first_seen VARCHAR,
                last_verified VARCHAR,
                verification_count INTEGER DEFAULT 0
            )
        """)

        # Entity resolution table (maps aliases to canonical IDs)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS entity_resolutions (
                alias VARCHAR,
                canonical_id VARCHAR,
                resolution_confidence DOUBLE,
                PRIMARY KEY (alias, canonical_id)
            )
        """)

    # -----------------------------------------------------------------
    # Document ingestion into graph
    # -----------------------------------------------------------------

    def ingest_document(
        self,
        text: str,
        document_id: str,
        document_title: str = "",
        team_id: Optional[str] = None,
        product_scope: Optional[list[str]] = None,
    ) -> ExtractionResult:
        """
        Ingest a document into the Knowledge Graph.

        Extracts entities, builds relationships with evidence,
        and persists everything to DuckDB.

        Args:
            text: full document text
            document_id: unique identifier
            document_title: human-readable title
            team_id: owning team (from OrgMap)
            product_scope: related products

        Returns:
            ExtractionResult with all extracted entities and relationships
        """
        # 1. Extract entities and relationships
        result = self.extractor.extract_from_document(
            text=text,
            document_id=document_id,
            document_title=document_title,
            team_id=team_id,
            product_scope=product_scope,
        )

        # 2. Persist entities
        for entity in result.entities:
            self._upsert_extended_entity(entity)

        # 3. Persist relationships
        for rel in result.relationships:
            self._upsert_extended_relationship(rel)

        # 4. Persist evidence
        for entity in result.entities:
            for ev in entity.evidence:
                self._persist_evidence(entity.id, ev)

        # 5. Invalidate traversal cache
        self.traversal.invalidate_cache()

        return result

    def _upsert_extended_entity(self, entity: ExtendedEntity) -> None:
        """Persist an ExtendedEntity to both entity tables."""
        # Base entity
        conn = self.repository.get_connection()
        conn.execute("""
            INSERT INTO graph_entities (id, name, entity_type, description, metadata, owner, visibility)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                entity_type = excluded.entity_type,
                description = excluded.description,
                metadata = excluded.metadata,
                owner = excluded.owner,
                visibility = excluded.visibility
        """, [
            entity.id,
            entity.name,
            entity.entity_type.value,
            entity.description,
            json.dumps(entity.metadata),
            entity.team_id,
            entity.visibility,
        ])

        # Extended metadata
        conn.execute("""
            INSERT INTO graph_entity_meta
            (entity_id, team_id, product_scope, visibility, average_confidence,
             first_seen, last_verified, verification_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entity_id) DO UPDATE SET
                team_id = COALESCE(excluded.team_id, graph_entity_meta.team_id),
                product_scope = COALESCE(excluded.product_scope, graph_entity_meta.product_scope),
                visibility = excluded.visibility,
                average_confidence = excluded.average_confidence,
                last_verified = COALESCE(excluded.last_verified, graph_entity_meta.last_verified),
                verification_count = excluded.verification_count
        """, [
            entity.id,
            entity.team_id,
            json.dumps(entity.product_scope),
            entity.visibility,
            entity.average_confidence,
            entity.first_seen,
            entity.last_verified,
            entity.verification_count,
        ])

    def _upsert_extended_relationship(self, rel: ExtendedRelationship) -> None:
        """Persist an ExtendedRelationship."""
        conn = self.repository.get_connection()
        conn.execute("""
            INSERT INTO graph_relationships
            (source_id, target_id, relation_type, description, confidence, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, target_id, relation_type)
            DO UPDATE SET
                description = excluded.description,
                confidence = GREATEST(excluded.confidence, graph_relationships.confidence),
                metadata = excluded.metadata
        """, [
            rel.source_id,
            rel.target_id,
            rel.relation_type.value,
            rel.description,
            rel.confidence,
            json.dumps(rel.metadata),
        ])

    def _persist_evidence(self, entity_id: str, evidence: Evidence) -> None:
        """Persist an evidence record."""
        conn = self.repository.get_connection()
        evidence_id = f"EVD-{entity_id}-{len(evidence.source_document)}-{hash(evidence.source_text or '')}"
        conn.execute("""
            INSERT INTO graph_evidence
            (evidence_id, entity_id, source_document, source_chunk, source_text,
             confidence, human_confirmed, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(evidence_id) DO UPDATE SET
                confidence = excluded.confidence,
                human_confirmed = excluded.human_confirmed,
                updated_at = excluded.updated_at
        """, [
            evidence_id,
            entity_id,
            evidence.source_document,
            evidence.source_chunk,
            evidence.source_text,
            evidence.confidence,
            evidence.human_confirmed,
            evidence.created_at,
            evidence.updated_at,
        ])

    # -----------------------------------------------------------------
    # Entity search and resolution
    # -----------------------------------------------------------------

    def search_entities(
        self,
        query: str = "",
        entity_type: Optional[str] = None,
        team_id: Optional[str] = None,
        min_confidence: float = 0.0,
        limit: int = 50,
    ) -> list[dict]:
        """
        Search entities with optional filters.

        Args:
            query: text to search (matches name/description)
            entity_type: filter by entity type
            team_id: filter by owning team
            min_confidence: minimum average confidence
            limit: max results

        Returns:
            List of entity dictionaries
        """
        conn = self.repository.get_connection()

        conditions = []
        params: list = []

        if entity_type:
            conditions.append("ge.entity_type = ?")
            params.append(entity_type)

        if team_id:
            conditions.append("gem.team_id = ?")
            params.append(team_id)

        if min_confidence > 0:
            conditions.append("gem.average_confidence >= ?")
            params.append(min_confidence)

        if query:
            conditions.append("(ge.name ILIKE ? OR ge.description ILIKE ?)")
            params.extend([f"%{query}%", f"%{query}%"])

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        rows = conn.execute(f"""
            SELECT ge.id, ge.name, ge.entity_type, ge.description,
                   ge.owner, ge.visibility,
                   gem.team_id, gem.average_confidence, gem.first_seen,
                   gem.verification_count
            FROM graph_entities ge
            LEFT JOIN graph_entity_meta gem ON ge.id = gem.entity_id
            WHERE {where_clause}
            ORDER BY gem.average_confidence DESC NULLS LAST
            LIMIT ?
        """, params + [limit]).fetchall()

        return [
            {
                "id": r[0],
                "name": r[1],
                "type": r[2],
                "description": r[3],
                "owner": r[4],
                "visibility": r[5],
                "team_id": r[6],
                "confidence": r[7] or 0.0,
                "first_seen": r[8],
                "verification_count": r[9] or 0,
            }
            for r in rows
        ]

    def resolve_entity(self, entity_name: str) -> Optional[dict]:
        """
        Resolve an entity name to its canonical form.

        Searches by name (case-insensitive) and returns the best match.
        """
        results = self.search_entities(query=entity_name, limit=5)

        if not results:
            return None

        # Exact match first
        for r in results:
            if r["name"].lower() == entity_name.lower():
                return r

        # Otherwise return highest confidence match
        return results[0]

    def get_entity_context(self, entity_id: str, depth: int = 2) -> Optional[dict]:
        """
        Get full context for an entity: metadata + neighborhood.

        Returns entity details + traversal context at specified depth.
        """
        entity = self.repository.get_entity(entity_id)
        if not entity:
            return None

        # Get traversal context
        context = self.traversal.expand_context(entity_id, depth=depth)

        # Get entity metadata
        conn = self.repository.get_connection()
        meta_row = conn.execute("""
            SELECT team_id, product_scope, average_confidence, first_seen, verification_count
            FROM graph_entity_meta WHERE entity_id = ?
        """, [entity_id]).fetchone()

        # Get evidence
        evidence_rows = conn.execute("""
            SELECT source_document, source_text, confidence, human_confirmed
            FROM graph_evidence WHERE entity_id = ?
            ORDER BY confidence DESC
        """, [entity_id]).fetchall()

        result = {
            "entity": {
                "id": entity.id,
                "name": entity.name,
                "type": entity.entity_type.value,
                "description": entity.description,
                "owner": entity.owner,
                "visibility": entity.visibility,
            },
            "metadata": {},
            "neighborhood": [],
            "evidence": [],
        }

        if meta_row:
            result["metadata"] = {
                "team_id": meta_row[0],
                "product_scope": json.loads(meta_row[1]) if meta_row[1] else [],
                "confidence": meta_row[2] or 0.0,
                "first_seen": meta_row[3],
                "verification_count": meta_row[4] or 0,
            }

        if context:
            result["neighborhood"] = context.neighborhood

        for ev in evidence_rows:
            result["evidence"].append({
                "source_document": ev[0],
                "source_text": ev[1],
                "confidence": ev[2],
                "human_confirmed": ev[3],
            })

        return result

    # -----------------------------------------------------------------
    # Graph traversal delegates
    # -----------------------------------------------------------------

    def find_path(self, source_id: str, target_id: str) -> Optional[dict]:
        """Find shortest path between two entities."""
        path = self.traversal.find_path(source_id, target_id)
        if not path:
            return None
        return {
            "path": path.path,
            "path_names": path.path_names,
            "path_types": path.path_types,
            "path_relations": path.path_relations,
            "total_confidence": path.total_confidence,
            "hops": path.hops,
        }

    def analyze_impact(self, entity_id: str, max_depth: int = 3) -> dict:
        """Analyze impact of an entity change."""
        result = self.traversal.analyze_impact(entity_id, max_depth)
        return {
            "source_id": result.source_id,
            "source_name": result.source_name,
            "affected_entities": result.affected_entities,
            "total_affected": result.total_affected,
            "impact_score": result.impact_score,
        }

    def get_communities(self) -> list[dict]:
        """Detect communities in the graph."""
        communities = self.traversal.detect_communities()
        return [
            {
                "community_id": c.community_id,
                "entity_ids": c.entity_ids,
                "entity_names": c.entity_names,
                "entity_types": c.entity_types,
                "internal_edges": c.internal_edges,
                "cohesion_score": c.cohesion_score,
            }
            for c in communities
        ]

    # -----------------------------------------------------------------
    # Statistics
    # -----------------------------------------------------------------

    def get_stats(self) -> dict:
        """Get comprehensive graph statistics."""
        conn = self.repository.get_connection()

        # Entity counts by type
        entity_rows = conn.execute("""
            SELECT entity_type, COUNT(*) FROM graph_entities GROUP BY entity_type
        """).fetchall()
        entities_by_type = {r[0]: r[1] for r in entity_rows}
        total_entities = sum(entities_by_type.values())

        # Relationship counts by type
        rel_rows = conn.execute("""
            SELECT relation_type, COUNT(*) FROM graph_relationships GROUP BY relation_type
        """).fetchall()
        relationships_by_type = {r[0]: r[1] for r in rel_rows}
        total_relationships = sum(relationships_by_type.values())

        # Average confidence
        conf_row = conn.execute("""
            SELECT AVG(confidence) FROM graph_relationships WHERE confidence IS NOT NULL
        """).fetchone()
        avg_confidence = conf_row[0] if conf_row and conf_row[0] else 0.0

        # Teams represented
        team_rows = conn.execute("""
            SELECT DISTINCT team_id FROM graph_entity_meta
            WHERE team_id IS NOT NULL
        """).fetchall()
        teams_represented = [r[0] for r in team_rows]

        return {
            "total_entities": total_entities,
            "total_relationships": total_relationships,
            "entities_by_type": entities_by_type,
            "relationships_by_type": relationships_by_type,
            "avg_confidence": round(avg_confidence, 4),
            "teams_represented": teams_represented,
        }

    def get_team_graph(self, team_id: str) -> dict:
        """
        Get the subgraph for a specific team.

        Returns all entities owned by the team and their relationships.
        """
        conn = self.repository.get_connection()

        # Get team entities
        entity_rows = conn.execute("""
            SELECT ge.id, ge.name, ge.entity_type, ge.description
            FROM graph_entities ge
            JOIN graph_entity_meta gem ON ge.id = gem.entity_id
            WHERE gem.team_id = ?
        """, [team_id]).fetchall()

        entity_ids = [r[0] for r in entity_rows]
        entities = [
            {"id": r[0], "name": r[1], "type": r[2], "description": r[3]}
            for r in entity_rows
        ]

        # Get relationships between team entities
        relationships = []
        for eid in entity_ids:
            rel_rows = conn.execute("""
                SELECT source_id, target_id, relation_type, confidence
                FROM graph_relationships
                WHERE source_id = ? OR target_id = ?
            """, [eid, eid]).fetchall()

            for r in rel_rows:
                if r[0] in entity_ids or r[1] in entity_ids:
                    relationships.append({
                        "source": r[0],
                        "target": r[1],
                        "relation": r[2],
                        "confidence": r[3],
                    })

        return {
            "team_id": team_id,
            "entities": entities,
            "relationships": relationships,
            "entity_count": len(entities),
            "relationship_count": len(relationships),
        }

    # -----------------------------------------------------------------
    # Human confirmation (for SEAL learning)
    # -----------------------------------------------------------------

    def confirm_entity(self, entity_id: str) -> None:
        """Mark an entity as human-confirmed."""
        conn = self.repository.get_connection()
        conn.execute("""
            UPDATE graph_entity_meta
            SET verification_count = verification_count + 1,
                last_verified = CURRENT_TIMESTAMP
            WHERE entity_id = ?
        """, [entity_id])

    def confirm_relationship(
        self, source_id: str, target_id: str, relation_type: str
    ) -> None:
        """Mark a relationship as human-confirmed."""
        conn = self.repository.get_connection()
        conn.execute("""
            UPDATE graph_relationships
            SET confidence = MIN(confidence + 0.1, 1.0)
            WHERE source_id = ? AND target_id = ? AND relation_type = ?
        """, [source_id, target_id, relation_type])

    # -----------------------------------------------------------------
    # Cleanup
    # -----------------------------------------------------------------

    def close(self) -> None:
        """Close the database connection."""
        self.repository.close()
