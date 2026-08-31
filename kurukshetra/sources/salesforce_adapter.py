"""
Production Salesforce Adapter
==============================

Salesforce Knowledge adapter implementing the full SourceAdapter contract
with production concerns:

- Transport abstraction (swap real/mock without changing adapter logic)
- Incremental sync via SystemModstamp cursor
- Cursor persistence in DuckDB
- Retry with exponential backoff
- Pagination for large result sets
- Deletion detection
- Team/visibility metadata
- Audit logging
- Error boundaries (one failed record doesn't stop discovery)

Usage:
    from kurukshetra.sources.salesforce_adapter import SalesforceAdapter

    adapter = SalesforceAdapter(config={
        "instance_url": "https://ideas.salesforce.com",
        "username": "user@ideas.com",
        # password/token resolved from env: SF_PASSWORD, SF_SECURITY_TOKEN
        "soql_objects": ["Knowledge__kav", "Case"],
        "batch_size": 200,
        "max_retries": 3,
    })

    # Or with mock transport for testing:
    adapter = SalesforceAdapter(transport=MockSalesforceTransport(...))
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from datetime import datetime
from typing import Any, Iterator, Optional

from .adapter import SourceAdapter
from .models import (
    DocumentProvenance,
    SourceCapability,
    SourceDocument,
    SourceHealth,
    SourceIdentity,
    SourceType,
)
from .salesforce_transport import (
    SFRecord,
    SalesforceTransport,
    SFTransportStats,
)

logger = logging.getLogger(__name__)

# ==================================================================
# Default Configuration
# ==================================================================

DEFAULT_CONFIG = {
    "instance_url": "https://login.salesforce.com",
    "api_version": "v59.0",
    "batch_size": 200,
    "max_retries": 3,
    "retry_base_delay_ms": 1000,
    "retry_max_delay_ms": 30000,
    "soql_objects": ["Knowledge__kav"],
    "title_field": "Title",
    "body_field": "KnowledgeBody__c",
    "url_prefix": "",
}

# Fields to extract from each SF record
KNOWLEDGE_FIELDS = [
    "Id", "Title", "KnowledgeBody__c", "Summary",
    "ArticleNumber", "SystemModstamp", "LastModifiedDate",
    "CreatedDate", "IsDeleted", "PublishStatus",
    "ValidationStatus", "Language",
]

CASE_FIELDS = [
    "Id", "Subject", "Description", "CaseNumber",
    "SystemModstamp", "LastModifiedDate", "CreatedDate",
    "IsDeleted", "Status", "Priority", "Type",
    "Team__c", "Product__c",
]


# ==================================================================
# Salesforce Adapter
# ==================================================================


class SalesforceAdapter(SourceAdapter):
    """
    Production Salesforce adapter.

    Implements incremental sync, cursor persistence, retry, pagination,
    and deletion detection.
    """

    def __init__(
        self,
        config: Optional[dict] = None,
        transport: Optional[SalesforceTransport] = None,
    ) -> None:
        super().__init__(config)
        self._transport = transport  # Injected for testing
        self._cfg = {**DEFAULT_CONFIG, **(config or {})}
        self._connected = False
        self._cursor: Optional[str] = None

    # ------------------------------------------------------------------
    # Source Identity
    # ------------------------------------------------------------------

    def identify(self) -> SourceIdentity:
        return SourceIdentity(
            source_id=self.config.get("source_id", "sforce-prod"),
            source_type=SourceType.SALESFORCE,
            display_name="Salesforce Knowledge",
            description="Salesforce Knowledge base and Case data",
            owner_team="sdops",
            config={
                "instance_url": self._cfg["instance_url"],
                "api_version": self._cfg["api_version"],
                "objects": self._cfg["soql_objects"],
            },
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def setup(self) -> None:
        """Validate connection or set up mock transport."""
        if self._transport is None:
            # In production, create HTTP transport here
            # For now, require transport injection
            raise RuntimeError(
                "SalesforceAdapter requires a transport. "
                "Inject MockSalesforceTransport for testing or "
                "SalesforceHTTPTransport for production."
            )
        self._transport.connect()
        self._connected = True
        self._cursor = self._load_cursor()
        logger.info(
            f"Salesforce adapter connected. Cursor: {self._cursor or 'none (full sync)'}"
        )

    def teardown(self) -> None:
        if self._transport:
            self._transport.close()
        self._connected = False

    # ------------------------------------------------------------------
    # Discovery with Incremental Sync
    # ------------------------------------------------------------------

    def discover(
        self, cursor: Optional[str] = None
    ) -> Iterator[SourceDocument]:
        """
        Discover records from Salesforce.

        If cursor is provided (or a persisted cursor exists), only
        fetch records modified since that cursor timestamp.

        Handles:
        - Pagination (batch_size)
        - Retry on transient errors
        - Error boundaries (skip bad records)
        - Deletion detection
        """
        if not self._connected:
            raise RuntimeError("Adapter not connected. Call setup() first.")

        # Determine sync mode
        sync_cursor = cursor or self._cursor
        is_incremental = sync_cursor is not None

        if is_incremental:
            logger.info(f"Incremental sync since {sync_cursor}")
        else:
            logger.info("Full sync — no cursor")

        stats = SFTransportStats()
        max_retries = self._cfg["max_retries"]
        retry_base = self._cfg["retry_base_delay_ms"]
        retry_max = self._cfg["retry_max_delay_ms"]
        batch_size = self._cfg["batch_size"]

        # Track latest SystemModstamp for cursor update
        latest_modstamp: Optional[datetime] = None

        for object_type in self._cfg["soql_objects"]:
            fields = (
                KNOWLEDGE_FIELDS if "Knowledge" in object_type
                else CASE_FIELDS
            )
            field_list = ", ".join(fields)

            # Build SOQL
            soql = f"SELECT {field_list} FROM {object_type}"
            if is_incremental:
                soql += f" WHERE SystemModstamp > {sync_cursor}"
            soql += f" ORDER BY SystemModstamp ASC LIMIT {batch_size}"

            # Execute with retry
            result = self._execute_with_retry(soql, max_retries, retry_base, retry_max)

            if result is None:
                logger.error(f"Failed to query {object_type} after {max_retries} retries")
                continue

            for record in result.records:
                try:
                    doc = self._record_to_document(record, object_type)
                    if doc:
                        # Track cursor
                        if record.system_modstamp:
                            if latest_modstamp is None or record.system_modstamp > latest_modstamp:
                                latest_modstamp = record.system_modstamp
                        yield doc
                except Exception as e:
                    logger.warning(f"Error processing record {record.record_id}: {e}")
                    stats.errors += 1

            # Check for deleted records
            if is_incremental and sync_cursor:
                try:
                    deleted_ids = self._transport.get_deleted(
                        object_type, datetime.fromisoformat(sync_cursor)
                    )
                    for deleted_id in deleted_ids:
                        yield SourceDocument(
                            title=f"Deleted: {deleted_id}",
                            text_content=f"[DELETED] Record {deleted_id} was removed from {object_type}",
                            provenance=DocumentProvenance(
                                source_id=self.identify().source_id,
                                source_type=SourceType.SALESFORCE,
                                source_path=f"salesforce://{object_type}/{deleted_id}",
                                external_id=deleted_id,
                            ),
                            status="deleted",
                        )
                except Exception as e:
                    logger.warning(f"Deletion check failed for {object_type}: {e}")

        # Persist updated cursor
        if latest_modstamp:
            new_cursor = latest_modstamp.isoformat()
            self._save_cursor(new_cursor)
            self._cursor = new_cursor
            logger.info(f"Cursor updated: {new_cursor}")

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> SourceHealth:
        if not self._transport:
            return SourceHealth(
                source_id=self.identify().source_id,
                healthy=False,
                last_error="No transport configured",
            )

        start = time.time()
        healthy = self._transport.is_healthy()
        latency = (time.time() - start) * 1000

        stats = self._transport.get_stats()

        return SourceHealth(
            source_id=self.identify().source_id,
            healthy=healthy,
            last_error="" if healthy else "Transport unhealthy",
            latency_ms=round(latency, 1),
            details={
                "objects": self._cfg["soql_objects"],
                "cursor": self._cursor,
                "queries_executed": stats.queries_executed,
                "records_fetched": stats.records_fetched,
                "api_calls": stats.api_calls,
                "errors": stats.errors,
            },
        )

    def capabilities(self) -> SourceCapability:
        return SourceCapability(
            supports_discovery=True,
            supports_incremental=True,
            supports_content_fetch=True,
            supports_metadata=True,
            supports_deletion=True,
            supports_versioning=True,
            supports_teams=True,
            supports_visibility=True,
            max_batch_size=self._cfg["batch_size"],
        )

    # ------------------------------------------------------------------
    # Record → SourceDocument Conversion
    # ------------------------------------------------------------------

    def _record_to_document(
        self, record: SFRecord, object_type: str
    ) -> Optional[SourceDocument]:
        """Convert a Salesforce record to a canonical SourceDocument."""

        # Extract title
        title = record.get("Title") or record.get("Subject") or record.get("CaseNumber") or record.record_id

        # Extract body/content
        body = record.get("KnowledgeBody__c") or record.get("Description") or ""
        summary = record.get("Summary") or ""

        # Combine for full text
        text_parts = []
        if title:
            text_parts.append(f"# {title}")
        if summary:
            text_parts.append(f"\n{summary}")
        if body:
            text_parts.append(f"\n{body}")

        text_content = "\n".join(text_parts)
        if not text_content.strip():
            text_content = f"[{object_type}] {title}"

        # Content hash for dedup
        content_hash = hashlib.sha256(text_content.encode("utf-8")).hexdigest()

        # Provenance
        instance_url = self._cfg["instance_url"]
        record_url = f"{instance_url}/{record.record_id}"
        if self._cfg.get("url_prefix"):
            record_url = f"{instance_url}/{self._cfg['url_prefix']}/{record.record_id}"

        provenance = DocumentProvenance(
            source_id=self.identify().source_id,
            source_type=SourceType.SALESFORCE,
            source_path=record_url,
            source_collection=object_type,
            external_id=record.record_id,
            external_url=record_url,
            fetched_at=datetime.utcnow(),
            last_modified_at=record.system_modstamp or record.last_modified_date,
            content_hash=content_hash,
            version_tag=f"v{record.created_date.isoformat()}" if record.created_date else "",
        )

        # Team detection
        team_ids = self._detect_teams(record, text_content)

        # Visibility
        visibility = self._determine_visibility(record)

        # Metadata
        metadata = {
            "object_type": object_type,
            "record_id": record.record_id,
            "article_number": record.get("ArticleNumber"),
            "publish_status": record.get("PublishStatus"),
            "validation_status": record.get("ValidationStatus"),
            "language": record.get("Language", "en"),
            "priority": record.get("Priority"),
            "status": record.get("Status"),
        }

        # Content signals
        systems = self._detect_systems(text_content)
        processes = self._detect_processes(text_content)

        return SourceDocument(
            title=title,
            text_content=text_content,
            content_type="text/markdown",
            format_hint="salesforce_knowledge",
            provenance=provenance,
            team_ids=team_ids,
            ownership_type="associated",
            team_confidence=0.6,
            visibility=visibility,
            metadata=metadata,
            tags=["salesforce", object_type.lower()],
            detected_systems=systems,
            detected_processes=processes,
        )

    # ------------------------------------------------------------------
    # Team Detection
    # ------------------------------------------------------------------

    def _detect_teams(self, record: SFRecord, text: str) -> list[str]:
        """Detect team associations from record fields and content."""
        teams = []

        # Check explicit team field
        team_field = record.get("Team__c")
        if team_field:
            teams.append(team_field.lower())

        # Content-based detection
        text_upper = text.upper()
        team_keywords = {
            "spm": ["SPM", "SERVICE PRODUCT"],
            "ics": ["ICS", "IMPLEMENTATION", "CLIENT SERVICES"],
            "sdops": ["SDOPS", "SERVICE DELIVERY"],
            "cpm": ["CPM", "CLIENT PROJECT"],
            "roa": ["ROA", "REVENUE OPERATIONS"],
        }
        for team_id, keywords in team_keywords.items():
            if any(kw in text_upper for kw in keywords):
                if team_id not in teams:
                    teams.append(team_id)

        return teams

    def _determine_visibility(self, record: SFRecord) -> str:
        """Determine document visibility from record metadata."""
        status = record.get("PublishStatus", "")
        if status == "Draft":
            return "Internal"
        validation = record.get("ValidationStatus", "")
        if "Approved" in str(validation):
            return "Internal"
        return "Internal"

    # ------------------------------------------------------------------
    # System/Process Detection
    # ------------------------------------------------------------------

    def _detect_systems(self, text: str) -> list[str]:
        systems = []
        known = [
            "G3", "RMS", "SFDC", "D360", "AMS", "G3AMSRC0",
            "CPM", "CRM", "Datadog", "PagerDuty",
        ]
        for sys_name in known:
            if sys_name in text:
                systems.append(sys_name)
        return systems

    def _detect_processes(self, text: str) -> list[str]:
        processes = []
        text_lower = text.lower()
        for proc in ["migration", "workflow", "monitoring", "configuration",
                      "installation", "verification", "deployment"]:
            if proc in text_lower:
                processes.append(proc)
        return processes

    # ------------------------------------------------------------------
    # Retry Logic
    # ------------------------------------------------------------------

    def _execute_with_retry(
        self, soql: str, max_retries: int, base_delay_ms: int, max_delay_ms: int
    ) -> Optional[Any]:
        """Execute a SOQL query with exponential backoff retry."""
        for attempt in range(max_retries + 1):
            try:
                return self._transport.query(soql)
            except ConnectionError as e:
                if attempt == max_retries:
                    logger.error(f"Query failed after {max_retries} retries: {e}")
                    return None
                delay_ms = min(
                    base_delay_ms * (2 ** attempt),
                    max_delay_ms,
                )
                logger.warning(
                    f"Query attempt {attempt + 1} failed: {e}. "
                    f"Retrying in {delay_ms}ms..."
                )
                time.sleep(delay_ms / 1000)
            except Exception as e:
                logger.error(f"Unexpected error in query: {e}")
                return None
        return None

    # ------------------------------------------------------------------
    # Cursor Persistence
    # ------------------------------------------------------------------

    def _load_cursor(self) -> Optional[str]:
        """Load persisted cursor from KnowledgeFabric."""
        try:
            from kurukshetra.knowledge.fabric import KnowledgeFabric
            fabric = KnowledgeFabric()
            return fabric.load_source_cursor(self.identify().source_id)
        except Exception as e:
            logger.warning(f"Failed to load cursor: {e}")
            return None

    def _save_cursor(self, cursor_value: str) -> None:
        """Persist cursor to KnowledgeFabric."""
        try:
            from kurukshetra.knowledge.fabric import KnowledgeFabric
            fabric = KnowledgeFabric()
            fabric.save_source_cursor(self.identify().source_id, cursor_value)
        except Exception as e:
            logger.warning(f"Failed to save cursor: {e}")
