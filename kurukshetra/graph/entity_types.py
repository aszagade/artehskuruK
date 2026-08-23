"""
Extended Entity & Relationship Types
=====================================

The complete type taxonomy for KURUKSHETRA's Knowledge Graph.

Entity Types:
  DOCUMENT  ? ingested knowledge artifact
  TEAM      ? organizational unit (SPM, ICS, SDOPS, etc.)
  PERSON    ? individual within the organization
  CLIENT    ? hotel/property client using IDeaS products
  PROPERTY  ? hotel property (physical location)
  SYSTEM    ? software system (G3 RMS, Opera, OXI, OHIP, etc.)
  PROCESS   ? operational procedure or workflow
  JOB       ? scheduled or ad-hoc operational task
  INCIDENT  ? error, failure, or production issue
  CONFIGURATION ? parameter, setting, or config value
  METRIC    ? measurement or KPI
  KNOWLEDGE_ARTICLE ? reference or knowledge base entry

Relationship Types:
  OWNED_BY     ? document/team/person owned by team/org
  BELONGS_TO   ? entity belongs to a team/group
  USES         ? entity uses another entity
  DEPENDS_ON   ? entity depends on another entity
  TRIGGERS     ? entity triggers another entity
  REFERENCES   ? entity references another entity
  RESOLVES     ? entity resolves an incident/error
  GENERATED_FROM ? entity derived from another entity
  MONITORS     ? entity monitors another entity
  CONFIGURES   ? entity configures another entity
  CONTAINS     ? entity contains another entity
  GENERATES    ? entity generates another entity

Every relationship carries Evidence for provenance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from .models import EntityType, RelationType  # re-export the originals


# =====================================================================
# Extended Entity Types (superset)
# =====================================================================

class ExtendedEntityType(Enum):
    """Complete entity type taxonomy for Graph Intelligence."""
    DOCUMENT          = "document"
    TEAM              = "team"
    PERSON            = "person"
    CLIENT            = "client"
    PROPERTY          = "property"
    SYSTEM            = "system"
    PROCESS           = "process"
    JOB               = "job"
    INCIDENT          = "incident"
    CONFIGURATION     = "configuration"
    METRIC            = "metric"
    KNOWLEDGE_ARTICLE = "knowledge_article"


class ExtendedRelationType(Enum):
    """Complete relationship type taxonomy for Graph Intelligence."""
    OWNED_BY       = "owned_by"
    BELONGS_TO     = "belongs_to"
    USES           = "uses"
    DEPENDS_ON     = "depends_on"
    TRIGGERS       = "triggers"
    REFERENCES     = "references"
    RESOLVES       = "resolves"
    GENERATED_FROM = "generated_from"
    MONITORS       = "monitors"
    CONFIGURES     = "configures"
    CONTAINS       = "contains"
    GENERATES      = "generate"


# =====================================================================
# Evidence ? provenance for every relationship
# =====================================================================

@dataclass
class Evidence:
    """
    Provenance record for a graph relationship.

    Every edge in the graph MUST carry evidence. This is the single
    source of truth for "why does this relationship exist?"

    Attributes:
        source_document: document_id that provided this evidence
        source_chunk: optional chunk_id within the document
        source_text: the exact text fragment that justifies the relationship
        confidence: machine-assessed confidence (0.0?1.0)
        human_confirmed: whether a human has validated this relationship
        created_at: when this evidence was first recorded
        updated_at: when this evidence was last modified
    """
    source_document: str
    source_chunk: Optional[str] = None
    source_text: Optional[str] = None
    confidence: float = 0.5
    human_confirmed: bool = False
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


# =====================================================================
# Extended Entity (carries org metadata)
# =====================================================================

@dataclass
class ExtendedEntity:
    """
    A knowledge graph node with organizational context.

    Extends the base Entity with:
      - team ownership (which team manages this entity)
      - product scope (which products this entity relates to)
      - evidence list (how we know about this entity)
      - temporal tracking (first/last seen, last verified)
    """
    id: str
    name: str
    entity_type: ExtendedEntityType
    description: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    # Organizational context
    team_id: Optional[str] = None       # owning team (from OrgMap)
    product_scope: list[str] = field(default_factory=list)
    visibility: str = "internal"        # internal | confidential | public

    # Evidence & confidence
    evidence: list[Evidence] = field(default_factory=list)
    average_confidence: float = 0.0

    # Temporal tracking
    first_seen: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_verified: Optional[str] = None
    verification_count: int = 0

    def add_evidence(self, evidence: Evidence) -> None:
        """Add evidence and recalculate average confidence."""
        self.evidence.append(evidence)
        if self.evidence:
            self.average_confidence = (
                sum(e.confidence for e in self.evidence) / len(self.evidence)
            )

    def to_dict(self) -> dict:
        """Serialize to dictionary for storage."""
        return {
            "id": self.id,
            "name": self.name,
            "entity_type": self.entity_type.value,
            "description": self.description,
            "metadata": self.metadata,
            "team_id": self.team_id,
            "product_scope": self.product_scope,
            "visibility": self.visibility,
            "average_confidence": self.average_confidence,
            "first_seen": self.first_seen,
            "last_verified": self.last_verified,
            "verification_count": self.verification_count,
        }


# =====================================================================
# Extended Relationship (carries evidence + confidence)
# =====================================================================

@dataclass
class ExtendedRelationship:
    """
    A directed edge in the knowledge graph.

    Every relationship MUST carry at least one Evidence record.
    Confidence is derived from the average of evidence confidences.
    """
    source_id: str
    target_id: str
    relation_type: ExtendedRelationType
    description: Optional[str] = None
    evidence: list[Evidence] = field(default_factory=list)
    confidence: float = 0.0
    metadata: dict = field(default_factory=dict)

    def recalculate_confidence(self) -> None:
        """Recalculate confidence from evidence list."""
        if self.evidence:
            self.confidence = (
                sum(e.confidence for e in self.evidence) / len(self.evidence)
            )

    def add_evidence(self, evidence: Evidence) -> None:
        """Add evidence and recalculate confidence."""
        self.evidence.append(evidence)
        self.recalculate_confidence()

    def to_dict(self) -> dict:
        """Serialize to dictionary for storage."""
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type.value,
            "description": self.description,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "evidence_count": len(self.evidence),
        }


# =====================================================================
# Mapping helpers: old types ? extended types
# =====================================================================

# EntityType -> ExtendedEntityType
ENTITY_TYPE_MAP = {
    EntityType.DOCUMENT: ExtendedEntityType.DOCUMENT,
    EntityType.PROCESS: ExtendedEntityType.PROCESS,
    EntityType.PERSON: ExtendedEntityType.PERSON,
    EntityType.SYSTEM: ExtendedEntityType.SYSTEM,
    EntityType.METRIC: ExtendedEntityType.METRIC,
    EntityType.CONFIGURATION: ExtendedEntityType.CONFIGURATION,
    EntityType.INCIDENT: ExtendedEntityType.INCIDENT,
    EntityType.KNOWLEDGE_ARTICLE: ExtendedEntityType.KNOWLEDGE_ARTICLE,
}

# RelationType -> ExtendedRelationType
RELATION_TYPE_MAP = {
    RelationType.RELATED_TO: ExtendedRelationType.REFERENCES,
    RelationType.DEPENDS_ON: ExtendedRelationType.DEPENDS_ON,
    RelationType.CONTAINS: ExtendedRelationType.CONTAINS,
    RelationType.GENERATES: ExtendedRelationType.GENERATES,
    RelationType.USES: ExtendedRelationType.USES,
    RelationType.MONITORS: ExtendedRelationType.MONITORS,
    RelationType.CONFIGURES: ExtendedRelationType.CONFIGURES,
    RelationType.TRIGGERS: ExtendedRelationType.TRIGGERS,
    RelationType.RESOLVES: ExtendedRelationType.RESOLVES,
}
