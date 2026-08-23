"""
Pattern Discovery Engine
========================

Analyzes system data to discover:
- Query pattern clusters (common workflows)
- Emerging issues (spike in failure-related queries)
- Knowledge gaps (frequent queries with poor answers)
- Terminology drift (new terms appearing over time)
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional

from kurukshetra.registry.database import get_connection


@dataclass(slots=True)
class QueryCluster:
    """A cluster of similar queries."""
    cluster_id: str
    topic: str
    query_count: int
    example_queries: list[str]
    avg_relevance_score: float
    trend: str  # rising, stable, declining


@dataclass(slots=True)
class EmergingIssue:
    """An emerging issue detected from query patterns."""
    issue_id: str
    topic: str
    mention_count: int
    time_window: str
    severity: str  # critical, warning, info
    example_queries: list[str]


@dataclass(slots=True)
class KnowledgeGap:
    """A knowledge gap detected from query patterns."""
    gap_id: str
    topic: str
    query_count: int
    avg_score: float
    suggestion: str


@dataclass(slots=True)
class DiscoveryReport:
    """Full pattern discovery report."""
    query_clusters: list[QueryCluster]
    emerging_issues: list[EmergingIssue]
    knowledge_gaps: list[KnowledgeGap]
    terminology_drift: list[dict]
    total_queries_analyzed: int


# Topic keywords for clustering
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "installation": ["install", "setup", "add property", "new property", "reinstall"],
    "troubleshooting": ["error", "failure", "issue", "problem", "troubleshoot", "resolve"],
    "monitoring": ["monitor", "alert", "notification", "exception", "job status"],
    "decision_upload": ["decision upload", "du", "full upload", "first decision", "catchup"],
    "migration": ["migration", "migrate", "switch", "transition", "move"],
    "configuration": ["config", "setting", "parameter", "activation", "enable"],
    "reporting": ["report", "email", "delivery", "scheduled", "export"],
    "data_flow": ["data flow", "extract", "data feed", "pull", "receive"],
}


class PatternDiscovery:
    """
    Discovers patterns in system usage data.
    """

    def __init__(self) -> None:
        pass

    def full_discovery(self) -> DiscoveryReport:
        """Run complete pattern discovery analysis."""
        clusters = self.discover_query_clusters()
        issues = self.detect_emerging_issues()
        gaps = self.detect_knowledge_gaps()
        drift = self.detect_terminology_drift()
        total = self._count_total_queries()

        return DiscoveryReport(
            query_clusters=clusters,
            emerging_issues=issues,
            knowledge_gaps=gaps,
            terminology_drift=drift,
            total_queries_analyzed=total,
        )

    def discover_query_clusters(self) -> list[QueryCluster]:
        """
        Cluster queries by topic to find common workflows.
        """
        try:
            conn = get_connection()
            rows = conn.execute(
                "SELECT query, score FROM chunk_score_history ORDER BY created_at DESC LIMIT 500"
            ).fetchall()
            conn.close()
        except Exception:
            return []

        if not rows:
            return []

        # Cluster by topic keywords
        topic_queries: dict[str, list[tuple[str, float]]] = defaultdict(list)

        for query, score in rows:
            query_lower = query.lower()
            for topic, keywords in TOPIC_KEYWORDS.items():
                if any(kw in query_lower for kw in keywords):
                    topic_queries[topic].append((query, score or 0.0))

        clusters = []
        for topic, queries in topic_queries.items():
            if len(queries) < 2:
                continue

            avg_score = sum(s for _, s in queries) / len(queries)
            examples = list(set(q for q, _ in queries))[:5]

            clusters.append(
                QueryCluster(
                    cluster_id=f"CL-{topic.upper()}",
                    topic=topic,
                    query_count=len(queries),
                    example_queries=examples,
                    avg_relevance_score=round(avg_score, 3),
                    trend="stable",  # Would need historical data for trend
                )
            )

        clusters.sort(key=lambda c: c.query_count, reverse=True)
        return clusters

    def detect_emerging_issues(self) -> list[EmergingIssue]:
        """
        Detect emerging issues from failure/error-related query spikes.
        """
        try:
            conn = get_connection()
            rows = conn.execute(
                """
                SELECT query, COUNT(*) as cnt
                FROM chunk_score_history
                WHERE is_correct = FALSE
                GROUP BY query
                HAVING COUNT(*) >= 2
                ORDER BY COUNT(*) DESC
                LIMIT 20
                """
            ).fetchall()
            conn.close()
        except Exception:
            return []

        issues = []
        for query, count in rows:
            # Classify severity
            if count >= 5:
                severity = "critical"
            elif count >= 3:
                severity = "warning"
            else:
                severity = "info"

            # Extract topic
            topic = "unknown"
            query_lower = query.lower()
            for topic_name, keywords in TOPIC_KEYWORDS.items():
                if any(kw in query_lower for kw in keywords):
                    topic = topic_name
                    break

            issues.append(
                EmergingIssue(
                    issue_id=f"EI-{len(issues)+1:03d}",
                    topic=topic,
                    mention_count=count,
                    time_window="all-time",
                    severity=severity,
                    example_queries=[query],
                )
            )

        return issues

    def detect_knowledge_gaps(self) -> list[KnowledgeGap]:
        """
        Detect knowledge gaps: queries with consistently low relevance scores.
        """
        try:
            conn = get_connection()
            rows = conn.execute(
                """
                SELECT query, AVG(score) as avg_score, COUNT(*) as cnt
                FROM chunk_score_history
                GROUP BY query
                HAVING AVG(score) < 0.3 AND COUNT(*) >= 2
                ORDER BY AVG(score) ASC
                LIMIT 20
                """
            ).fetchall()
            conn.close()
        except Exception:
            return []

        gaps = []
        for query, avg_score, count in rows:
            # Determine suggestion
            if avg_score < 0.1:
                suggestion = f"Critical gap: Very low relevance for '{query}'. Consider ingesting new documents."
            elif avg_score < 0.2:
                suggestion = f"Low relevance for '{query}'. Review existing documents for completeness."
            else:
                suggestion = f"Moderate gap for '{query}'. Consider improving chunking or adding context."

            gaps.append(
                KnowledgeGap(
                    gap_id=f"KG-{len(gaps)+1:03d}",
                    topic=query[:50],
                    query_count=count,
                    avg_score=round(avg_score, 3),
                    suggestion=suggestion,
                )
            )

        return gaps

    def detect_terminology_drift(self) -> list[dict]:
        """
        Detect new terms appearing in recent queries that weren't
        present in older queries.
        """
        try:
            conn = get_connection()

            # Recent queries (last 50)
            recent = conn.execute(
                "SELECT query FROM chunk_score_history ORDER BY created_at DESC LIMIT 50"
            ).fetchall()

            # Older queries (before last 50)
            older = conn.execute(
                "SELECT query FROM chunk_score_history ORDER BY created_at DESC LIMIT 500 OFFSET 50"
            ).fetchall()

            conn.close()
        except Exception:
            return []

        if not recent or not older:
            return []

        # Extract terms
        recent_terms = Counter()
        older_terms = Counter()

        for (query,) in recent:
            words = re.findall(r"\b[A-Za-z]{4,}\b", query)
            for w in words:
                recent_terms[w.lower()] += 1

        for (query,) in older:
            words = re.findall(r"\b[A-Za-z]{4,}\b", query)
            for w in words:
                older_terms[w.lower()] += 1

        # Find new terms (in recent but not in older)
        drift = []
        for term, count in recent_terms.most_common(20):
            if term not in older_terms and count >= 2:
                drift.append({
                    "term": term,
                    "recent_count": count,
                    "status": "new",
                })

        return drift[:10]

    def _count_total_queries(self) -> int:
        """Count total queries in history."""
        try:
            conn = get_connection()
            count = conn.execute(
                "SELECT COUNT(*) FROM chunk_score_history"
            ).fetchone()[0]
            conn.close()
            return count
        except Exception:
            return 0

    def generate_report(self, report: DiscoveryReport) -> str:
        """Generate a human-readable discovery report."""
        lines = [
            "=" * 60,
            "PATTERN DISCOVERY REPORT",
            "=" * 60,
            f"Total queries analyzed: {report.total_queries_analyzed}",
            "",
        ]

        if report.query_clusters:
            lines.append("📊 Query Clusters")
            lines.append("-" * 40)
            for c in report.query_clusters:
                lines.append(f"  {c.topic}: {c.query_count} queries (avg score: {c.avg_relevance_score:.3f})")
                for q in c.example_queries[:2]:
                    lines.append(f"    - {q[:60]}")
            lines.append("")

        if report.emerging_issues:
            lines.append("🚨 Emerging Issues")
            lines.append("-" * 40)
            for issue in report.emerging_issues:
                severity_icon = {"critical": "🔴", "warning": "🟡", "info": "🟢"}.get(issue.severity, "⚪")
                lines.append(f"  {severity_icon} {issue.topic}: {issue.mention_count} failures")
            lines.append("")

        if report.knowledge_gaps:
            lines.append("📚 Knowledge Gaps")
            lines.append("-" * 40)
            for gap in report.knowledge_gaps[:5]:
                lines.append(f"  • {gap.suggestion}")
            lines.append("")

        if report.terminology_drift:
            lines.append("🔤 Terminology Drift")
            lines.append("-" * 40)
            for drift in report.terminology_drift[:5]:
                lines.append(f"  • New term: '{drift['term']}' (seen {drift['recent_count']} times)")
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)
