"""
Mocked Salesforce Adapter
=========================

Proof-of-concept adapter demonstrating the Source Adapter contract
using deterministic, local test data.

This adapter simulates a Salesforce Knowledge base with:
- Knowledge articles
- Case workflows
- Configuration documents

All data is deterministic and local — no Salesforce credentials required.

When real Salesforce API access is available, this adapter would be
replaced by a SalesforceAPIAdapter that uses the same contract.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Iterator, Optional

from .adapter import SourceAdapter
from .models import (
    DocumentProvenance,
    SourceCapability,
    SourceDocument,
    SourceHealth,
    SourceIdentity,
    SourceType,
)


# ==================================================================
# Deterministic Mock Data
# ==================================================================

MOCK_ARTICLES = [
    {
        "id": "KA-0001",
        "title": "SFDC Case Workflow — AMS Recoding",
        "body": (
            "## AMS Recoding Workflow\n\n"
            "This document describes the AMS Recoding process for SFDC cases.\n\n"
            "### Overview\n"
            "When a client requests AMS recoding, the following steps are performed:\n"
            "1. Client Services receives the request via CPM/CRM\n"
            "2. A scope of work (SoW) is created\n"
            "3. The case is assigned to the Case Owner\n"
            "4. Technical team performs the recoding\n"
            "5. QA validates the changes\n"
            "6. Deployment to production via G3AMSRC0\n\n"
            "### Systems Involved\n"
            "- G3AMSRC0 (CPM/CRM)\n"
            "- SFDC (Service Cloud)\n"
            "- RMS (Rate Management System)\n\n"
            "### Team\n"
            "Primary: SPM (Service Product Management)\n"
            "Supporting: ICS (Implementation & Client Services)\n"
        ),
        "object_type": "Knowledge__kav",
        "last_modified": datetime(2025, 6, 15, 10, 30),
        "author": "admin@ideas.com",
        "url": "https://ideas.salesforce.com/knowledge/KA-0001",
    },
    {
        "id": "KA-0002",
        "title": "G3 Data Feed Configuration Guide",
        "body": (
            "## G3 Data Feed Configuration\n\n"
            "This document covers the configuration of G3 data feeds for "
            "real-time pricing updates.\n\n"
            "### Feed Types\n"
            "- RMS2G3_Prices: Real-time price updates from RMS to G3\n"
            "- G32SFDC_Status: Status updates from G3 to Salesforce\n"
            "- D360_G3_Inventory: Inventory data from D360 to G3\n\n"
            "### Configuration Steps\n"
            "1. Verify G3 service account credentials\n"
            "2. Configure feed schedule in RMS admin\n"
            "3. Map field aliases between systems\n"
            "4. Test feed with sample data\n"
            "5. Enable production schedule\n\n"
            "### Important Notes\n"
            "Feed frequency: Every 5 minutes for pricing, hourly for status.\n"
            "Monitoring: Check G3_DATA_FEED_STATUS dashboard for feed health.\n"
            "Contact: SDOPS team for feed infrastructure issues.\n"
        ),
        "object_type": "Knowledge__kav",
        "last_modified": datetime(2025, 7, 20, 14, 15),
        "author": "sdops@ideas.com",
        "url": "https://ideas.salesforce.com/knowledge/KA-0002",
    },
    {
        "id": "KA-0003",
        "title": "Rate Shopping Migration Process",
        "body": (
            "## Rate Shopping Migration\n\n"
            "Migration process for moving rate shopping configurations "
            "from legacy RMS to the new G3 Rate Shopping module.\n\n"
            "### Prerequisites\n"
            "- G3 Rate Shopping module licensed\n"
            "- RMS legacy rate data exported\n"
            "- Client approval for migration timeline\n\n"
            "### Migration Steps\n"
            "1. Export rate shopping rules from RMS (RMS2G3_RSExport)\n"
            "2. Transform data format for G3 compatibility\n"
            "3. Import into G3 Rate Shopping (G3_RSImport)\n"
            "4. Validate rate calculations match legacy system\n"
            "5. Switch client traffic to G3 endpoints\n"
            "6. Monitor for 48 hours\n"
            "7. Decommission legacy RMS rate shopping\n\n"
            "### Rollback Plan\n"
            "If issues are detected within 7 days, switch traffic back "
            "to legacy RMS endpoints. Contact SDOPS for rollback support.\n"
        ),
        "object_type": "Knowledge__kav",
        "last_modified": datetime(2025, 5, 10, 9, 0),
        "author": "spm@ideas.com",
        "url": "https://ideas.salesforce.com/knowledge/KA-0003",
    },
    {
        "id": "KA-0004",
        "title": "Proactive Monitoring — Data Discrepancy",
        "body": (
            "## G3 Proactive Monitoring: Data Discrepancy Detection\n\n"
            "This document describes the proactive monitoring system for "
            "detecting data discrepancies between G3 and downstream systems.\n\n"
            "### Monitored Systems\n"
            "- G3 ↔ SFDC: Case data sync\n"
            "- G3 ↔ RMS: Rate data sync\n"
            "- G3 ↔ D360: Inventory data sync\n\n"
            "### Discrepancy Types\n"
            "1. Price mismatch: G3 price differs from SFDC display price\n"
            "2. Status lag: Case status not updated within SLA (5 min)\n"
            "3. Missing records: Record exists in G3 but not in SFDC\n"
            "4. Orphan records: Record exists in SFDC but not in G3\n\n"
            "### Alert Channels\n"
            "- Datadog: G3_PROACTIVE_MONITORING dashboard\n"
            "- Email: sdops-alerts@ideas.com\n"
            "- PagerDuty: G3-DataIntegrity service\n\n"
            "### Response Procedure\n"
            "1. Acknowledge alert in PagerDuty\n"
            "2. Check Datadog dashboard for scope\n"
            "3. If price mismatch: halt affected feeds\n"
            "4. If status lag: check G3 service health\n"
            "5. Escalate to SDOPS lead if unresolved in 30 min\n"
        ),
        "object_type": "Knowledge__kav",
        "last_modified": datetime(2025, 8, 1, 16, 45),
        "author": "sdops@ideas.com",
        "url": "https://ideas.salesforce.com/knowledge/KA-0004",
    },
    {
        "id": "KA-0005",
        "title": "G3 Stats to Inventory Transition",
        "body": (
            "## G3 Stats to Inventory Transition\n\n"
            "Migration of statistical reporting from legacy G3 Stats module "
            "to the new unified Inventory dashboard.\n\n"
            "### Background\n"
            "The legacy G3 Stats module provided nightly statistical reports. "
            "The new Inventory module provides real-time dashboards with "
            "the same data plus additional metrics.\n\n"
            "### Transition Plan\n"
            "Phase 1: Run parallel (4 weeks)\n"
            "- Enable Inventory dashboard alongside G3 Stats\n"
            "- Compare daily outputs for discrepancies\n"
            "- Document any metric differences\n\n"
            "Phase 2: Client migration (2 weeks)\n"
            "- Migrate client-specific report subscriptions\n"
            "- Update scheduled report recipients\n"
            "- Disable legacy G3 Stats access per client\n\n"
            "Phase 3: Decommission (1 week)\n"
            "- Archive G3 Stats data\n"
            "- Remove G3 Stats service from production\n"
            "- Update documentation\n\n"
            "### Key Contacts\n"
            "- SDOPS: Infrastructure and service management\n"
            "- SPM: Product requirements and client communication\n"
            "- ICS: Client-facing migration support\n"
        ),
        "object_type": "Knowledge__kav",
        "last_modified": datetime(2025, 4, 12, 11, 30),
        "author": "spm@ideas.com",
        "url": "https://ideas.salesforce.com/knowledge/KA-0005",
    },
]


# ==================================================================
# Mocked Salesforce Adapter
# ==================================================================


class SalesforceMockAdapter(SourceAdapter):
    """
    Mocked Salesforce Knowledge adapter.

    Produces deterministic SourceDocuments from local test data.
    Demonstrates the full adapter contract without API access.
    """

    def __init__(self, config: Optional[dict] = None) -> None:
        super().__init__(config)
        self._instance_url = self.config.get(
            "instance_url", "https://ideas.salesforce.com"
        )
        self._api_version = self.config.get("api_version", "v59.0")

    def identify(self) -> SourceIdentity:
        return SourceIdentity(
            source_id="sforce-knowledge-mock",
            source_type=SourceType.SALESFORCE,
            display_name="Salesforce Knowledge (Mock)",
            description="Mocked Salesforce Knowledge base for development/testing",
            owner_team="sdops",
            config={
                "instance_url": self._instance_url,
                "api_version": self._api_version,
            },
        )

    def discover(
        self, cursor: Optional[str] = None
    ) -> Iterator[SourceDocument]:
        """
        Discover articles from the mock data.

        If cursor is provided, only yield articles modified after
        the cursor timestamp.
        """
        since = None
        if cursor:
            try:
                since = datetime.fromisoformat(cursor)
            except (ValueError, TypeError):
                since = None

        for article in MOCK_ARTICLES:
            # Apply cursor filtering
            if since and article["last_modified"] <= since:
                continue

            provenance = DocumentProvenance(
                source_id="sforce-knowledge-mock",
                source_type=SourceType.SALESFORCE,
                source_path=article["url"],
                source_collection="Knowledge__kav",
                external_id=article["id"],
                external_url=article["url"],
                fetched_at=datetime.utcnow(),
                last_modified_at=article["last_modified"],
                content_hash=_hash_text(article["body"]),
                version_tag=f"1.0",
            )

            # Determine teams from content
            team_ids = _detect_teams_from_text(article["body"])

            yield SourceDocument(
                title=article["title"],
                text_content=article["body"],
                content_type="text/markdown",
                format_hint="knowledge_article",
                provenance=provenance,
                team_ids=team_ids,
                ownership_type="associated",
                team_confidence=0.7,
                visibility="Internal",
                metadata={
                    "object_type": article["object_type"],
                    "author": article["author"],
                    "article_id": article["id"],
                },
                tags=["salesforce", "knowledge", "workflow"],
                detected_systems=_detect_systems(article["body"]),
                detected_processes=_detect_processes(article["body"]),
            )

    def health(self) -> SourceHealth:
        """Always healthy in mock mode."""
        return SourceHealth(
            source_id="sforce-knowledge-mock",
            healthy=True,
            documents_total=len(MOCK_ARTICLES),
            documents_fresh=len(MOCK_ARTICLES),
            details={"mode": "mock", "article_count": len(MOCK_ARTICLES)},
        )

    def capabilities(self) -> SourceCapability:
        return SourceCapability(
            supports_discovery=True,
            supports_incremental=True,
            supports_content_fetch=True,
            supports_metadata=True,
            supports_deletion=False,
            supports_versioning=True,
            supports_teams=True,
            supports_visibility=True,
            max_batch_size=100,
        )


# ==================================================================
# Helpers
# ==================================================================


def _hash_text(text: str) -> str:
    """Deterministic SHA-256 of text content."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _detect_teams_from_text(text: str) -> list[str]:
    """Simple keyword-based team detection."""
    teams = []
    text_upper = text.upper()
    if "SPM" in text_upper or "SERVICE PRODUCT" in text_upper:
        teams.append("spm")
    if "ICS" in text_upper or "IMPLEMENTATION" in text_upper or "CLIENT SERVICES" in text_upper:
        teams.append("ics")
    if "SDOPS" in text_upper:
        teams.append("sdops")
    if "CPM" in text_upper:
        teams.append("cpm")
    return teams


def _detect_systems(text: str) -> list[str]:
    """Simple system detection from text."""
    systems = []
    known = [
        "G3", "RMS", "SFDC", "D360", "AMS", "G3AMSRC0",
        "CPM", "CRM", "Datadog", "PagerDuty",
    ]
    for sys_name in known:
        if sys_name in text:
            systems.append(sys_name)
    return systems


def _detect_processes(text: str) -> list[str]:
    """Simple process detection from text."""
    processes = []
    text_lower = text.lower()
    if "migration" in text_lower:
        processes.append("migration")
    if "workflow" in text_lower:
        processes.append("workflow")
    if "monitoring" in text_lower:
        processes.append("monitoring")
    if "configuration" in text_lower:
        processes.append("configuration")
    return processes
