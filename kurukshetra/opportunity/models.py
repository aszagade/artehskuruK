"""
Opportunity Engine Models
=========================

Data structures for enterprise opportunity detection.

An Opportunity represents a discovered pattern across enterprise systems
that warrants human review. It never executes actions — only proposes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class OpportunityCategory(Enum):
    """Categories of opportunities the engine can detect."""
    AUTOMATION = "automation"
    MONITORING = "monitoring"
    DOCUMENTATION = "documentation"
    PROCESS_IMPROVEMENT = "process_improvement"
    KNOWLEDGE_GAP = "knowledge_gap"
    DUPLICATE_WORK = "duplicate_work"
    RISK_DETECTION = "risk_detection"


class OpportunityStatus(Enum):
    """Lifecycle status of an opportunity."""
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"


class SourceSystem(Enum):
    """Enterprise systems the engine analyzes."""
    DATADOG = "datadog"
    SALESFORCE = "salesforce"
    CONFLUENCE = "confluence"
    TEAMS = "teams"
    OUTLOOK = "outlook"
    SQL = "sql"
    SMARTSHEET = "smartsheet"
    INTERNAL = "internal"  # KURUKSHETRA's own data


@dataclass(slots=True)
class Event:
    """
    A structured event from an enterprise system.

    The detector consumes events and discovers patterns.
    Events are the raw input — never modified by the engine.
    """
    event_id: str
    source: SourceSystem
    event_type: str         # alert, query, ticket, document_update, etc.
    subject: str            # what the event is about
    team: str               # affected team
    timestamp: str          # ISO timestamp
    metadata: dict = field(default_factory=dict)
    # Evidence
    details: str = ""       # human-readable description
    source_url: str = ""    # link to original event
    quantity: int = 1       # for aggregated events


@dataclass(slots=True)
class Opportunity:
    """
    A discovered pattern that warrants human review.

    Every opportunity carries evidence explaining why it was created.
    The engine never executes — only proposes.
    """
    opportunity_id: str
    title: str
    category: OpportunityCategory
    source_system: SourceSystem
    affected_team: str
    frequency: int              # how many events triggered this
    evidence: str               # why this was detected
    confidence: float           # 0.0-1.0, how strong the signal is
    status: OpportunityStatus = OpportunityStatus.PROPOSED
    first_seen: str = ""
    last_seen: str = ""
    event_ids: list[str] = field(default_factory=list)  # source events
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class DetectionResult:
    """Result of a detection run."""
    opportunities_found: int
    events_analyzed: int
    categories: dict[str, int]  # category -> count
    elapsed_seconds: float
