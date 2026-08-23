"""
Self-Improvement Recommendations
=================================

Analyzes system data and recommends what to build/improve:
- Knowledge gaps (queries with poor results)
- Document quality issues
- Retrieval strategy optimization
- Agent swarm readiness assessment
- Glossary expansion opportunities
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from kurukshetra.registry.database import get_connection


@dataclass(slots=True)
class Recommendation:
    """A self-improvement recommendation."""
    recommendation_id: str
    category: str  # knowledge_gap, document_quality, retrieval_optimization, etc.
    priority: str  # critical, high, medium, low
    title: str
    description: str
    action_items: list[str]
    data_evidence: dict
    created_at: str


class SelfRecommender:
    """
    Analyzes system data to generate improvement recommendations.
    """

    def __init__(self) -> None:
        pass

    def analyze_and_recommend(self) -> list[Recommendation]:
        """
        Run full analysis and generate recommendations.

        Returns prioritized list of improvement recommendations.
        """
        recommendations: list[Recommendation] = []

        # 1. Knowledge gap analysis
        recommendations.extend(self._analyze_knowledge_gaps())

        # 2. Document quality analysis
        recommendations.extend(self._analyze_document_quality())

        # 3. Feedback pattern analysis
        recommendations.extend(self._analyze_feedback_patterns())

        # 4. Retrieval performance analysis
        recommendations.extend(self._analyze_retrieval_performance())

        # 5. Glossary expansion opportunities
        recommendations.extend(self._analyze_glossary_opportunities())

        # Sort by priority
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        recommendations.sort(
            key=lambda r: priority_order.get(r.priority, 4)
        )

        return recommendations

    def _analyze_knowledge_gaps(self) -> list[Recommendation]:
        """Identify queries that return poor results."""
        recommendations = []
        rec_id = 1

        try:
            conn = get_connection()

            # Check for chunks with consistently low scores
            rows = conn.execute(
                """
                SELECT chunk_id, AVG(score) as avg_score, COUNT(*) as usage_count
                FROM chunk_score_history
                GROUP BY chunk_id
                HAVING AVG(score) < 0.3 AND COUNT(*) > 2
                ORDER BY AVG(score) ASC
                LIMIT 10
                """
            ).fetchall()
            conn.close()

            if rows:
                recommendations.append(
                    Recommendation(
                        recommendation_id=f"REC-KG-{rec_id:03d}",
                        category="knowledge_gap",
                        priority="high",
                        title="Low-Relevance Chunks Detected",
                        description=(
                            f"{len(rows)} chunks consistently return with low relevance scores. "
                            "These may need re-chunking, content review, or the source documents "
                            "may need updating."
                        ),
                        action_items=[
                            "Review the identified chunks for content quality",
                            "Consider re-chunking with different granularity",
                            "Check if source documents are still current",
                            "Update or remove outdated content",
                        ],
                        data_evidence={
                            "low_relevance_chunks": len(rows),
                            "worst_score": round(rows[0][1], 3) if rows else 0,
                        },
                        created_at="",
                    )
                )
                rec_id += 1
        except Exception:
            pass

        return recommendations

    def _analyze_document_quality(self) -> list[Recommendation]:
        """Identify documents with quality issues."""
        recommendations = []
        rec_id = 1

        try:
            conn = get_connection()

            # Check for documents with no chunks (failed ingestion)
            rows = conn.execute(
                """
                SELECT d.document_id, d.title
                FROM documents d
                LEFT JOIN chunks c ON d.document_id = c.document_id
                WHERE c.chunk_id IS NULL
                LIMIT 10
                """
            ).fetchall()
            conn.close()

            if rows:
                recommendations.append(
                    Recommendation(
                        recommendation_id=f"REC-DQ-{rec_id:03d}",
                        category="document_quality",
                        priority="high",
                        title="Documents Not Ingested",
                        description=(
                            f"{len(rows)} documents are registered but have no chunks. "
                            "They may have failed during ingestion or extraction."
                        ),
                        action_items=[
                            "Re-run ingestion pipeline for affected documents",
                            "Check PDF extraction logs for errors",
                            "Verify document format is supported",
                        ],
                        data_evidence={"empty_documents": len(rows)},
                        created_at="",
                    )
                )
                rec_id += 1
        except Exception:
            pass

        return recommendations

    def _analyze_feedback_patterns(self) -> list[Recommendation]:
        """Analyze feedback patterns for improvement signals."""
        recommendations = []
        rec_id = 1

        try:
            conn = get_connection()

            # Overall feedback sentiment
            row = conn.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) as positive
                FROM rag_feedback
                """
            ).fetchone()
            conn.close()

            if row and row[0] > 10:
                total, positive = row
                positive = positive or 0
                accuracy = positive / total

                if accuracy < 0.6:
                    recommendations.append(
                        Recommendation(
                            recommendation_id=f"REC-FB-{rec_id:03d}",
                            category="feedback_pattern",
                            priority="critical",
                            title="Low User Satisfaction Detected",
                            description=(
                                f"Only {accuracy:.0%} of user feedback is positive "
                                f"({positive}/{total}). This indicates systemic retrieval "
                                "quality issues that need immediate attention."
                            ),
                            action_items=[
                                "Analyze negative feedback for common patterns",
                                "Review and improve retrieval strategies",
                                "Consider adding more domain-specific knowledge",
                                "Evaluate chunking strategy effectiveness",
                            ],
                            data_evidence={
                                "total_feedback": total,
                                "positive_feedback": positive,
                                "satisfaction_rate": round(accuracy, 3),
                            },
                            created_at="",
                        )
                    )
                    rec_id += 1
        except Exception:
            pass

        return recommendations

    def _analyze_retrieval_performance(self) -> list[Recommendation]:
        """Analyze retrieval strategy performance."""
        recommendations = []
        rec_id = 1

        # This would analyze verification results in production
        # For now, provide a structural recommendation
        recommendations.append(
            Recommendation(
                recommendation_id=f"REC-RP-{rec_id:03d}",
                category="retrieval_optimization",
                priority="medium",
                title="Cross-Strategy Verification Ready",
                description=(
                    "Multiple retrieval strategies are available (BM25, Vector, HyDE, "
                    "Multi-Query, Parent-Child). Enable cross-verification to measure "
                    "which strategy performs best for each query type."
                ),
                action_items=[
                    "Run evaluation harness with all strategies enabled",
                    "Measure precision@3 for each strategy independently",
                    "Optimize strategy weights based on evaluation results",
                    "Consider enabling adaptive weight adjustment",
                ],
                data_evidence={
                    "available_strategies": ["bm25", "vector", "hyde", "multi_query", "parent_child"],
                },
                created_at="",
            )
        )

        return recommendations

    def _analyze_glossary_opportunities(self) -> list[Recommendation]:
        """Identify glossary expansion opportunities."""
        recommendations = []
        rec_id = 1

        try:
            conn = get_connection()
            pending_count = conn.execute(
                "SELECT COUNT(*) FROM unknown_terms WHERE status = 'pending'"
            ).fetchone()[0]
            conn.close()

            if pending_count > 5:
                recommendations.append(
                    Recommendation(
                        recommendation_id=f"REC-GL-{rec_id:03d}",
                        category="glossary_expansion",
                        priority="medium",
                        title="Unknown Terms Awaiting Confirmation",
                        description=(
                            f"{pending_count} unknown terms have been detected but not yet "
                            "confirmed. Adding these to the glossary will improve future "
                            "retrieval and classification accuracy."
                        ),
                        action_items=[
                            "Review pending unknown terms",
                            "Confirm valid terms and provide definitions",
                            "Reject false positives",
                            "Update document metadata with confirmed terms",
                        ],
                        data_evidence={"pending_terms": pending_count},
                        created_at="",
                    )
                )
                rec_id += 1
        except Exception:
            pass

        return recommendations

    def generate_roadmap(self, recommendations: list[Recommendation]) -> str:
        """
        Generate a development roadmap from recommendations.
        """
        lines = [
            "=" * 60,
            "KURUKSHETRA SELF-IMPROVEMENT ROADMAP",
            "=" * 60,
            "",
        ]

        by_category: dict[str, list[Recommendation]] = {}
        for r in recommendations:
            by_category.setdefault(r.category, []).append(r)

        category_display = {
            "knowledge_gap": "📚 Knowledge Gaps",
            "document_quality": "📄 Document Quality",
            "feedback_pattern": "💬 Feedback Patterns",
            "retrieval_optimization": "🔍 Retrieval Optimization",
            "glossary_expansion": "📖 Glossary Expansion",
        }

        for cat, recs in by_category.items():
            display = category_display.get(cat, cat)
            lines.append(f"{display}")
            lines.append("-" * 40)

            for r in recs:
                priority_icon = {
                    "critical": "🔴",
                    "high": "🟠",
                    "medium": "🟡",
                    "low": "🟢",
                }.get(r.priority, "⚪")

                lines.append(f"  {priority_icon} [{r.priority.upper()}] {r.title}")
                lines.append(f"     {r.description}")
                lines.append(f"     Actions:")
                for action in r.action_items:
                    lines.append(f"       • {action}")
                lines.append("")

        if not recommendations:
            lines.append("No recommendations at this time.")
            lines.append("System is performing within expected parameters.")

        lines.append("=" * 60)
        return "\n".join(lines)
