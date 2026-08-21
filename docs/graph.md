# Graph Module

The **Graph** module provides data structures for representing knowledge graphs within KURUKSHETRA.

## Overview

This module defines the core building blocks for constructing and querying enterprise knowledge graphs:
- **Entities**: Nodes in the graph representing discrete units of knowledge
- **Relationships**: Edges connecting entities with defined semantics
- **Enums**: Type systems for classifying entities and relationships

## Core Components

### EntityType Enum

Classification system for entity types in the knowledge graph.

```python
EntityType.DOCUMENT      # Documents and files
EntityType.PROCESS       # Business processes and workflows  
EntityType.PERSON        # People and roles
EntityType.SYSTEM        # Technical systems and applications
EntityType.METRIC        # Metrics and KPIs
EntityType.CONFIGURATION # Configuration settings
EntityType.INCIDENT       # Incidents and issues
EntityType.KNOWLEDGE_ARTICLE  # Knowledge base articles
```

### RelationType Enum

Classification system for relationship types between entities.

```python
RelationType.RELATED_TO    # General relationship
RelationType.DEPENDS_ON    # Dependency relationship
RelationType.CONTAINS      # Containment hierarchy
RelationType.GENERATES     # Generation/production relationship
RelationType.USES          # Usage relationship
RelationType.MONITORS      # Monitoring relationship
RelationType.CONFIGURES    # Configuration relationship
RelationType.TRIGGERS      # Trigger/activation relationship
RelationType.RESOLVES      # Resolution relationship
```

### Entity Dataclass

Represents a knowledge graph entity (node).

**Fields:**
- `id` (str): Unique identifier for the entity
- `name` (str): Human-readable name or title
- `entity_type` (EntityType): Classification of the entity
- `description` (Optional[str]): Detailed description (default: None)
- `metadata` (Optional[dict]): Additional attributes (default: None)
- `owner` (Optional[str]): Ownership identifier (default: None)
- `visibility` (Optional[str]): Visibility level (default: None)

**Example:**
```python
from kurukshetra.graph import Entity, EntityType

entity = Entity(
    id="doc-123",
    name="G3 Installation Process",
    entity_type=EntityType.DOCUMENT,
    description="Step-by-step guide for G3 system installation",
    metadata={"version": "1.0", "author": "support-team"},
    owner="Service Delivery",
    visibility="Internal"
)
```

### Relationship Dataclass

Represents a relationship between two entities (edge).

**Fields:**
- `source_id` (str): ID of the source entity
- `target_id` (str): ID of the target entity
- `relation_type` (RelationType): Type of relationship
- `description` (Optional[str]): Explanation of the relationship (default: None)
- `confidence` (Optional[float]): Confidence score 0.0-1.0 (default: None)
- `metadata` (Optional[dict]): Additional attributes (default: None)

**Example:**
```python
from kurukshetra.graph import Relationship, RelationType

relationship = Relationship(
    source_id="doc-123",
    target_id="proc-456",
    relation_type=RelationType.DOCUMENTS,
    description="Installation document describes the process",
    confidence=0.95,
    metadata={"created_at": "2024-01-15"}
)
```

## Usage Patterns

### Building a Knowledge Graph

```python
from kurukshetra.graph import Entity, Relationship, EntityType, RelationType

# Create entities
installation_doc = Entity(
    id="doc-install",
    name="G3 Installation Guide",
    entity_type=EntityType.DOCUMENT,
    owner="Support"
)

monitoring_process = Entity(
    id="proc-monitor",
    name="Monitor by Exception",
    entity_type=EntityType.PROCESS,
    owner="Operations"
)

# Create relationships
Relationship(
    source_id="doc-install",
    target_id="proc-monitor",
    relation_type=RelationType.RELATED_TO
)
```

### Graph Querying

The graph structures are designed to work with:
- In-memory traversal algorithms
- Persistent graph databases (Neo4j, ArangoDB)
- Vector search over entity metadata
- RAG pipelines for knowledge retrieval

## Best Practices

1. **Entity Identification**: Use stable, unique IDs that persist across sessions
2. **Type Consistency**: Apply EntityType and RelationType consistently throughout the organization
3. **Metadata Standards**: Define common metadata fields at the organizational level
4. **Ownership Tracking**: Always specify entity ownership for governance purposes
5. **Visibility Levels**: Use visibility levels to control access to sensitive information

## Integration with SEAL

Graph entities can be registered in SEAL for:
- Adaptive learning over relationships
- Pattern discovery across connected entities
- Contextual retrieval based on graph structure

```python
# Example: Registering a graph in SEAL
from seal.registry import register_knowledge_graph

entities = [installation_doc, monitoring_process]
relationships = [relationship]
register_knowledge_graph("enterprise-processes", entities, relationships)
```

## API Reference

- [`Entity`](kurukshetra/graph/models.py:45)
- [`Relationship`](kurukshetra/graph/models.py:68)
- [`EntityType`](kurukshetra/graph/models.py:12)
- [`RelationType`](kurukshetra/graph/models.py:27)
