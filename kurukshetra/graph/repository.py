"""
Graph Repository
================

DuckDB persistence layer for the KURUKSHETRA Knowledge Graph.
"""

from __future__ import annotations

import json
from typing import List, Optional

import duckdb

from .models import Entity, Relationship, EntityType, RelationType


class GraphRepository:
    """Stores graph entities and relationships inside DuckDB."""

    def __init__(self, db_path: str = "kurukshetra_registry.duckdb") -> None:
        self.db_path = db_path
        self._connection: Optional[duckdb.DuckDBPyConnection] = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def get_connection(self) -> duckdb.DuckDBPyConnection:
        if self._connection is None:
            self._connection = duckdb.connect(self.db_path)
        return self._connection

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def create_tables(self) -> None:
        conn = self.get_connection()

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS graph_entities (
                id VARCHAR PRIMARY KEY,
                name VARCHAR,
                entity_type VARCHAR,
                description VARCHAR,
                metadata JSON,
                owner VARCHAR,
                visibility VARCHAR
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS graph_relationships (
                source_id VARCHAR,
                target_id VARCHAR,
                relation_type VARCHAR,
                description VARCHAR,
                confidence DOUBLE,
                metadata JSON,
                PRIMARY KEY (source_id, target_id, relation_type)
            )
            """
        )

    # ------------------------------------------------------------------
    # Entity Operations
    # ------------------------------------------------------------------

    def upsert_entity(self, entity: Entity) -> None:
        conn = self.get_connection()

        conn.execute(
            """
            INSERT INTO graph_entities
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                entity_type = excluded.entity_type,
                description = excluded.description,
                metadata = excluded.metadata,
                owner = excluded.owner,
                visibility = excluded.visibility
            """,
            [
                entity.id,
                entity.name,
                entity.entity_type.value,
                entity.description,
                json.dumps(entity.metadata),
                entity.owner,
                entity.visibility,
            ],
        )

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        conn = self.get_connection()

        row = conn.execute(
            """
            SELECT id,
                   name,
                   entity_type,
                   description,
                   metadata,
                   owner,
                   visibility
            FROM graph_entities
            WHERE id = ?
            """,
            [entity_id],
        ).fetchone()

        if row is None:
            return None

        try:
            etype = EntityType(row[2])
        except (ValueError, KeyError):
            etype = EntityType.DOCUMENT  # fallback for extended types

        return Entity(
            id=row[0],
            name=row[1],
            entity_type=etype,
            description=row[3],
            metadata=json.loads(row[4]) if row[4] else {},
            owner=row[5],
            visibility=row[6],
        )

    def search_entities(
        self,
        entity_type: Optional[EntityType] = None,
    ) -> List[Entity]:
        conn = self.get_connection()

        if entity_type:
            rows = conn.execute(
                """
                SELECT *
                FROM graph_entities
                WHERE entity_type = ?
                """,
                [entity_type.value],
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM graph_entities"
            ).fetchall()


        entities: List[Entity] = []

        for row in rows:
            try:
                etype = EntityType(row[2])
            except (ValueError, KeyError):
                etype = EntityType.DOCUMENT  # fallback for extended types

            entities.append(
                Entity(
                    id=row[0],
                    name=row[1],
                    entity_type=etype,
                    description=row[3],
                    metadata=json.loads(row[4]) if row[4] else {},
                    owner=row[5],
                    visibility=row[6],
                )
            )

        return entities

    # ------------------------------------------------------------------
    # Relationship Operations
    # ------------------------------------------------------------------

    def upsert_relationship(self, relationship: Relationship) -> None:
        conn = self.get_connection()

        conn.execute(
            """
            INSERT INTO graph_relationships
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, target_id, relation_type)
            DO UPDATE SET
                description = excluded.description,
                confidence = excluded.confidence,
                metadata = excluded.metadata
            """,
            [
                relationship.source_id,
                relationship.target_id,
                relationship.relation_type.value,
                relationship.description,
                relationship.confidence,
                json.dumps(relationship.metadata),
            ],
        )

    def get_neighbors(self, entity_id: str) -> List[Relationship]:
        conn = self.get_connection()

        rows = conn.execute(
            """
            SELECT source_id,
                   target_id,
                   relation_type,
                   description,
                   confidence,
                   metadata
            FROM graph_relationships
            WHERE source_id = ? OR target_id = ?
            """,
            [entity_id, entity_id],
        ).fetchall()

        relationships: List[Relationship] = []

        for row in rows:
            relationships.append(
                Relationship(
                    source_id=row[0],
                    target_id=row[1],
                    relation_type=RelationType(row[2]),
                    description=row[3],
                    confidence=row[4],
                    metadata=json.loads(row[5]) if row[5] else {},
                )
            )

        return relationships

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None