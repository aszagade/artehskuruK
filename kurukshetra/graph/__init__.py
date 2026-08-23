"""
Graph Module — Knowledge Graph Intelligence
============================================

Public API for the KURUKSHETRA Knowledge Graph.

Core models:
  - Entity, Relationship, EntityType, RelationType (base types)
  - ExtendedEntity, ExtendedRelationship, ExtendedEntityType, ExtendedRelationType
  - Evidence (provenance tracking)

Repository:
  - GraphRepository (DuckDB persistence)

Intelligence:
  - SmartEntityExtractor (entity extraction from text)
  - GraphTraversalEngine (pathfinding, impact analysis, context)
  - GraphRegistry (unified query service)

Connectors:
  - BaseConnector (abstract interface)
  - ConfluenceConnector, DatadogConnector, SQLConnector, TeamsConnector, SEALConnector
"""

from .models import Entity, Relationship, EntityType, RelationType
from .repository import GraphRepository
from .entity_types import (
    Evidence,
    ExtendedEntity,
    ExtendedEntityType,
    ExtendedRelationship,
    ExtendedRelationType,
    ENTITY_TYPE_MAP,
    RELATION_TYPE_MAP,
)
from .extractor import SmartEntityExtractor, ExtractionResult
from .traversal import (
    GraphTraversalEngine,
    PathResult,
    ImpactResult,
    ContextResult,
    CommunityResult,
)
from .registry import GraphRegistry
from .connectors import (
    BaseConnector,
    ConfluenceConnector,
    DatadogConnector,
    SQLConnector,
    TeamsConnector,
    SEALConnector,
    get_connector,
    list_connectors,
)

__all__ = [
    # Base models
    "Entity",
    "Relationship",
    "EntityType",
    "RelationType",
    # Repository
    "GraphRepository",
    # Extended types
    "Evidence",
    "ExtendedEntity",
    "ExtendedEntityType",
    "ExtendedRelationship",
    "ExtendedRelationType",
    "ENTITY_TYPE_MAP",
    "RELATION_TYPE_MAP",
    # Extraction
    "SmartEntityExtractor",
    "ExtractionResult",
    # Traversal
    "GraphTraversalEngine",
    "PathResult",
    "ImpactResult",
    "ContextResult",
    "CommunityResult",
    # Registry
    "GraphRegistry",
    # Connectors
    "BaseConnector",
    "ConfluenceConnector",
    "DatadogConnector",
    "SQLConnector",
    "TeamsConnector",
    "SEALConnector",
    "get_connector",
    "list_connectors",
]
