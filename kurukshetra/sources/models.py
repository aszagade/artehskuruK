"""
Source Adapter Data Models
==========================

Canonical representations shared by all source adapters.

Every source type (Salesforce, Confluence, Datadog, SQL, filesystem, etc.)
produces the same SourceDocument representation that feeds into the
Knowledge Fabric.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


# ==================================================================
# Source Types
# ==================================================================


class SourceType(Enum):
    """Known source types. Extensible for future connectors."""

    FILESYSTEM = "filesystem"
    NETWORK_SHARE = "network_share"
    SALESFORCE = "salesforce"
    CONFLUENCE = "confluence"
    DATADOG = "datadog"
    SQL = "sql"
    TEAMS = "teams"
    OUTLOOK = "outlook"
    GRAPH_API = "graph_api"
    SMARTSHEET = "smartsheet"
    GITHUB = "github"
    CUSTOM = "custom"


# ==================================================================
# Source Identity
# ==================================================================


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    """
    Immutable identity for a knowledge source.

    Each source type has exactly one SourceIdentity, even if it
    serves multiple teams or collections.
    """

    source_id: str            # Unique identifier, e.g. "sforce-prod", "ics-share"
    source_type: SourceType   # Which connector type
    display_name: str         # Human-readable name
    description: str = ""     # What this source contains
    owner_team: str = ""      # Team responsible for the source (not document ownership)
    config: dict[str, Any] = field(default_factory=dict)  # Source-specific config (non-secret)

    def __post_init__(self) -> None:
        if not self.source_id:
            raise ValueError("source_id is required")
        if not self.source_type:
            raise ValueError("source_type is required")


# ==================================================================
# Document Provenance
# ==================================================================


@dataclass(slots=True)
class DocumentProvenance:
    """
    Full provenance chain for a document.

    Every document entering the system through an adapter carries
    complete provenance: where it came from, when it was seen,
    who owns it, and what trust level it carries.
    """

    source_id: str                                # Which source
    source_type: SourceType                       # Source type
    source_path: str                              # Original location (URL, path, ID)
    source_collection: str = ""                   # Sub-collection (folder, object type)
    external_id: str = ""                         # Source-system's own ID
    external_url: str = ""                        # Direct link to the original
    fetched_at: datetime = field(default_factory=datetime.utcnow)
    last_modified_at: Optional[datetime] = None   # Source's own modification time
    content_hash: str = ""                        # SHA-256 of content for dedup
    version_tag: str = ""                         # Source's version if available
    trust_level: str = "observed"                 # observed | candidate | confirmed

    def __str__(self) -> str:
        return f"{self.source_id}:{self.source_path}"


# ==================================================================
# Source Cursor (Incremental Change Detection)
# ==================================================================


@dataclass(slots=True)
class SourceCursor:
    """
    Cursor for incremental change detection.

    Each adapter type defines its own cursor semantics:
    - filesystem: highest mtime seen
    - Salesforce: last SystemModstamp
    - Confluence: last modified date
    - SQL: last row ID or timestamp
    """

    source_id: str
    cursor_type: str               # Adapter-defined cursor type
    cursor_value: str              # Opaque cursor value
    last_run: datetime = field(default_factory=datetime.utcnow)
    items_processed: int = 0
    items_new: int = 0
    items_changed: int = 0
    items_removed: int = 0
    errors: int = 0


# ==================================================================
# Source Document (Canonical Representation)
# ==================================================================


@dataclass(slots=True)
class SourceDocument:
    """
    Canonical document representation from any source adapter.

    This is the bridge between external sources and the Knowledge Fabric.
    Every adapter produces SourceDocuments; the Fabric consumes them
    through a single ingestion path.
    """

    # Content
    title: str                                       # Document title
    text_content: str                                # Full extractable text
    content_type: str = "text/plain"                 # MIME type
    format_hint: str = ""                            # Original format (pdf, xlsx, html, json)

    # Provenance (required)
    provenance: DocumentProvenance = field(default_factory=lambda: DocumentProvenance(
        source_id="", source_type=SourceType.CUSTOM, source_path="",
    ))

    # Team / ownership
    team_ids: list[str] = field(default_factory=list)         # Associated teams
    ownership_type: str = "associated"                        # owner | user | supporting | affected | associated
    team_confidence: float = 0.5                              # Confidence in team association

    # Security / visibility
    visibility: str = "Internal"                              # public | internal | confidential | restricted
    classification: str = ""                                  # Optional classification label
    access_groups: list[str] = field(default_factory=list)    # Who can access this document

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)   # Source-specific metadata
    tags: list[str] = field(default_factory=list)            # Free-form tags
    language: str = "en"                                      # ISO 639-1

    # Content signals
    detected_systems: list[str] = field(default_factory=list)   # Systems mentioned
    detected_products: list[str] = field(default_factory=list)  # Products mentioned
    detected_processes: list[str] = field(default_factory=list) # Processes mentioned
    detected_acronyms: list[str] = field(default_factory=list)  # Acronyms found
    detected_identifiers: list[str] = field(default_factory=list) # IDs, ticket numbers

    # Lifecycle
    status: str = "active"          # active | archived | deleted
    parent_doc_id: str = ""         # Parent document if hierarchical
    child_doc_ids: list[str] = field(default_factory=list)  # Child documents

    def __post_init__(self) -> None:
        if not self.title:
            raise ValueError("SourceDocument.title is required")
        if not self.text_content:
            raise ValueError("SourceDocument.text_content is required")


# ==================================================================
# Source Capabilities
# ==================================================================


@dataclass(frozen=True, slots=True)
class SourceCapability:
    """
    Declares what an adapter can do.

    The Knowledge Fabric uses capabilities to determine how to
    interact with each source.
    """

    supports_discovery: bool = True        # Can enumerate documents
    supports_incremental: bool = False     # Can do incremental detection
    supports_content_fetch: bool = True    # Can fetch document content
    supports_metadata: bool = True         # Can provide rich metadata
    supports_deletion: bool = False        # Can detect deleted documents
    supports_versioning: bool = False      # Can track document versions
    supports_teams: bool = False           # Can provide team/ownership info
    supports_visibility: bool = False      # Can provide access control info
    max_batch_size: int = 100              # Max documents per fetch
    supports_streaming: bool = False       # Can stream large results


# ==================================================================
# Source Health
# ==================================================================


@dataclass(slots=True)
class SourceHealth:
    """Health/status of a source adapter."""

    source_id: str
    healthy: bool = True
    last_check: datetime = field(default_factory=datetime.utcnow)
    last_error: str = ""
    last_success: Optional[datetime] = None
    documents_total: int = 0
    documents_fresh: int = 0
    documents_stale: int = 0
    latency_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)
