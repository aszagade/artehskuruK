"""
Knowledge Fabric Evolution
==========================

The ingestion pipeline itself evolves over time:
- A/B test different chunking strategies
- Measure which retrieval technique works best per query type
- Auto-adjust hybrid retrieval weights based on performance
- Evolve scoring system based on real outcomes
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Optional

from kurukshetra.registry.database import get_connection


@dataclass(slots=True)
class StrategyPerformance:
    """Performance metrics for a specific retrieval strategy."""
    strategy_name: str
    avg_score: float
    query_count: int
    feedback_accuracy: float  # From user feedback
    latency_ms: float


@dataclass(slots=True)
class ChunkingExperiment:
    """Record of a chunking strategy experiment."""
    experiment_id: str
    strategy_name: str
    chunk_size: int
    overlap: int
    avg_retrieval_score: float
    query_count: int
    started_at: str
    status: str  # running, completed, failed


class FabricEvolution:
    """
    Tracks and optimizes the Knowledge Fabric over time.
    """

    def __init__(self) -> None:
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        conn = get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS strategy_performance (
                strategy_name TEXT,
                query_date DATE,
                avg_score DOUBLE,
                query_count INTEGER,
                feedback_accuracy DOUBLE,
                latency_ms DOUBLE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chunking_experiments (
                experiment_id TEXT PRIMARY KEY,
                strategy_name TEXT,
                chunk_size INTEGER,
                overlap INTEGER,
                avg_retrieval_score DOUBLE,
                query_count INTEGER,
                started_at TIMESTAMP,
                status TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS weight_history (
                recorded_at TIMESTAMP,
                bm25_weight DOUBLE,
                vector_weight DOUBLE,
                hyde_weight DOUBLE,
                multi_query_weight DOUBLE,
                performance_score DOUBLE
            )
        """)
        conn.close()

    def record_strategy_performance(
        self,
        strategy_name: str,
        avg_score: float,
        query_count: int,
        feedback_accuracy: float,
        latency_ms: float,
    ) -> None:
        """Record performance data for a retrieval strategy."""
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO strategy_performance
            (strategy_name, query_date, avg_score, query_count,
             feedback_accuracy, latency_ms)
            VALUES (?, CURRENT_DATE, ?, ?, ?, ?)
            """,
            (strategy_name, avg_score, query_count, feedback_accuracy, latency_ms),
        )
        conn.close()

    def get_strategy_rankings(self) -> list[StrategyPerformance]:
        """Get strategy performance rankings."""
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT
                strategy_name,
                AVG(avg_score) as avg_score,
                SUM(query_count) as total_queries,
                AVG(feedback_accuracy) as avg_accuracy,
                AVG(latency_ms) as avg_latency
            FROM strategy_performance
            GROUP BY strategy_name
            ORDER BY AVG(avg_score) DESC
            """
        ).fetchall()
        conn.close()

        return [
            StrategyPerformance(
                strategy_name=r[0],
                avg_score=round(r[1] or 0, 3),
                query_count=r[2] or 0,
                feedback_accuracy=round(r[3] or 0, 3),
                latency_ms=round(r[4] or 0, 1),
            )
            for r in rows
        ]

    def suggest_optimal_weights(self) -> dict[str, float]:
        """
        Suggest optimal hybrid retrieval weights based on performance data.

        Uses feedback accuracy and retrieval scores to compute
        strategy importance weights.
        """
        rankings = self.get_strategy_rankings()

        if not rankings:
            return {
                "bm25": 0.25,
                "vector": 0.30,
                "hyde": 0.20,
                "multi_query": 0.15,
                "parent_child": 0.10,
            }

        # Calculate weights based on performance
        total_score = sum(r.avg_score * r.feedback_accuracy for r in rankings)
        if total_score == 0:
            total_score = 1.0

        weights = {}
        for r in rankings:
            weight = (r.avg_score * r.feedback_accuracy) / total_score
            weights[r.strategy_name] = round(max(weight, 0.05), 3)  # Min 5%

        # Ensure weights sum to 1.0
        total_weight = sum(weights.values())
        if total_weight > 0:
            weights = {k: round(v / total_weight, 3) for k, v in weights.items()}

        return weights

    def record_weights(
        self,
        weights: dict[str, float],
        performance_score: float,
    ) -> None:
        """Record a set of weights for historical tracking."""
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO weight_history
            (recorded_at, bm25_weight, vector_weight, hyde_weight,
             multi_query_weight, performance_score)
            VALUES (CURRENT_TIMESTAMP, ?, ?, ?, ?, ?)
            """,
            (
                weights.get("bm25", 0.25),
                weights.get("vector", 0.30),
                weights.get("hyde", 0.20),
                weights.get("multi_query", 0.15),
                performance_score,
            ),
        )
        conn.close()

    def start_chunking_experiment(
        self,
        strategy_name: str,
        chunk_size: int,
        overlap: int,
    ) -> ChunkingExperiment:
        """Start a new chunking experiment."""
        experiment_id = f"EXP-{int(time.time())}"
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        experiment = ChunkingExperiment(
            experiment_id=experiment_id,
            strategy_name=strategy_name,
            chunk_size=chunk_size,
            overlap=overlap,
            avg_retrieval_score=0.0,
            query_count=0,
            started_at=timestamp,
            status="running",
        )

        conn = get_connection()
        conn.execute(
            """
            INSERT INTO chunking_experiments
            (experiment_id, strategy_name, chunk_size, overlap,
             avg_retrieval_score, query_count, started_at, status)
            VALUES (?, ?, ?, ?, 0, 0, ?, 'running')
            """,
            (experiment_id, strategy_name, chunk_size, overlap, timestamp),
        )
        conn.close()

        return experiment

    def update_experiment(
        self,
        experiment_id: str,
        avg_score: float,
        query_count: int,
    ) -> None:
        """Update experiment with new performance data."""
        conn = get_connection()
        conn.execute(
            """
            UPDATE chunking_experiments
            SET avg_retrieval_score = ?, query_count = ?
            WHERE experiment_id = ?
            """,
            (avg_score, query_count, experiment_id),
        )
        conn.close()

    def complete_experiment(self, experiment_id: str) -> None:
        """Mark an experiment as completed."""
        conn = get_connection()
        conn.execute(
            "UPDATE chunking_experiments SET status = 'completed' WHERE experiment_id = ?",
            (experiment_id,),
        )
        conn.close()

    def get_experiment_results(self) -> list[ChunkingExperiment]:
        """Get all experiment results."""
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM chunking_experiments ORDER BY started_at DESC"
        ).fetchall()
        conn.close()

        return [
            ChunkingExperiment(
                experiment_id=r[0],
                strategy_name=r[1],
                chunk_size=r[2],
                overlap=r[3],
                avg_retrieval_score=r[4] or 0.0,
                query_count=r[5] or 0,
                started_at=r[6],
                status=r[7],
            )
            for r in rows
        ]

    def generate_evolution_report(self) -> str:
        """Generate a report of the Knowledge Fabric's evolution."""
        lines = [
            "=" * 60,
            "KNOWLEDGE FABRIC EVOLUTION REPORT",
            "=" * 60,
            "",
        ]

        # Strategy rankings
        rankings = self.get_strategy_rankings()
        if rankings:
            lines.append("📊 Strategy Performance Rankings")
            lines.append("-" * 40)
            for i, r in enumerate(rankings, 1):
                lines.append(
                    f"  {i}. {r.strategy_name}: "
                    f"score={r.avg_score:.3f}  "
                    f"accuracy={r.feedback_accuracy:.3f}  "
                    f"queries={r.query_count}"
                )
            lines.append("")

        # Optimal weights
        weights = self.suggest_optimal_weights()
        lines.append("⚖️ Suggested Optimal Weights")
        lines.append("-" * 40)
        for strategy, weight in sorted(weights.items(), key=lambda x: -x[1]):
            bar = "█" * int(weight * 50)
            lines.append(f"  {strategy:15s} {weight:.3f} {bar}")
        lines.append("")

        # Experiments
        experiments = self.get_experiment_results()
        if experiments:
            lines.append("🧪 Chunking Experiments")
            lines.append("-" * 40)
            for exp in experiments:
                status_icon = "✅" if exp.status == "completed" else "🔄"
                lines.append(
                    f"  {status_icon} {exp.strategy_name} "
                    f"(size={exp.chunk_size}, overlap={exp.overlap}): "
                    f"score={exp.avg_retrieval_score:.3f}"
                )
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)
