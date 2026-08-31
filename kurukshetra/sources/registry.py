"""
Source Adapter Registry
=======================

Manages source adapter instances, their lifecycle, and coordination
with the Knowledge Fabric.

The registry is the single entry point for:
- Registering new source adapters
- Listing available sources
- Triggering discovery/ingestion from all sources
- Monitoring source health
"""

from __future__ import annotations

import logging
from typing import Optional

from .adapter import SourceAdapter
from .models import SourceHealth, SourceIdentity

logger = logging.getLogger(__name__)


class SourceAdapterRegistry:
    """
    Registry of all configured source adapters.

    Usage:
        registry = SourceAdapterRegistry()
        registry.register(SalesforceAdapter(config={...}))
        registry.register(FilesystemAdapter(config={...}))

        for identity in registry.list_sources():
            print(identity.source_id)

        for doc in registry.discover_all():
            fabric.ingest_source_document(doc)
    """

    def __init__(self) -> None:
        self._adapters: dict[str, SourceAdapter] = {}
        self._identities: dict[str, SourceIdentity] = {}

    def register(self, adapter: SourceAdapter) -> SourceIdentity:
        """
        Register a source adapter.

        Calls adapter.identify() to get the source identity,
        then stores the adapter.

        Returns:
            SourceIdentity for the registered source.
        """
        identity = adapter.identify()
        source_id = identity.source_id

        if source_id in self._adapters:
            logger.warning(f"Replacing existing adapter for source: {source_id}")
            old = self._adapters[source_id]
            old.teardown()

        self._adapters[source_id] = adapter
        self._identities[source_id] = identity
        logger.info(f"Registered adapter: {source_id} ({identity.source_type.value})")

        try:
            adapter.setup()
        except Exception as e:
            logger.warning(f"Adapter setup failed for {source_id}: {e}")

        return identity

    def unregister(self, source_id: str) -> bool:
        """
        Unregister a source adapter.

        Returns True if the adapter was found and removed.
        """
        adapter = self._adapters.pop(source_id, None)
        self._identities.pop(source_id, None)

        if adapter:
            try:
                adapter.teardown()
            except Exception as e:
                logger.warning(f"Adapter teardown failed for {source_id}: {e}")
            return True
        return False

    def get(self, source_id: str) -> Optional[SourceAdapter]:
        """Get an adapter by source ID."""
        return self._adapters.get(source_id)

    def get_identity(self, source_id: str) -> Optional[SourceIdentity]:
        """Get a source identity by source ID."""
        return self._identities.get(source_id)

    def list_sources(self) -> list[SourceIdentity]:
        """List all registered source identities."""
        return list(self._identities.values())

    def list_source_ids(self) -> list[str]:
        """List all registered source IDs."""
        return list(self._adapters.keys())

    def count(self) -> int:
        """Number of registered adapters."""
        return len(self._adapters)

    def health_all(self) -> list[SourceHealth]:
        """Check health of all registered sources."""
        results = []
        for source_id, adapter in self._adapters.items():
            try:
                health = adapter.health()
                results.append(health)
            except Exception as e:
                results.append(SourceHealth(
                    source_id=source_id,
                    healthy=False,
                    last_error=str(e),
                ))
        return results

    def health_one(self, source_id: str) -> Optional[SourceHealth]:
        """Check health of a specific source."""
        adapter = self._adapters.get(source_id)
        if not adapter:
            return None
        try:
            return adapter.health()
        except Exception as e:
            return SourceHealth(
                source_id=source_id,
                healthy=False,
                last_error=str(e),
            )

    def clear(self) -> int:
        """
        Remove all adapters.

        Returns the number of adapters removed.
        """
        count = len(self._adapters)
        for source_id in list(self._adapters.keys()):
            self.unregister(source_id)
        return count
