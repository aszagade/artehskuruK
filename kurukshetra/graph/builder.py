"""
Auto Graph Construction
=======================

Automatically extracts entities and relationships from ingested documents
to build a knowledge graph without manual intervention.

Entity types: Document, Process, System, Error, Person, Configuration
Relationship types: uses, generates, resolves, depends_on, configures
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .models import Entity, Relationship, EntityType, RelationType
from .repository import GraphRepository


# ---------------------------------------------------------------------------
# Entity extraction patterns
# ---------------------------------------------------------------------------

SYSTEM_PATTERNS = [
    re.compile(r"\b(G3\s*RMS|Opera\s*Cloud|NGI|OXI|OHIP|FOLS|TARS|CP\s*Pricing)\b", re.IGNORECASE),
    re.compile(r"\b(Datadog|Smartsheet|SFDC|Salesforce|JIRA|SynXis|Curtis)\b", re.IGNORECASE),
    re.compile(r"\b(RabbitMQ|Kafka|SAS|SQL\s*Server|Docker|Kubernetes)\b", re.IGNORECASE),
]

ERROR_PATTERNS = [
    re.compile(r"\b(\w+Step)\s+(?:failure|failed|error)", re.IGNORECASE),
    re.compile(r"(?:error|exception|failure)[\s:]+([A-Z][\w\s]{5,50})", re.IGNORECASE),
]

PROCESS_PATTERNS = [
    re.compile(r"(?:process|procedure|workflow|steps?)\s+(?:to\s+)?(\w[\w\s]{5,40})", re.IGNORECASE),
    re.compile(r"(?:installation|migration|configuration|monitoring)\s+(?:of\s+)?(\w[\w\s]{5,40})", re.IGNORECASE),
]

CONFIGURATION_PATTERNS = [
    re.compile(r"(?:parameter|setting|config(?:uration)?)\s*[:=]\s*(\w+)", re.IGNORECASE),
    re.compile(r"(?:enable|disable|activate|deactivate)\s+(\w+)", re.IGNORECASE),
]


@dataclass(slots=True)
class ExtractionResult:
    """Result of entity/relationship extraction from a document."""
    document_id: str
    entities_found: list[Entity]
    relationships_found: list[Relationship]
    extraction_confidence: float


class GraphBuilder:
    """
    Automatically constructs knowledge graph from document content.

    Extracts entities and relationships using pattern matching,
    then stores them in the graph repository.
    """

    def __init__(self, repository: Optional[GraphRepository] = None) -> None:
        self.repository = repository or GraphRepository()
        self.repository.create_tables()

    def build_from_text(
        self,
        text: str,
        document_id: str,
        document_title: str = "",
    ) -> ExtractionResult:
        """
        Extract entities and relationships from document text.

        Args:
            text: Full document text
            document_id: Unique document identifier
            document_title: Document title for context

        Returns:
            ExtractionResult with found entities and relationships
        """
        entities: list[Entity] = []
        relationships: list[Relationship] = []

        # 1. Create document entity
        doc_entity = Entity(
            id=document_id,
            name=document_title or document_id,
            entity_type=EntityType.DOCUMENT,
            description=f"Document: {document_title}",
        )
        entities.append(doc_entity)

        # 2. Extract system entities
        system_entities = self._extract_systems(text, document_id)
        entities.extend(system_entities)

        # 3. Extract error entities
        error_entities, error_rels = self._extract_errors(text, document_id)
        entities.extend(error_entities)
        relationships.extend(error_rels)

        # 4. Extract process entities
        process_entities, process_rels = self._extract_processes(text, document_id)
        entities.extend(process_entities)
        relationships.extend(process_rels)

        # 5. Extract configuration entities
        config_entities, config_rels = self._extract_configurations(text, document_id)
        entities.extend(config_entities)
        relationships.extend(config_rels)

        # 6. Create relationships between document and all extracted entities
        for entity in entities:
            if entity.id != document_id:
                relationships.append(
                    Relationship(
                        source_id=document_id,
                        target_id=entity.id,
                        relation_type=RelationType.RELATED_TO,
                        description=f"Document references {entity.name}",
                        confidence=0.8,
                    )
                )

        # 7. Store in repository
        for entity in entities:
            self.repository.upsert_entity(entity)
        for rel in relationships:
            self.repository.upsert_relationship(rel)

        # Calculate extraction confidence
        confidence = min(0.5 + len(entities) * 0.05 + len(relationships) * 0.03, 1.0)

        return ExtractionResult(
            document_id=document_id,
            entities_found=entities,
            relationships_found=relationships,
            extraction_confidence=round(confidence, 3),
        )

    def _extract_systems(
        self, text: str, document_id: str
    ) -> list[Entity]:
        """Extract system entities from text."""
        found_systems: dict[str, Entity] = {}

        for pattern in SYSTEM_PATTERNS:
            for match in pattern.finditer(text):
                system_name = match.group(1).strip()
                system_id = f"SYS-{system_name.upper().replace(' ', '-')}"

                if system_id not in found_systems:
                    found_systems[system_id] = Entity(
                        id=system_id,
                        name=system_name,
                        entity_type=EntityType.SYSTEM,
                        description=f"System: {system_name}",
                    )

        return list(found_systems.values())

    def _extract_errors(
        self, text: str, document_id: str
    ) -> tuple[list[Entity], list[Relationship]]:
        """Extract error entities and their resolution relationships."""
        entities: list[Entity] = []
        relationships: list[Relationship] = []

        for pattern in ERROR_PATTERNS:
            for match in pattern.finditer(text):
                error_name = match.group(1).strip()
                if len(error_name) < 5:
                    continue

                error_id = f"ERR-{error_name.upper().replace(' ', '-')[:50]}"

                entities.append(
                    Entity(
                        id=error_id,
                        name=error_name,
                        entity_type=EntityType.INCIDENT,
                        description=f"Error: {error_name}",
                    )
                )

                # Link error to document as resolution source
                relationships.append(
                    Relationship(
                        source_id=error_id,
                        target_id=document_id,
                        relation_type=RelationType.RESOLVES,
                        description=f"Document resolves {error_name}",
                        confidence=0.7,
                    )
                )

        return entities, relationships

    def _extract_processes(
        self, text: str, document_id: str
    ) -> tuple[list[Entity], list[Relationship]]:
        """Extract process entities."""
        entities: list[Entity] = []
        relationships: list[Relationship] = []

        for pattern in PROCESS_PATTERNS:
            for match in pattern.finditer(text):
                process_name = match.group(1).strip()
                if len(process_name) < 5:
                    continue

                process_id = f"PROC-{process_name.upper().replace(' ', '-')[:50]}"

                entities.append(
                    Entity(
                        id=process_id,
                        name=process_name,
                        entity_type=EntityType.PROCESS,
                        description=f"Process: {process_name}",
                    )
                )

        return entities, relationships

    def _extract_configurations(
        self, text: str, document_id: str
    ) -> tuple[list[Entity], list[Relationship]]:
        """Extract configuration entities."""
        entities: list[Entity] = []
        relationships: list[Relationship] = []

        for pattern in CONFIGURATION_PATTERNS:
            for match in pattern.finditer(text):
                config_name = match.group(1).strip()
                if len(config_name) < 3:
                    continue

                config_id = f"CFG-{config_name.upper().replace(' ', '-')[:50]}"

                entities.append(
                    Entity(
                        id=config_id,
                        name=config_name,
                        entity_type=EntityType.CONFIGURATION,
                        description=f"Configuration: {config_name}",
                    )
                )

        return entities, relationships

    def build_from_document_store(self, limit: int = 50) -> list[ExtractionResult]:
        """
        Build graph from all registered documents in the store.

        Args:
            limit: Maximum number of documents to process

        Returns:
            List of ExtractionResults
        """
        from kurukshetra.registry.chunks import ChunkRepository

        chunk_repo = ChunkRepository()
        chunks = chunk_repo.load()

        # Group chunks by document
        doc_chunks: dict[str, list] = {}
        for chunk in chunks:
            doc_chunks.setdefault(chunk.document_id, []).append(chunk)

        results: list[ExtractionResult] = []

        for doc_id, doc_chunk_list in list(doc_chunks.items())[:limit]:
            # Combine all chunks from this document
            full_text = "\n\n".join(c.text for c in doc_chunk_list)

            result = self.build_from_text(
                text=full_text,
                document_id=doc_id,
                document_title=doc_id,
            )
            results.append(result)

        return results

    def get_entity_context(
        self, entity_id: str, depth: int = 2
    ) -> dict:
        """
        Get contextual information about an entity by traversing the graph.

        Returns entity details + related entities up to specified depth.
        """
        entity = self.repository.get_entity(entity_id)
        if entity is None:
            return {"error": f"Entity {entity_id} not found"}

        neighbors = self.repository.get_neighbors(entity_id)

        related_entities = []
        for rel in neighbors:
            # Get the other end of the relationship
            other_id = (
                rel.target_id if rel.source_id == entity_id else rel.source_id
            )
            other_entity = self.repository.get_entity(other_id)
            if other_entity:
                related_entities.append({
                    "entity": {
                        "id": other_entity.id,
                        "name": other_entity.name,
                        "type": other_entity.entity_type.value,
                    },
                    "relationship": {
                        "type": rel.relation_type.value,
                        "description": rel.description,
                        "confidence": rel.confidence,
                    },
                })

        return {
            "entity": {
                "id": entity.id,
                "name": entity.name,
                "type": entity.entity_type.value,
                "description": entity.description,
                "owner": entity.owner,
                "visibility": entity.visibility,
            },
            "related_entities": related_entities,
            "total_relationships": len(neighbors),
        }
