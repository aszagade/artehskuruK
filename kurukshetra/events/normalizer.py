"""
Event Normalizer
================

Converts raw data from external systems into canonical Event objects.

Each connector calls the appropriate normalizer method:
  - DatadogConnector → normalize_datadog_alert(...)
  - SalesforceConnector → normalize_salesforce_ticket(...)
  - TeamsConnector → normalize_teams_message(...)

The normalizer:
  1. Maps external fields to canonical Event fields
  2. Generates a fingerprint for deduplication
  3. Sets entity_type based on content analysis
  4. Enriches with evidence and metadata
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Optional

from .models import Event, EventType, SourceSystem, EntityKind, EventStatus


class EventNormalizer:
    """
    Converts raw system data into canonical Events.

    Each method handles one source system. The fingerprint is
    computed from (source, entity_id, event_type, title) to
    deduplicate repeated identical events.
    """

    # ------------------------------------------------------------------
    # Fingerprint generation
    # ------------------------------------------------------------------

    @staticmethod
    def compute_fingerprint(
        source: str,
        entity_id: str,
        event_type: str,
        title: str,
    ) -> str:
        """
        Deterministic fingerprint for deduplication.

        Same source + entity + type + title → same fingerprint.
        """
        raw = f"{source}|{entity_id}|{event_type}|{title}".lower().strip()
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Datadog normalization
    # ------------------------------------------------------------------

    def normalize_datadog_alert(
        self,
        alert_id: str,
        title: str,
        body: str,
        priority: str = "info",
        team: str = "unknown",
        timestamp: Optional[str] = None,
        tags: Optional[dict] = None,
    ) -> Event:
        """Normalize a Datadog alert into a canonical Event."""
        tags = tags or {}
        entity_id = tags.get("host", tags.get("service", "unknown"))
        entity_type = self._infer_entity_type(title, body)

        evidence = f"Datadog alert '{title}' (priority: {priority})"
        if body:
            evidence += f" — {body[:200]}"

        event_type_str = "alert" if priority in ("critical", "error", "high") else "heartbeat"

        return Event(
            event_id=f"DD-{alert_id}",
            source=SourceSystem.DATADOG,
            source_type="alert",
            entity_id=entity_id,
            entity_type=entity_type,
            title=title,
            timestamp=timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            actor="datadog",
            team=team,
            payload={"priority": priority, "body": body, "tags": tags},
            evidence=evidence,
            metadata={"alert_id": alert_id, "priority": priority},
            fingerprint=self.compute_fingerprint("datadog", entity_id, event_type_str, title),
        )

    # ------------------------------------------------------------------
    # Salesforce normalization
    # ------------------------------------------------------------------

    def normalize_salesforce_ticket(
        self,
        ticket_id: str,
        subject: str,
        description: str,
        status: str = "open",
        team: str = "unknown",
        timestamp: Optional[str] = None,
        case_type: str = "support",
    ) -> Event:
        """Normalize a Salesforce case/ticket into a canonical Event."""
        entity_type = EntityKind.INCIDENT if "incident" in subject.lower() else EntityKind.UNKNOWN
        event_type_str = "ticket"

        evidence = f"Salesforce case '{subject}' (status: {status}, type: {case_type})"
        if description:
            evidence += f" — {description[:200]}"

        return Event(
            event_id=f"SF-{ticket_id}",
            source=SourceSystem.SALESFORCE,
            source_type="ticket",
            entity_id=ticket_id,
            entity_type=entity_type,
            title=subject,
            timestamp=timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            actor="salesforce",
            team=team,
            payload={"status": status, "description": description, "case_type": case_type},
            evidence=evidence,
            metadata={"ticket_id": ticket_id, "status": status, "case_type": case_type},
            fingerprint=self.compute_fingerprint("salesforce", ticket_id, event_type_str, subject),
        )

    # ------------------------------------------------------------------
    # Confluence normalization
    # ------------------------------------------------------------------

    def normalize_confluence_page(
        self,
        page_id: str,
        title: str,
        space: str,
        content_preview: str = "",
        author: str = "unknown",
        team: str = "unknown",
        timestamp: Optional[str] = None,
    ) -> Event:
        """Normalize a Confluence page update into a canonical Event."""
        entity_type = EntityKind.DOCUMENT

        evidence = f"Confluence page '{title}' in space '{space}' updated by {author}"
        if content_preview:
            evidence += f" — {content_preview[:200]}"

        return Event(
            event_id=f"CONF-{page_id}",
            source=SourceSystem.CONFLUENCE,
            source_type="document_update",
            entity_id=page_id,
            entity_type=entity_type,
            title=title,
            timestamp=timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            actor=author,
            team=team,
            payload={"space": space, "content_preview": content_preview},
            evidence=evidence,
            metadata={"page_id": page_id, "space": space},
            fingerprint=self.compute_fingerprint("confluence", page_id, "document_update", title),
        )

    # ------------------------------------------------------------------
    # Teams normalization
    # ------------------------------------------------------------------

    def normalize_teams_message(
        self,
        message_id: str,
        channel: str,
        content: str,
        author: str = "unknown",
        team: str = "unknown",
        timestamp: Optional[str] = None,
        is_question: bool = False,
    ) -> Event:
        """Normalize a Teams message into a canonical Event."""
        event_type_str = "search" if is_question else "message"
        entity_type = EntityKind.PERSON

        evidence = f"Teams message in #{channel} by {author}"
        if content:
            evidence += f" — {content[:200]}"

        return Event(
            event_id=f"TEAM-{message_id}",
            source=SourceSystem.TEAMS,
            source_type="message",
            entity_id=message_id,
            entity_type=entity_type,
            title=content[:100] if content else "Empty message",
            timestamp=timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            actor=author,
            team=team,
            payload={"channel": channel, "content": content, "is_question": is_question},
            evidence=evidence,
            metadata={"message_id": message_id, "channel": channel},
            fingerprint=self.compute_fingerprint("teams", message_id, event_type_str, content[:100]),
        )

    # ------------------------------------------------------------------
    # Outlook normalization
    # ------------------------------------------------------------------

    def normalize_outlook_email(
        self,
        message_id: str,
        subject: str,
        body_preview: str,
        from_address: str = "unknown",
        team: str = "unknown",
        timestamp: Optional[str] = None,
        is_shared_mailbox: bool = False,
    ) -> Event:
        """Normalize an Outlook email into a canonical Event."""
        entity_type = EntityKind.DOCUMENT
        source_type = "message"

        evidence = f"Email '{subject}' from {from_address}"
        if is_shared_mailbox:
            evidence += " (shared mailbox)"
        if body_preview:
            evidence += f" — {body_preview[:200]}"

        return Event(
            event_id=f"OUTLOOK-{message_id}",
            source=SourceSystem.OUTLOOK,
            source_type=source_type,
            entity_id=message_id,
            entity_type=entity_type,
            title=subject,
            timestamp=timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            actor=from_address,
            team=team,
            payload={"from": from_address, "body_preview": body_preview, "is_shared": is_shared_mailbox},
            evidence=evidence,
            metadata={"message_id": message_id},
            fingerprint=self.compute_fingerprint("outlook", message_id, source_type, subject),
        )

    # ------------------------------------------------------------------
    # SQL normalization
    # ------------------------------------------------------------------

    def normalize_sql_event(
        self,
        query_id: str,
        query_text: str,
        database: str,
        team: str = "unknown",
        timestamp: Optional[str] = None,
        rows_affected: int = 0,
        duration_ms: float = 0,
    ) -> Event:
        """Normalize a SQL query event into a canonical Event."""
        entity_type = EntityKind.SYSTEM
        event_type_str = "query"

        evidence = f"SQL query on '{database}' ({rows_affected} rows, {duration_ms:.0f}ms)"
        if query_text:
            evidence += f" — {query_text[:200]}"

        return Event(
            event_id=f"SQL-{query_id}",
            source=SourceSystem.SQL,
            source_type="query",
            entity_id=query_id,
            entity_type=entity_type,
            title=f"SQL: {query_text[:80]}",
            timestamp=timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            actor="sql_executor",
            team=team,
            payload={"database": database, "query": query_text, "rows_affected": rows_affected, "duration_ms": duration_ms},
            evidence=evidence,
            metadata={"database": database, "duration_ms": duration_ms},
            fingerprint=self.compute_fingerprint("sql", query_id, event_type_str, query_text[:80]),
        )

    # ------------------------------------------------------------------
    # Generic normalization
    # ------------------------------------------------------------------

    def normalize_generic(
        self,
        event_id: str,
        source: SourceSystem,
        source_type: str,
        title: str,
        entity_id: str = "unknown",
        entity_type: EntityKind = EntityKind.UNKNOWN,
        team: str = "unknown",
        actor: str = "unknown",
        timestamp: Optional[str] = None,
        payload: Optional[dict] = None,
        evidence: str = "",
    ) -> Event:
        """Normalize any custom event into the canonical model."""
        return Event(
            event_id=event_id,
            source=source,
            source_type=source_type,
            entity_id=entity_id,
            entity_type=entity_type,
            title=title,
            timestamp=timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            actor=actor,
            team=team,
            payload=payload or {},
            evidence=evidence or title,
            fingerprint=self.compute_fingerprint(source.value, entity_id, source_type, title),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_entity_type(title: str, body: str = "") -> EntityKind:
        """Infer entity type from content keywords."""
        text = f"{title} {body}".lower()
        if any(w in text for w in ("error", "exception", "crash", "incident", "timeout")):
            return EntityKind.INCIDENT
        if any(w in text for w in ("deploy", "release", "build", "pipeline")):
            return EntityKind.PROCESS
        if any(w in text for w in ("config", "setting", "parameter", "threshold")):
            return EntityKind.CONFIGURATION
        if any(w in text for w in ("metric", "gauge", "counter", "rate")):
            return EntityKind.METRIC
        return EntityKind.SYSTEM
