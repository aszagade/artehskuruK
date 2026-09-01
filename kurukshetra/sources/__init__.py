"""
Source Adapter Foundation
========================

Canonical interface for all enterprise knowledge sources.

Every external source (Salesforce, Confluence, Datadog, SQL, filesystem,
Teams, Outlook, etc.) feeds knowledge into KURUKSHETRA through the same
adapter contract.

Design principles:
- One adapter per source type
- Adapters produce canonical SourceDocument objects
- SourceDocuments carry full provenance and security metadata
- Adapters handle their own discovery and incremental change detection
- The Knowledge Fabric ingests SourceDocuments through the same pipeline
- No source is automatically trusted — provenance is always preserved

Usage:
    from kurukshetra.sources import SourceAdapterRegistry, SalesforceAdapter

    registry = SourceAdapterRegistry()
    registry.register(SalesforceAdapter(config={...}))

    for adapter in registry:
        for doc in adapter.discover():
            fabric.ingest_source_document(doc)
"""

from .models import (
    SourceDocument,
    SourceIdentity,
    SourceCursor,
    SourceCapability,
    SourceHealth,
    SourceType,
    DocumentProvenance,
)
from .adapter import SourceAdapter
from .registry import SourceAdapterRegistry
from .salesforce_adapter import SalesforceAdapter
from .salesforce_transport import (
    SalesforceTransport,
    MockSalesforceTransport,
    SalesforceHTTPTransport,
    SFRecord,
)
from .salesforce_mock import SalesforceMockAdapter
from .persistent_registry import PersistentSourceRegistry, SourceRecord, SyncStateRecord
from .authority import AuthorityStore, AuthorityLevel, DocumentAuthority, AuthorityConflict

__all__ = [
    "SourceDocument",
    "SourceIdentity",
    "SourceCursor",
    "SourceCapability",
    "SourceHealth",
    "SourceType",
    "DocumentProvenance",
    "SourceAdapter",
    "SourceAdapterRegistry",
    "PersistentSourceRegistry",
    "SourceRecord",
    "SyncStateRecord",
    "AuthorityStore",
    "AuthorityLevel",
    "DocumentAuthority",
    "AuthorityConflict",
    "SalesforceAdapter",
    "SalesforceTransport",
    "MockSalesforceTransport",
    "SFRecord",
    "SalesforceMockAdapter",
]
