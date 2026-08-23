"""
Cross-Strategy Scoring & Verification
======================================

Runs multiple retrieval strategies in parallel and cross-checks results.
If BM25, Vector, HyDE, Multi-Query, and Parent-Child all agree → HIGH confidence.
If they disagree → flag for review, lower confidence.

Uses Bayesian fusion of scores across strategies.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from .models import RetrievalResult


@dataclass(slots=True)
class CrossVerifiedResult:
    """A retrieval result that has been cross-verified across strategies."""
    chunk_id: str
    document_id: str
    final_score: float
    text: str
    strategy_scores: dict[str, float]   # strategy_name -> score
    agreeing_strategies: int            # How many strategies returned this chunk
    total_strategies: int
    confidence: float                   # Cross-verification confidence (0-1)
    metadata: dict = field(default_factory=dict)


@dataclass
class CrossVerificationReport:
    """Full report of cross-verification across strategies."""
    results: list[CrossVerifiedResult]
    strategy_agreement: float   # Average agreement between strategies
    total_unique_chunks: int    # Unique chunks found across all strategies
    strategy_counts: dict[str, int]  # How many chunks each strategy found


class CrossVerifier:
    """
    Cross-verifies retrieval results across multiple strategies.

    Merges results using Bayesian-inspired fusion:
    - Each strategy provides scores for chunks
    - Chunks found by more strategies get higher confidence
    - Final score = weighted average of strategy scores × agreement boost
    """

    # Default weights for each retrieval strategy
    DEFAULT_WEIGHTS: dict[str, float] = {
        "bm25": 0.25,
        "vector": 0.30,
        "hyde": 0.20,
        "multi_query": 0.15,
        "parent_child": 0.10,
    }

    def __init__(self, strategy_weights: Optional[dict[str, float]] = None) -> None:
        self.weights = strategy_weights or self.DEFAULT_WEIGHTS.copy()

    def verify(
        self,
        strategy_results: dict[str, list[RetrievalResult]],
        top_k: int = 5,
    ) -> CrossVerificationReport:
        """
        Cross-verify results from multiple retrieval strategies.

        Args:
            strategy_results: {strategy_name: [RetrievalResult, ...]}
            top_k: Number of final results to return

        Returns:
            CrossVerificationReport with cross-verified results
        """
        # Collect all unique chunks and their strategy scores
        chunk_data: dict[str, dict] = defaultdict(lambda: {
            "strategy_scores": {},
            "text": "",
            "document_id": "",
        })

        strategy_counts: dict[str, int] = {}

        for strategy_name, results in strategy_results.items():
            strategy_counts[strategy_name] = len(results)
            weight = self.weights.get(strategy_name, 0.2)

            for result in results:
                cid = result.chunk_id
                chunk_data[cid]["strategy_scores"][strategy_name] = result.score * weight
                chunk_data[cid]["text"] = result.text
                chunk_data[cid]["document_id"] = result.document_id

        total_strategies = len(strategy_results)
        if total_strategies == 0:
            return CrossVerificationReport(
                results=[],
                strategy_agreement=0.0,
                total_unique_chunks=0,
                strategy_counts={},
            )

        # Calculate cross-verified scores
        verified_results: list[CrossVerifiedResult] = []

        for cid, data in chunk_data.items():
            strat_scores = data["strategy_scores"]
            agreeing = len(strat_scores)

            # Weighted average score from strategies that found this chunk
            if strat_scores:
                weighted_sum = sum(strat_scores.values())
                # Apply weight normalization
                total_weight = sum(
                    self.weights.get(s, 0.2) for s in strat_scores
                )
                base_score = weighted_sum / max(total_weight, 0.01)
            else:
                base_score = 0.0

            # Agreement boost: chunks found by more strategies are more reliable
            agreement_ratio = agreeing / max(total_strategies, 1)
            agreement_boost = 0.5 + 0.5 * agreement_ratio  # 0.5 to 1.0

            # Confidence: based on agreement and number of strategies
            if agreeing >= 4:
                confidence = 0.95
            elif agreeing >= 3:
                confidence = 0.85
            elif agreeing >= 2:
                confidence = 0.70
            elif agreeing == 1:
                confidence = 0.50
            else:
                confidence = 0.0

            final_score = base_score * agreement_boost

            verified_results.append(
                CrossVerifiedResult(
                    chunk_id=cid,
                    document_id=data["document_id"],
                    final_score=final_score,
                    text=data["text"],
                    strategy_scores=strat_scores,
                    agreeing_strategies=agreeing,
                    total_strategies=total_strategies,
                    confidence=confidence,
                    metadata={
                        "agreement_ratio": agreement_ratio,
                        "agreement_boost": agreement_boost,
                    },
                )
            )

        # Sort by final score
        verified_results.sort(key=lambda x: x.final_score, reverse=True)

        # Calculate overall strategy agreement
        if verified_results:
            avg_agreement = sum(
                r.agreeing_strategies / r.total_strategies
                for r in verified_results
            ) / len(verified_results)
        else:
            avg_agreement = 0.0

        return CrossVerificationReport(
            results=verified_results[:top_k],
            strategy_agreement=round(avg_agreement, 3),
            total_unique_chunks=len(chunk_data),
            strategy_counts=strategy_counts,
        )

    def merge_to_retrieval_results(
        self, report: CrossVerificationReport
    ) -> list[RetrievalResult]:
        """Convert CrossVerificationReport back to standard RetrievalResult list."""
        return [
            RetrievalResult(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                score=r.final_score,
                text=r.text,
                metadata={
                    "strategy": "cross_verified",
                    "confidence": r.confidence,
                    "agreeing_strategies": r.agreeing_strategies,
                    "total_strategies": r.total_strategies,
                    "strategy_scores": r.strategy_scores,
                },
            )
            for r in report.results
        ]
