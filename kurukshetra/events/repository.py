"""
Event Repository
================

DuckDB persistence for the Enterprise Event Bus.

Tables:
  - enterprise_events: canonical events from all connectors
  - event_fingerprints: deduplication index

Design:
  - Idempotent inserts (INSERT OR IGNORE)
  - Fingerprint-based deduplication
  - Efficient queries by source, team, entity, time range
"""

from __future__ import annotations

import json
from typing import Optional

from kurukshetra.registry.database import get_connection
from .models import Event, EventBatch, EventStats, EventStatus, SourceSystem, EventType, EntityKind


class EventRepository:
    """DuckDB persistence for the Enterprise Event Bus."""

    def __init__(self) -> None:
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        conn = get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS enterprise_events (
                event_id TEXT PRIMARY KEY,
                source TEXT,
                source_type TEXT,
                entity_id TEXT,
                entity_type TEXT,
                title TEXT,
                timestamp TEXT,
                actor TEXT,
                team TEXT,
                payload TEXT,
                evidence TEXT,
                metadata TEXT,
                fingerprint TEXT,
                status TEXT DEFAULT 'new',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS event_fingerprints (
                fingerprint TEXT PRIMARY KEY,
                event_id TEXT,
                first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
                occurrence_count INTEGER DEFAULT 1
            )
        """)
        # Indexes for common queries
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_source ON enterprise_events(source)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_team ON enterprise_events(team)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_entity ON enterprise_events(entity_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_status ON enterprise_events(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_fingerprint ON enterprise_events(fingerprint)")
        except Exception:
            pass  # Indexes may already exist
        conn.close()

    def insert_event(self, event: Event) -> bool:
        """
        Insert a single event. Returns True if inserted, False if duplicate.
        Idempotent: same event_id or same fingerprint → skipped.
        """
        conn = get_connection()
        try:
            # Check event_id deduplication
            exists = conn.execute(
                "SELECT 1 FROM enterprise_events WHERE event_id = ?",
                (event.event_id,),
            ).fetchone()
            if exists:
                conn.close()
                return False

            # Check fingerprint deduplication
            if event.fingerprint:
                existing = conn.execute(
                    "SELECT event_id FROM event_fingerprints WHERE fingerprint = ?",
                    (event.fingerprint,),
                ).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE event_fingerprints SET occurrence_count = occurrence_count + 1 "
                        "WHERE fingerprint = ?",
                        (event.fingerprint,),
                    )
                    conn.close()
                    return False

            # Insert event
            conn.execute(
                """INSERT INTO enterprise_events
                (event_id, source, source_type, entity_id, entity_type,
                 title, timestamp, actor, team, payload, evidence,
                 metadata, fingerprint, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    event.event_id, event.source.value,
                    event.source_type.value if hasattr(event.source_type, 'value') else event.source_type,
                    event.entity_id, event.entity_type.value if hasattr(event.entity_type, 'value') else event.entity_type, event.title,
                    event.timestamp, event.actor, event.team,
                    json.dumps(event.payload), event.evidence,
                    json.dumps(event.metadata), event.fingerprint,
                    event.status.value,
                ],
            )

            # Record fingerprint
            if event.fingerprint:
                conn.execute(
                    """INSERT INTO event_fingerprints
                    (fingerprint, event_id)
                    VALUES (?, ?)""",
                    (event.fingerprint, event.event_id),
                )

            conn.close()
            return True
        except Exception:
            conn.close()
            return False

    def insert_events(self, events: list[Event]) -> EventBatch:
        """Insert a batch of events with deduplication."""
        inserted = 0
        deduplicated = 0
        rejected = 0
        errors: list[str] = []

        for event in events:
            try:
                if self.insert_event(event):
                    inserted += 1
                else:
                    deduplicated += 1
            except Exception as e:
                rejected += 1
                errors.append(f"{event.event_id}: {e}")

        return EventBatch(
            total=len(events),
            inserted=inserted,
            deduplicated=deduplicated,
            rejected=rejected,
            errors=errors,
        )

    def get_event(self, event_id: str) -> Optional[Event]:
        """Get a single event by ID."""
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM enterprise_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        conn.close()
        if row is None:
            return None
        return self._row_to_event(row)

    def get_events(
        self,
        source: Optional[str] = None,
        team: Optional[str] = None,
        entity_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Event]:
        """Query events with filters."""
        conn = get_connection()
        conditions = []
        params: list = []
        if source:
            conditions.append("source = ?")
            params.append(source)
        if team:
            conditions.append("team = ?")
            params.append(team)
        if entity_id:
            conditions.append("entity_id = ?")
            params.append(entity_id)
        if entity_type:
            conditions.append("entity_type = ?")
            params.append(entity_type)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where = " AND ".join(conditions) if conditions else "1=1"
        rows = conn.execute(
            f"SELECT * FROM enterprise_events WHERE {where} "
            f"ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        conn.close()
        return [self._row_to_event(r) for r in rows]

    def get_event_count(self, source: Optional[str] = None) -> int:
        conn = get_connection()
        if source:
            n = conn.execute(
                "SELECT COUNT(*) FROM enterprise_events WHERE source = ?",
                (source,),
            ).fetchone()[0]
        else:
            n = conn.execute("SELECT COUNT(*) FROM enterprise_events").fetchone()[0]
        conn.close()
        return n

    def get_deduplicated_count(self) -> int:
        """Count events that were deduplicated (fingerprint seen >1 time)."""
        conn = get_connection()
        n = conn.execute(
            "SELECT SUM(occurrence_count - 1) FROM event_fingerprints "
            "WHERE occurrence_count > 1"
        ).fetchone()[0]
        conn.close()
        return n or 0

    def update_status(self, event_id: str, status: EventStatus) -> None:
        conn = get_connection()
        conn.execute(
            "UPDATE enterprise_events SET status = ? WHERE event_id = ?",
            (status.value, event_id),
        )
        conn.close()

    def get_stats(self) -> EventStats:
        """Aggregate statistics."""
        conn = get_connection()
        total = conn.execute("SELECT COUNT(*) FROM enterprise_events").fetchone()[0]

        by_source = dict(conn.execute(
            "SELECT source, COUNT(*) FROM enterprise_events GROUP BY source"
        ).fetchall())
        by_type = dict(conn.execute(
            "SELECT entity_type, COUNT(*) FROM enterprise_events GROUP BY entity_type"
        ).fetchall())
        by_team = dict(conn.execute(
            "SELECT team, COUNT(*) FROM enterprise_events GROUP BY team"
        ).fetchall())
        by_status = dict(conn.execute(
            "SELECT status, COUNT(*) FROM enterprise_events GROUP BY status"
        ).fetchall())
        dedup = conn.execute(
            "SELECT COALESCE(SUM(occurrence_count - 1), 0) FROM event_fingerprints "
            "WHERE occurrence_count > 1"
        ).fetchone()[0]
        conn.close()

        return EventStats(
            total_events=total,
            by_source=by_source,
            by_type=by_type,
            by_team=by_team,
            by_status=by_status,
            deduplicated_count=dedup,
        )

    def clear(self) -> int:
        """Delete all events. Returns count deleted."""
        conn = get_connection()
        n = conn.execute("SELECT COUNT(*) FROM enterprise_events").fetchone()[0]
        conn.execute("DELETE FROM enterprise_events")
        conn.execute("DELETE FROM event_fingerprints")
        conn.close()
        return n

    @staticmethod
    def _row_to_event(row: tuple) -> Event:
        return Event(
            event_id=row[0],
            source=SourceSystem(row[1]),
            source_type=row[2],
            entity_id=row[3],
            entity_type=EntityKind(row[4]),
            title=row[5],
            timestamp=row[6],
            actor=row[7],
            team=row[8],
            payload=json.loads(row[9]) if row[9] else {},
            evidence=row[10] or "",
            metadata=json.loads(row[11]) if row[11] else {},
            fingerprint=row[12] or "",
            status=EventStatus(row[13]) if row[13] else EventStatus.NEW,
        )
