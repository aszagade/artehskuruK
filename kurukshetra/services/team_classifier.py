"""
Team Classifier
===============

Auto-classifies documents and queries to teams using the OrgMap.

Features:
- Multi-signal classification (keywords + filename + content patterns)
- Cross-team detection (documents used by multiple teams)
- Confidence scoring per team
- Persistent classification history in DuckDB
- Classification override and correction support
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Optional

from kurukshetra.agent.org_map import OrgMap, TeamDefinition
from kurukshetra.registry.database import get_connection


@dataclass(slots=True)
class ClassificationResult:
    """Result of classifying a document or query to teams."""
    primary_team_id: str
    primary_team_name: str
    all_team_matches: list[dict]  # [{team_id, team_name, confidence, is_cross_team, matched_sub_teams}]
    is_cross_team: bool
    cross_team_ids: list[str]
    confidence: float
    method: str  # "auto", "override", "correction"


class TeamClassifier:
    """
    Classifies documents and queries to organizational teams.

    Uses the OrgMap for classification and stores results in DuckDB.
    """

    def __init__(self) -> None:
        self.org_map = OrgMap()
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Create classification tables."""
        conn = get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS team_classifications (
                document_id TEXT,
                primary_team TEXT,
                all_matches TEXT,
                is_cross_team BOOLEAN,
                cross_team_ids TEXT,
                confidence DOUBLE,
                method TEXT,
                classified_at TIMESTAMP,
                PRIMARY KEY (document_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS team_corrections (
                document_id TEXT,
                original_team TEXT,
                corrected_team TEXT,
                corrected_by TEXT,
                corrected_at TIMESTAMP
            )
        """)
        conn.close()

    def classify_document(
        self,
        text: str,
        filename: str = "",
        document_id: str = "",
    ) -> ClassificationResult:
        """
        Classify a document to its owning team(s).

        Args:
            text: Document text content
            filename: Original filename
            document_id: Unique document ID

        Returns:
            ClassificationResult with team assignments
        """
        # Use OrgMap for classification
        matches = self.org_map.classify_document(text, filename)

        if not matches:
            return ClassificationResult(
                primary_team_id="unknown",
                primary_team_name="UNKNOWN",
                all_team_matches=[],
                is_cross_team=False,
                cross_team_ids=[],
                confidence=0.0,
                method="auto",
            )

        primary = matches[0]
        cross_team_ids = [
            m["team_id"] for m in matches[1:]
            if m.get("is_cross_team", False)
        ]

        result = ClassificationResult(
            primary_team_id=primary["team_id"],
            primary_team_name=primary["team_name"],
            all_team_matches=matches,
            is_cross_team=len(cross_team_ids) > 0,
            cross_team_ids=cross_team_ids,
            confidence=primary["confidence"],
            method="auto",
        )

        # Persist classification
        if document_id:
            self._persist_classification(document_id, result)

        return result

    def classify_query(self, query: str) -> list[dict]:
        """
        Classify a user query to determine which team's knowledge to search.

        Returns ranked list of team matches with sub-team specificity.
        """
        matches = self.org_map.classify_team_by_keywords(query)

        results = []
        for team_id, score in matches:
            team = self.org_map.get_team(team_id)
            if not team:
                continue

            # Find matching sub-teams
            query_lower = query.lower()
            matched_subs = []
            for sub in team.sub_teams:
                sub_matches = sum(1 for kw in sub.keywords if kw in query_lower)
                if sub_matches > 0:
                    matched_subs.append({
                        "sub_team_id": sub.sub_team_id,
                        "name": sub.name,
                        "matches": sub_matches,
                        "focus": sub.agent_focus,
                    })

            matched_subs.sort(key=lambda x: -x["matches"])

            results.append({
                "team_id": team_id,
                "team_name": team.name,
                "full_name": team.full_name,
                "confidence": score,
                "sub_teams": matched_subs,
                "agent_capabilities": team.agent_capabilities,
                "tools_used": team.tools_used,
            })

        return results

    def get_team_for_document(self, document_id: str) -> Optional[dict]:
        """Get the stored classification for a document."""
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM team_classifications WHERE document_id = ?",
            (document_id,),
        ).fetchone()
        conn.close()

        if row is None:
            return None

        return {
            "document_id": row[0],
            "primary_team": row[1],
            "all_matches": json.loads(row[2]) if row[2] else [],
            "is_cross_team": row[3],
            "cross_team_ids": json.loads(row[4]) if row[4] else [],
            "confidence": row[5],
            "method": row[6],
            "classified_at": row[7],
        }

    def correct_classification(
        self,
        document_id: str,
        correct_team_id: str,
        corrected_by: str = "user",
    ) -> None:
        """
        Override/correct a document's team classification.

        Also records the correction for learning.
        """
        # Get original classification
        original = self.get_team_for_document(document_id)
        original_team = original["primary_team"] if original else "unknown"

        # Record correction
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO team_corrections
            (document_id, original_team, corrected_team, corrected_by, corrected_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (document_id, original_team, correct_team_id, corrected_by),
        )

        # Update classification
        team = self.org_map.get_team(correct_team_id)
        conn.execute(
            """
            INSERT OR REPLACE INTO team_classifications
            (document_id, primary_team, all_matches, is_cross_team,
             cross_team_ids, confidence, method, classified_at)
            VALUES (?, ?, ?, FALSE, '[]', 1.0, 'override', CURRENT_TIMESTAMP)
            """,
            (document_id, correct_team_id, json.dumps([{
                "team_id": correct_team_id,
                "team_name": team.name if team else correct_team_id,
                "confidence": 1.0,
                "is_primary": True,
            }])),
        )
        conn.close()

    def get_documents_by_team(self, team_id: str) -> list[dict]:
        """Get all documents classified to a specific team."""
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM team_classifications WHERE primary_team = ?",
            (team_id,),
        ).fetchall()
        conn.close()

        return [
            {
                "document_id": r[0],
                "confidence": r[5],
                "method": r[6],
                "classified_at": r[7],
            }
            for r in rows
        ]

    def get_cross_team_documents(self) -> list[dict]:
        """Get all documents that belong to multiple teams."""
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM team_classifications WHERE is_cross_team = TRUE"
        ).fetchall()
        conn.close()

        return [
            {
                "document_id": r[0],
                "primary_team": r[1],
                "cross_team_ids": json.loads(r[4]) if r[4] else [],
                "confidence": r[5],
            }
            for r in rows
        ]

    def get_team_stats(self) -> dict:
        """Get classification statistics per team."""
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT primary_team, COUNT(*) as cnt, AVG(confidence) as avg_conf
            FROM team_classifications
            GROUP BY primary_team
            ORDER BY COUNT(*) DESC
            """
        ).fetchall()
        conn.close()

        return {
            r[0]: {"document_count": r[1], "avg_confidence": round(r[2] or 0, 3)}
            for r in rows
        }

    def _persist_classification(
        self, document_id: str, result: ClassificationResult
    ) -> None:
        """Store classification result in DuckDB."""
        conn = get_connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO team_classifications
            (document_id, primary_team, all_matches, is_cross_team,
             cross_team_ids, confidence, method, classified_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                document_id,
                result.primary_team_id,
                json.dumps(result.all_team_matches),
                result.is_cross_team,
                json.dumps(result.cross_team_ids),
                result.confidence,
                result.method,
            ),
        )
        conn.close()

    def generate_classification_report(self) -> str:
        """Generate a report of all document classifications."""
        stats = self.get_team_stats()
        cross_team = self.get_cross_team_documents()

        lines = [
            "=" * 60,
            "TEAM CLASSIFICATION REPORT",
            "=" * 60,
            "",
        ]

        total_docs = sum(s["document_count"] for s in stats.values())
        lines.append(f"Total classified documents: {total_docs}")
        lines.append(f"Cross-team documents: {len(cross_team)}")
        lines.append("")

        lines.append("Documents per Team:")
        lines.append("-" * 40)
        for team_id, data in stats.items():
            team = self.org_map.get_team(team_id)
            name = team.name if team else team_id
            full = team.full_name if team else ""
            bar = "█" * min(data["document_count"], 30)
            lines.append(
                f"  {name:8s} ({full[:25]:25s}): "
                f"{data['document_count']:3d} docs  "
                f"conf={data['avg_confidence']:.2f}  {bar}"
            )

        if cross_team:
            lines.append("")
            lines.append("Cross-Team Documents:")
            lines.append("-" * 40)
            for doc in cross_team[:10]:
                cross_names = [cid.upper() for cid in doc["cross_team_ids"]]
                lines.append(
                    f"  {doc['document_id']}: "
                    f"{doc['primary_team'].upper()} + {', '.join(cross_names)}"
                )

        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)
