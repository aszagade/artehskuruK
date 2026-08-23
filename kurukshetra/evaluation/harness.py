"""
RAG Evaluation Harness
======================

Measures RAG system quality through:
- Retrieval precision@k
- Answer accuracy against gold standard Q&A pairs
- Confidence calibration
- Knowledge decay detection
- Batch evaluation across document corpus
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from kurukshetra.retrieval.models import RetrievalResult


@dataclass(slots=True)
class EvalQuery:
    """A gold-standard evaluation query with expected results."""
    query: str
    expected_document_ids: list[str]  # Docs that SHOULD appear in results
    expected_keywords: list[str]      # Keywords that SHOULD be in top results
    category: str = "general"         # Classification for category-level analysis
    difficulty: str = "medium"        # easy, medium, hard


@dataclass(slots=True)
class EvalResult:
    """Result of evaluating a single query."""
    query: str
    retrieved_doc_ids: list[str]
    retrieved_texts: list[str]
    scores: list[float]
    expected_doc_ids: list[str]
    hit_at_k: dict[int, bool]         # {1: True, 3: True, 5: False, 10: True}
    precision_at_k: dict[int, float]  # {1: 1.0, 3: 0.67, 5: 0.4}
    keyword_coverage: float           # Fraction of expected keywords found
    latency_ms: float
    category: str


@dataclass
class EvalMetrics:
    """Aggregate evaluation metrics across all queries."""
    total_queries: int = 0
    mean_reciprocal_rank: float = 0.0
    mean_precision_at_1: float = 0.0
    mean_precision_at_3: float = 0.0
    mean_precision_at_5: float = 0.0
    mean_recall_at_5: float = 0.0
    mean_keyword_coverage: float = 0.0
    mean_latency_ms: float = 0.0
    category_scores: dict[str, dict[str, float]] = field(default_factory=dict)
    pass_at_1_rate: float = 0.0
    pass_at_3_rate: float = 0.0
    grade: str = "N/A"  # A/B/C/D/F

    def summary(self) -> str:
        """Return a human-readable summary."""
        lines = [
            "=" * 60,
            "RAG EVALUATION REPORT",
            "=" * 60,
            f"Total Queries    : {self.total_queries}",
            f"Grade            : {self.grade}",
            f"MRR              : {self.mean_reciprocal_rank:.3f}",
            f"Precision@1      : {self.mean_precision_at_1:.3f}",
            f"Precision@3      : {self.mean_precision_at_3:.3f}",
            f"Precision@5      : {self.mean_precision_at_5:.3f}",
            f"Recall@5         : {self.mean_recall_at_5:.3f}",
            f"Keyword Coverage : {self.mean_keyword_coverage:.3f}",
            f"Mean Latency     : {self.mean_latency_ms:.1f} ms",
            f"Pass@1 Rate      : {self.pass_at_1_rate:.1%}",
            f"Pass@3 Rate      : {self.pass_at_3_rate:.1%}",
        ]

        if self.category_scores:
            lines.append("\nCategory Breakdown:")
            for cat, scores in self.category_scores.items():
                lines.append(f"  {cat}: P@3={scores.get('precision@3', 0):.3f}  "
                           f"Keywords={scores.get('keyword_coverage', 0):.3f}")

        lines.append("=" * 60)
        return "\n".join(lines)


class EvaluationHarness:
    """
    Runs evaluation queries against the RAG system and measures quality.

    Usage:
        harness = EvaluationHarness()
        harness.load_gold_set("path/to/eval_queries.json")
        metrics = harness.evaluate(retrieval_fn)
        print(metrics.summary())
    """

    def __init__(self) -> None:
        self.gold_set: list[EvalQuery] = []
        self.results: list[EvalResult] = []

    def load_gold_set(self, path: str | Path) -> None:
        """Load gold-standard evaluation queries from JSON file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Gold set not found: {path}")

        with open(path) as f:
            data = json.load(f)

        self.gold_set = []
        for item in data:
            self.gold_set.append(EvalQuery(
                query=item["query"],
                expected_document_ids=item.get("expected_document_ids", []),
                expected_keywords=item.get("expected_keywords", []),
                category=item.get("category", "general"),
                difficulty=item.get("difficulty", "medium"),
            ))

    def add_query(self, query: EvalQuery) -> None:
        """Add a single evaluation query to the gold set."""
        self.gold_set.append(query)

    def evaluate(
        self,
        retrieval_fn: Callable[[str, int], list[RetrievalResult]],
        max_k: int = 10,
    ) -> EvalMetrics:
        """
        Run all gold-set queries and compute metrics.

        Args:
            retrieval_fn: Function that takes (query, top_k) and returns RetrievalResults
            max_k: Maximum k for precision@k calculations

        Returns:
            EvalMetrics with aggregate scores
        """
        self.results = []

        for eval_query in self.gold_set:
            result = self._evaluate_single(eval_query, retrieval_fn, max_k)
            self.results.append(result)

        return self._compute_aggregate_metrics()

    def _evaluate_single(
        self,
        eval_query: EvalQuery,
        retrieval_fn: Callable[[str, int], list[RetrievalResult]],
        max_k: int,
    ) -> EvalResult:
        """Evaluate a single query."""
        start = time.time()
        results = retrieval_fn(eval_query.query, max_k)
        latency_ms = (time.time() - start) * 1000

        retrieved_ids = [r.document_id for r in results]
        retrieved_texts = [r.text for r in results]
        scores = [r.score for r in results]

        # Hit@k: did any expected doc appear in top-k?
        hit_at_k = {}
        for k in [1, 3, 5, 10]:
            if k > max_k:
                break
            hit_at_k[k] = any(
                doc_id in retrieved_ids[:k]
                for doc_id in eval_query.expected_document_ids
            )

        # Precision@k: fraction of top-k that are relevant
        precision_at_k = {}
        for k in [1, 3, 5]:
            if k > max_k:
                break
            relevant_in_top_k = sum(
                1 for doc_id in retrieved_ids[:k]
                if doc_id in eval_query.expected_document_ids
            )
            precision_at_k[k] = relevant_in_top_k / k

        # Keyword coverage: fraction of expected keywords found in top-5
        all_text = " ".join(retrieved_texts[:5]).lower()
        if eval_query.expected_keywords:
            found = sum(
                1 for kw in eval_query.expected_keywords
                if kw.lower() in all_text
            )
            keyword_coverage = found / len(eval_query.expected_keywords)
        else:
            keyword_coverage = 1.0

        return EvalResult(
            query=eval_query.query,
            retrieved_doc_ids=retrieved_ids,
            retrieved_texts=retrieved_texts,
            scores=scores,
            expected_doc_ids=eval_query.expected_document_ids,
            hit_at_k=hit_at_k,
            precision_at_k=precision_at_k,
            keyword_coverage=keyword_coverage,
            latency_ms=latency_ms,
            category=eval_query.category,
        )

    def _compute_aggregate_metrics(self) -> EvalMetrics:
        """Compute aggregate metrics from individual results."""
        if not self.results:
            return EvalMetrics()

        n = len(self.results)

        # MRR: Reciprocal rank of first relevant result
        mrr_sum = 0.0
        for r in self.results:
            for rank, doc_id in enumerate(r.retrieved_doc_ids, 1):
                if doc_id in r.expected_doc_ids:
                    mrr_sum += 1.0 / rank
                    break
        mean_mrr = mrr_sum / n

        # Precision averages
        p1_sum = sum(r.precision_at_k.get(1, 0) for r in self.results)
        p3_sum = sum(r.precision_at_k.get(3, 0) for r in self.results)
        p5_sum = sum(r.precision_at_k.get(5, 0) for r in self.results)

        # Recall@5: fraction of expected docs found in top 5
        recall_sum = 0.0
        for r in self.results:
            if r.expected_doc_ids:
                found = sum(
                    1 for doc_id in r.retrieved_doc_ids[:5]
                    if doc_id in r.expected_doc_ids
                )
                recall_sum += found / len(r.expected_doc_ids)

        # Keyword coverage average
        kw_sum = sum(r.keyword_coverage for r in self.results)

        # Latency average
        lat_sum = sum(r.latency_ms for r in self.results)

        # Pass rates (at least one expected doc in top-k)
        pass1 = sum(1 for r in self.results if r.hit_at_k.get(1, False))
        pass3 = sum(1 for r in self.results if r.hit_at_k.get(3, False))

        # Category breakdown
        categories: dict[str, list[EvalResult]] = {}
        for r in self.results:
            categories.setdefault(r.category, []).append(r)

        cat_scores = {}
        for cat, cat_results in categories.items():
            cat_n = len(cat_results)
            cat_scores[cat] = {
                "precision@3": sum(
                    r.precision_at_k.get(3, 0) for r in cat_results
                ) / cat_n,
                "keyword_coverage": sum(
                    r.keyword_coverage for r in cat_results
                ) / cat_n,
                "count": cat_n,
            }

        # Grade
        avg_p3 = p3_sum / n
        if avg_p3 >= 0.8:
            grade = "A"
        elif avg_p3 >= 0.6:
            grade = "B"
        elif avg_p3 >= 0.4:
            grade = "C"
        elif avg_p3 >= 0.2:
            grade = "D"
        else:
            grade = "F"

        return EvalMetrics(
            total_queries=n,
            mean_reciprocal_rank=round(mean_mrr, 4),
            mean_precision_at_1=round(p1_sum / n, 4),
            mean_precision_at_3=round(p3_sum / n, 4),
            mean_precision_at_5=round(p5_sum / n, 4),
            mean_recall_at_5=round(recall_sum / n, 4),
            mean_keyword_coverage=round(kw_sum / n, 4),
            mean_latency_ms=round(lat_sum / n, 1),
            category_scores=cat_scores,
            pass_at_1_rate=round(pass1 / n, 4),
            pass_at_3_rate=round(pass3 / n, 4),
            grade=grade,
        )

    def save_results(self, path: str | Path) -> None:
        """Save evaluation results to JSON."""
        path = Path(path)
        data = []
        for r in self.results:
            data.append({
                "query": r.query,
                "retrieved_doc_ids": r.retrieved_doc_ids,
                "expected_doc_ids": r.expected_doc_ids,
                "hit_at_k": r.hit_at_k,
                "precision_at_k": r.precision_at_k,
                "keyword_coverage": r.keyword_coverage,
                "latency_ms": r.latency_ms,
                "category": r.category,
            })

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def load_eval_queries_from_spm_docs(self) -> None:
        """
        Generate baseline evaluation queries from known SPM document topics.
        These are hand-crafted to test core IDeaS G3 RMS knowledge.
        """
        baseline_queries = [
            EvalQuery(
                query="How to handle G3 RMS decision upload failures?",
                expected_document_ids=[],
                expected_keywords=["decision upload", "failure", "G3", "resolution"],
                category="troubleshooting",
                difficulty="easy",
            ),
            EvalQuery(
                query="What is the process for G3 Full Upload?",
                expected_document_ids=[],
                expected_keywords=["full upload", "G3", "process", "procedure"],
                category="process",
                difficulty="easy",
            ),
            EvalQuery(
                query="How to install a new property using FOLS?",
                expected_document_ids=[],
                expected_keywords=["FOLS", "installation", "property", "add"],
                category="installation",
                difficulty="medium",
            ),
            EvalQuery(
                query="Troubleshooting steps for G3 monitoring alerts",
                expected_document_ids=[],
                expected_keywords=["monitoring", "alert", "G3", "troubleshoot"],
                category="troubleshooting",
                difficulty="medium",
            ),
            EvalQuery(
                query="How to resolve CPOptimalPriceToBARStep failures?",
                expected_document_ids=[],
                expected_keywords=["CPOptimalPriceToBAR", "failure", "resolution"],
                category="error_resolution",
                difficulty="hard",
            ),
            EvalQuery(
                query="G3 Opera Agent installation and reinstallation process",
                expected_document_ids=[],
                expected_keywords=["Opera Agent", "installation", "reinstall", "G3"],
                category="installation",
                difficulty="medium",
            ),
            EvalQuery(
                query="How to handle Hilton NGI decision delivery job failures?",
                expected_document_ids=[],
                expected_keywords=["Hilton", "NGI", "decision delivery", "failure"],
                category="troubleshooting",
                difficulty="hard",
            ),
            EvalQuery(
                query="What is the OXI to Agent migration process?",
                expected_document_ids=[],
                expected_keywords=["OXI", "Agent", "migration", "process"],
                category="migration",
                difficulty="medium",
            ),
            EvalQuery(
                query="How to configure continuous pricing for new properties?",
                expected_document_ids=[],
                expected_keywords=["continuous pricing", "configuration", "property", "CP"],
                category="configuration",
                difficulty="medium",
            ),
            EvalQuery(
                query="Rate shopping data not present on BAD/Pricing screen",
                expected_document_ids=[],
                expected_keywords=["rate shopping", "BAD", "pricing", "data", "missing"],
                category="troubleshooting",
                difficulty="hard",
            ),
        ]

        for q in baseline_queries:
            self.gold_set.append(q)
