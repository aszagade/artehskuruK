"""
Opportunity Repository
======================

DuckDB persistence for events and opportunities.

Tables:
  - opportunity_events: raw events from enterprise systems
  - opportunity_store: detected opportunities
"""

from __future__ import annotations

import json
from typing import Optional

from kurukshetra.registry.database import get_connection
from .models import Event, Opportunity, OpportunityCategory, OpportunityStatus, SourceSystem


class OpportunityRepository:
    """DuckDB persistence for the Opportunity Engine."""

    def __init__(self) -> None:
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        conn = get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS opportunity_events (
                event_id TEXT PRIMARY KEY,
                source TEXT,
                event_type TEXT,
                subject TEXT,
                team TEXT,
                timestamp TEXT,
                details TEXT,
                source_url TEXT,
                quantity INTEGER DEFAULT 1,
                metadata TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS opportunity_store (
                opportunity_id TEXT PRIMARY KEY,
                title TEXT,
                category TEXT,
                source_system TEXT,
                affected_team TEXT,
                frequency INTEGER,
                evidence TEXT,
                confidence DOUBLE,
                status TEXT DEFAULT 'proposed',
                first_seen TEXT,
                last_seen TEXT,
                event_ids TEXT,
                metadata TEXT
            )
        """)
        conn.close()

    # -- Events --

    def insert_event(self, event: Event) -> None:
        conn = get_connection()
        conn.execute(
            """INSERT OR REPLACE INTO opportunity_events
            (event_id, source, event_type, subject, team, timestamp,
             details, source_url, quantity, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                event.event_id, event.source.value, event.event_type,
                event.subject, event.team, event.timestamp,
                event.details, event.source_url, event.quantity,
                json.dumps(event.metadata),
            ],
        )
        conn.close()

    def insert_events(self, events: list[Event]) -> None:
        conn = get_connection()
        for e in events:
            conn.execute(
                """INSERT OR REPLACE INTO opportunity_events
                (event_id, source, event_type, subject, team, timestamp,
                 details, source_url, quantity, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    e.event_id, e.source.value, e.event_type,
                    e.subject, e.team, e.timestamp,
                    e.details, e.source_url, e.quantity,
                    json.dumps(e.metadata),
                ],
            )
        conn.close()

    def get_events(
        self,
        source: Optional[str] = None,
        team: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> list[Event]:
        conn = get_connection()
        conditions = []
        params: list = []
        if source:
            conditions.append("source = ?")
            params.append(source)
        if team:
            conditions.append("team = ?")
            params.append(team)
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)

        where = " AND ".join(conditions) if conditions else "1=1"
        rows = conn.execute(
            f"SELECT * FROM opportunity_events WHERE {where} ORDER BY timestamp",
            params,
        ).fetchall()
        conn.close()

        return [
            Event(
                event_id=r[0], source=SourceSystem(r[1]), event_type=r[2],
                subject=r[3], team=r[4], timestamp=r[5],
                details=r[6], source_url=r[7], quantity=r[8],
                metadata=json.loads(r[9]) if r[9] else {},
            )
            for r in rows
        ]

    def get_event_count(self) -> int:
        conn = get_connection()
        n = conn.execute("SELECT COUNT(*) FROM opportunity_events").fetchone()[0]
        conn.close()
        return n

    # -- Opportunities --

    def upsert_opportunity(self, opp: Opportunity) -> None:
        conn = get_connection()
        conn.execute(
            """INSERT INTO opportunity_store
            (opportunity_id, title, category, source_system, affected_team,
             frequency, evidence, confidence, status, first_seen, last_seen,
             event_ids, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(opportunity_id) DO UPDATE SET
                frequency = excluded.frequency,
                confidence = excluded.confidence,
                last_seen = excluded.last_seen,
                event_ids = excluded.event_ids,
                metadata = excluded.metadata""",
            [
                opp.opportunity_id, opp.title, opp.category.value,
                opp.source_system.value, opp.affected_team,
                opp.frequency, opp.evidence, opp.confidence,
                opp.status.value, opp.first_seen, opp.last_seen,
                json.dumps(opp.event_ids), json.dumps(opp.metadata),
            ],
        )
        conn.close()

    def get_opportunities(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
        team: Optional[str] = None,
    ) -> list[Opportunity]:
        conn = get_connection()
        conditions = []
        params: list = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if category:
            conditions.append("category = ?")
            params.append(category)
        if team:
            conditions.append("affected_team = ?")
            params.append(team)

        where = " AND ".join(conditions) if conditions else "1=1"
        rows = conn.execute(
            f"SELECT * FROM opportunity_store WHERE {where} ORDER BY confidence DESC",
            params,
        ).fetchall()
        conn.close()

        return [
            Opportunity(
                opportunity_id=r[0], title=r[1],
                category=OpportunityCategory(r[2]),
                source_system=SourceSystem(r[3]),
                affected_team=r[4], frequency=r[5],
                evidence=r[6], confidence=r[7],
                status=OpportunityStatus(r[8]),
                first_seen=r[9], last_seen=r[10],
                event_ids=json.loads(r[11]) if r[11] else [],
                metadata=json.loads(r[12]) if r[12] else {},
            )
            for r in rows
        ]

    def update_status(self, opportunity_id: str, status: str) -> None:
        conn = get_connection()
        conn.execute(
            "UPDATE opportunity_store SET status = ? WHERE opportunity_id = ?",
            (status, opportunity_id),
        )
        conn.close()

    def get_stats(self) -> dict:
        conn = get_connection()
        total = conn.execute("SELECT COUNT(*) FROM opportunity_store").fetchone()[0]
        by_status = conn.execute(
            "SELECT status, COUNT(*) FROM opportunity_store GROUP BY status"
        ).fetchall()
        by_category = conn.execute(
            "SELECT category, COUNT(*) FROM opportunity_store GROUP BY category"
        ).fetchall()
        events = conn.execute("SELECT COUNT(*) FROM opportunity_events").fetchone()[0]
        conn.close()

        return {
            "total_opportunities": total,
            "total_events": events,
            "by_status": {r[0]: r[1] for r in by_status},
            "by_category": {r[0]: r[1] for r in by_category},
        }
