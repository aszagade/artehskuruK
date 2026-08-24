"""
Event Bus Models
================

Canonical event model for every external system connector.

Every system (Datadog, Salesforce, Teams, Outlook, Confluence, SQL,
Smartsheet) normalizes its data into this single Event model before
entering Kurukshetra.

Design principles:
  - Deterministic only
  - Idempotent inserts
  - Deduplicate repeated events
  - Never execute actions
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SourceSystem(Enum):
    """Enterprise systems that produce events."""
    DATADOG = "datadog"
    SALESFORCE = "salesforce"
    CONFLUENCE = "confluence"
    TEAMS = "teams"
    OUTLOOK = "outlook"
    SQL = "sql"
    SMARTSHEET = "smartsheet"
    INTERNAL = "internal"


class EventType(Enum):
    """Event categories."""
    ALERT = "alert"
    ERROR = "error"
    INCIDENT = "incident"
    DEPLOYMENT = "deployment"
    CONFIG_CHANGE = "config_change"
    DOCUMENT_UPDATE = "document_update"
    QUERY = "query"
    SEARCH = "search"
    TICKET = "ticket"
    MESSAGE = "message"
    FEEDBACK = "feedback"
    HEARTBEAT = "heartbeat"
    OTHER = "other"


class EntityKind(Enum):
    """Types of entities an event can reference."""
    SYSTEM = "system"
    PROCESS = "process"
    INCIDENT = "incident"
    DOCUMENT = "document"
    PERSON = "person"
    TEAM = "team"
    CLIENT = "client"
    CONFIGURATION = "configuration"
    METRIC = "metric"
    UNKNOWN = "unknown"


class EventStatus(Enum):
    """Lifecycle status of an event."""
    NEW = "new"
    PROCESSED = "processed"
    DEDUPLICATED = "deduplicated"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


@dataclass(slots=True)
class Event:
    """
    Canonical enterprise event.

    Every connector normalizes its data into this model.
    The bus deduplicates by event_id and fingerprint.

    Fields:
      event_id:    Unique identifier (connector + original ID)
      source:      Which enterprise system
      source_type: Sub-type within the system (e.g. "monitor", "alert")
      entity_id:   ID of the entity this event concerns
      entity_type: Kind of entity (system, process, document, etc.)
      title:       Human-readable summary
      timestamp:   ISO 8601
      actor:       Who or what triggered this event
      team:        Owning team (from OrgMap)
      payload:     Full structured data (JSON-serializable)
      evidence:    Why this event matters (human-readable)
      metadata:    Extensible key-value pairs
      fingerprint: Deduplication hash (auto-computed if blank)
      status:      Lifecycle status
    """
    event_id: str
    source: SourceSystem
    source_type: str
    entity_id: str
    entity_type: EntityKind
    title: str
    timestamp: str
    actor: str
    team: str
    payload: dict = field(default_factory=dict)
    evidence: str = ""
    metadata: dict = field(default_factory=dict)
    fingerprint: str = ""
    status: EventStatus = EventStatus.NEW


@dataclass(slots=True)
class EventBatch:
    """Result of ingesting a batch of events."""
    total: int
    inserted: int
    deduplicated: int
    rejected: int
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EventStats:
    """Aggregate statistics about stored events."""
    total_events: int
    by_source: dict[str, int]
    by_type: dict[str, int]
    by_team: dict[str, int]
    by_status: dict[str, int]
    deduplicated_count: int
