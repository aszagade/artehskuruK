"""
Source Adapter — Abstract Base Contract
=======================================

Every enterprise source connector implements this contract.

The contract is deliberately minimal:

1. identify()     — who am I?
2. discover()     — what documents exist?
3. fetch()        — give me the content
4. health()       — are you working?

Change detection is handled by the adapter using SourceCursor,
which is persisted by the Knowledge Fabric.

Design principle: adapters are stateless between calls.
The Fabric manages cursors, fingerprints, and version state.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator, Optional

from .models import (
    SourceCapability,
    SourceDocument,
    SourceHealth,
    SourceIdentity,
)


class SourceAdapter(ABC):
    """
    Abstract base for all source adapters.

    Subclass this for Salesforce, Confluence, Datadog, SQL, etc.

    The adapter is responsible for:
    - Connecting to its source system
    - Discovering available documents/content
    - Fetching document content as SourceDocuments
    - Reporting health status

    The adapter is NOT responsible for:
    - Change detection (managed by Knowledge Fabric via cursors)
    - Deduplication (managed by Knowledge Fabric via SHA-256)
    - Ingestion into RAG/Graph/SEAL (managed by Knowledge Fabric)
    - Access control enforcement (managed by Knowledge Fabric)
    """

    def __init__(self, config: Optional[dict] = None) -> None:
        """
        Initialize the adapter with source-specific configuration.

        Args:
            config: Adapter-specific configuration dict.
                    Credentials and secrets should be resolved from
                    environment variables, not passed in config.
        """
        self.config = config or {}

    # ------------------------------------------------------------------
    # Required: Source Identity
    # ------------------------------------------------------------------

    @abstractmethod
    def identify(self) -> SourceIdentity:
        """
        Return the identity of this source.

        Called once during registration to establish source identity.
        Must be deterministic — same config produces same identity.
        """

    # ------------------------------------------------------------------
    # Required: Document Discovery
    # ------------------------------------------------------------------

    @abstractmethod
    def discover(self, cursor: Optional[str] = None) -> Iterator[SourceDocument]:
        """
        Discover and yield documents from this source.

        Args:
            cursor: Optional opaque cursor from a previous discover() call.
                    If None, discover all documents.
                    If provided, discover only documents changed since
                    the cursor was created.

        Yields:
            SourceDocument for each discovered document.

        The adapter should yield documents lazily where possible.
        Each SourceDocument must carry full DocumentProvenance.
        """

    # ------------------------------------------------------------------
    # Required: Health Check
    # ------------------------------------------------------------------

    @abstractmethod
    def health(self) -> SourceHealth:
        """
        Check if the source is accessible and healthy.

        Called periodically by the Knowledge Fabric to monitor source health.
        Should be lightweight — don't fetch all documents.
        """

    # ------------------------------------------------------------------
    # Optional: Capabilities
    # ------------------------------------------------------------------

    def capabilities(self) -> SourceCapability:
        """
        Declare what this adapter can do.

        Override to declare specific capabilities.
        Default assumes basic discovery + content fetch.
        """
        return SourceCapability()

    # ------------------------------------------------------------------
    # Optional: Lifecycle
    # ------------------------------------------------------------------

    def setup(self) -> None:
        """
        One-time setup called when the adapter is first registered.

        Use for connection validation, schema creation, etc.
        Default is no-op.
        """

    def teardown(self) -> None:
        """
        Cleanup called when the adapter is unregistered.

        Use for closing connections, releasing resources.
        Default is no-op.
        """

    def configure(self, config: dict) -> None:
        """
        Update adapter configuration.

        Called when configuration changes at runtime.
        """
        self.config.update(config)
