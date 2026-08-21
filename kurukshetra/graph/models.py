"""
Graph entity models for KURUKSHETRA.

This module defines the core data structures for representing knowledge graph entities,
relationships, and their types within the enterprise AI command center.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class EntityType(Enum):
    """
    Enumeration of entity types in the knowledge graph.
    
    Represents the categorical classification of entities for organizational and retrieval purposes.
    """
    DOCUMENT = "document"
    PROCESS = "process"
    PERSON = "person"
    SYSTEM = "system"
    METRIC = "metric"
    CONFIGURATION = "configuration"
    INCIDENT = "incident"
    KNOWLEDGE_ARTICLE = "knowledge_article"


class RelationType(Enum):
    """
    Enumeration of relationship types in the knowledge graph.
    
    Defines how entities are connected and interact within the enterprise knowledge fabric.
    """
    RELATED_TO = "related_to"
    DEPENDS_ON = "depends_on"
    CONTAINS = "contains"
    GENERATES = "generates"
    USES = "uses"
    MONITORS = "monitors"
    CONFIGURES = "configures"
    TRIGGERS = "triggers"
    RESOLVES = "resolves"


@dataclass
class Entity:
    """
    Represents a knowledge graph entity.
    
    An entity is a discrete unit of knowledge with a unique identifier, type,
    and associated metadata. Entities form the nodes in the knowledge graph.
    
    Attributes:
        id: Unique identifier for the entity
        name: Human-readable name or title
        entity_type: Classification of the entity (from EntityType enum)
        description: Optional detailed description
        metadata: Optional dictionary of additional attributes
        owner: Optional ownership identifier
        visibility: Optional visibility level
    """
    id: str
    name: str
    entity_type: EntityType
    description: Optional[str] = None
    metadata: Optional[dict] = None
    owner: Optional[str] = None
    visibility: Optional[str] = None


@dataclass
class Relationship:
    """
    Represents a relationship between two entities in the knowledge graph.
    
    A relationship defines how two entities are connected, including the direction,
type of connection, and optional confidence score. Relationships form the edges
in the knowledge graph.
    
    Attributes:
        source_id: ID of the source entity
        target_id: ID of the target entity
        relation_type: Type of relationship (from RelationType enum)
        description: Optional explanation of the relationship
        confidence: Optional confidence score (0.0 to 1.0)
        metadata: Optional dictionary of additional attributes
    """
    source_id: str
    target_id: str
    relation_type: RelationType
    description: Optional[str] = None
    confidence: Optional[float] = None
    metadata: Optional[dict] = None