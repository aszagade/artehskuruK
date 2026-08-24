"""
Event Bus
=========

Single ingestion layer for every external system connector.

Every connector calls bus.ingest(event) or bus.ingest_batch(events).
The bus:
  1. Validates the event
  2. Computes fingerprint if missing
  3. Deduplicates against existing events
  4. Persists to DuckDB
  5. Returns batch result

No actions are executed. The bus only stores and deduplicates.

Usage:
    bus = EventBus()
    result = bus.ingest_batch(events)
    print(f"Inserted: {result.inserted}, Deduped: {result.deduplicated}")
"""

from __future__ import annotations

from typing import Optional

from .models import Event, EventBatch, EventStats, EventStatus
from .repository import EventRepository
from .normalizer import EventNormalizer


class EventBus:
    """
    Enterprise Event Bus — single ingestion point for all connectors.

    Responsibilities:
      - Validate events
      - Compute fingerprints
      - Deduplicate
      - Persist to DuckDB
      - Provide query and stats

    Does NOT:
      - Execute actions
      - Modify SANJAYA, RAG, Graph, SEAL, or Opportunity Engine
      - Call any LLM
    """

    def __init__(self) -> None:
        self.repository = EventRepository()
        self.normalizer = EventNormalizer()

    def ingest(self, event: Event) -> bool:
        """
        Ingest a single event.
        Returns True if inserted, False if duplicate.
        """
        # Ensure fingerprint exists
        if not event.fingerprint:
            event.fingerprint = EventNormalizer.compute_fingerprint(
                event.source.value, event.entity_id,
                event.source_type, event.title,
            )
        return self.repository.insert_event(event)

    def ingest_batch(self, events: list[Event]) -> EventBatch:
        """Ingest a batch of events with deduplication."""
        # Ensure fingerprints
        for event in events:
            if not event.fingerprint:
                event.fingerprint = EventNormalizer.compute_fingerprint(
                    event.source.value, event.entity_id,
                    event.source_type, event.title,
                )
        return self.repository.insert_events(events)

    def get_event(self, event_id: str) -> Optional[Event]:
        """Get a single event by ID."""
        return self.repository.get_event(event_id)

    def query(
        self,
        source: Optional[str] = None,
        team: Optional[str] = None,
        entity_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[Event]:
        """Query events with optional filters."""
        return self.repository.get_events(
            source=source, team=team, entity_id=entity_id,
            entity_type=entity_type, status=status, limit=limit,
        )

    def update_status(self, event_id: str, status: EventStatus) -> None:
        """Update an event's lifecycle status."""
        self.repository.update_status(event_id, status)

    def get_stats(self) -> EventStats:
        """Get aggregate statistics."""
        return self.repository.get_stats()

    def clear(self) -> int:
        """Clear all events. Returns count deleted."""
        return self.repository.clear()

    # ------------------------------------------------------------------
    # Convenience: ingest from raw dict (for connectors)
    # ------------------------------------------------------------------

    def ingest_raw(self, raw: dict, source: str) -> Event:
        """
        Ingest a raw dict from a connector.
        Returns the normalized Event after persistence.
        """
        from .models import SourceSystem as Src

        src = Src(source.lower()) if source.lower() in [s.value for s in Src] else Src.INTERNAL

        event = self.normalizer.normalize_generic(
            event_id=raw.get("event_id", f"RAW-{str(hash(str(raw)))[:8]}"),
            source=src,
            source_type=raw.get("source_type", "unknown"),
            title=raw.get("title", "Untitled"),
            entity_id=raw.get("entity_id", "unknown"),
            entity_type=raw.get("entity_type", "unknown"),
            team=raw.get("team", "unknown"),
            actor=raw.get("actor", "unknown"),
            timestamp=raw.get("timestamp"),
            payload=raw.get("payload", {}),
            evidence=raw.get("evidence", ""),
        )

        self.ingest(event)
        return event
