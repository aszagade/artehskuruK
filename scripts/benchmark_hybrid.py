"""
Hybrid Retrieval Weight Benchmark
==================================

Tests different BM25/Vector weight combinations and RRF
against the 20-question ICS corpus benchmark.

Key finding from score analysis:
- BM25 scores range 9-11 (raw)
- Vector scores range 0.65-0.70 (cosine)
- Current weights (0.4/0.6) are dominated by BM25 (4.28 vs 0.41)
- Need score normalization before meaningful hybrid fusion
"""

from __future__ import annotations

import sys
import time
from collections import defaultdict

sys.path.insert(0, ".")

from kurukshetra.retrieval.database_bm25 import DatabaseBM25Retriever
from kurukshetra.retrieval.vector import VectorRetriever
from kurukshetra.retrieval.models import RetrievalResult

# Same benchmark as Mission 3.9
QUESTIONS = [
    ("Q01", "What is G3 Data Feed Configuration?", "DOC-000498", "exact"),
    ("Q02", "What is the RPM configuration process?", "DOC-000505", "exact"),
    ("Q03", "What is the Delphi Installation process?", "DOC-000497", "exact"),
    ("Q04", "How to configure Demand360 in G3 RMS?", "DOC-000499", "exact"),
    ("Q05", "How to configure STR in G3 RMS?", "DOC-000500", "exact"),
    ("Q06", "What is G3 RSS Configuration?", "DOC-000501", "acronym"),
    ("Q07", "How does RMS D360 SFDC workflow work?", "DOC-000491", "acronym"),
    ("Q08", "How to handle duplicate group deletion?", "DOC-000502", "workflow"),
    ("Q09", "What is the Property Merge-Split workflow?", "DOC-000489", "workflow"),
    ("Q10", "What is the Rate Shopping Migration workflow?", "DOC-000490", "workflow"),
    ("Q11", "What is the Include/Exclude Room Types workflow?", "DOC-000492", "config"),
    ("Q12", "What is the SSD to OCIM migration?", "DOC-000495", "config"),
    ("Q13", "What is the AMS Recoding process?", "DOC-000493", "process"),
    ("Q14", "What is the De-Installation NGI process?", "DOC-000494", "process"),
    ("Q15", "What is Synthetic History to Standard Switch?", "DOC-000506", "process"),
    ("Q16", "What is the ClientSpecific MS Recoding Process?", "DOC-000496", "process"),
    ("Q17", "What is G3 Proactive Monitoring for Data Discrepancy?", "DOC-000487", "cross-doc"),
    ("Q18", "What is the G3 Stats to Inventory Transition?", "DOC-000488", "cross-doc"),
    ("Q19", "What is the Price Grid to Daily Continuous Pricing workflow?", "DOC-000504", "semantic"),
    ("Q20", "What are the Pricing Issues procedures?", "DOC-000507", "semantic"),
]


def normalize_scores(results: list[RetrievalResult]) -> list[RetrievalResult]:
    """Min-max normalize scores to 0-1 range."""
    if not results:
        return results
    scores = [r.score for r in results]
    min_s, max_s = min(scores), max(scores)
    span = max_s - min_s
    if span == 0:
        return results
    for r in results:
        r.score = (r.score - min_s) / span
    return results


def hybrid_weighted(
    bm25_results: list[RetrievalResult],
    vec_results: list[RetrievalResult],
    bm25_weight: float,
    vec_weight: float,
    normalize: bool = True,
    top_k: int = 5,
) -> list[RetrievalResult]:
    """Combine BM25 and Vector results with given weights."""
    if normalize:
        bm25_results = normalize_scores([RetrievalResult(r.chunk_id, r.document_id, r.score, r.text, r.metadata.copy()) for r in bm25_results])
        vec_results = normalize_scores([RetrievalResult(r.chunk_id, r.document_id, r.score, r.text, r.metadata.copy()) for r in vec_results])

    scores = {}
    for r in bm25_results:
        scores[r.chunk_id] = {"result": r, "score": r.score * bm25_weight}
    for r in vec_results:
        if r.chunk_id in scores:
            scores[r.chunk_id]["score"] += r.score * vec_weight
        else:
            scores[r.chunk_id] = {"result": r, "score": r.score * vec_weight}

    merged = []
    for item in scores.values():
        result = item["result"]
        result.score = item["score"]
        merged.append(result)

    return sorted(merged, key=lambda x: x.score, reverse=True)[:top_k]


def rrf_fusion(
    bm25_results: list[RetrievalResult],
    vec_results: list[RetrievalResult],
    k: int = 60,
    top_k: int = 5,
) -> list[RetrievalResult]:
    """Reciprocal Rank Fusion."""
    scores = defaultdict(float)

    for rank, r in enumerate(bm25_results):
        scores[r.chunk_id] += 1.0 / (k + rank + 1)
        if r.chunk_id not in scores:
            scores[r.chunk_id] = 0  # ensure entry exists

    for rank, r in enumerate(vec_results):
        scores[r.chunk_id] += 1.0 / (k + rank + 1)

    # Build result map
    result_map = {}
    for r in bm25_results:
        result_map[r.chunk_id] = r
    for r in vec_results:
        if r.chunk_id not in result_map:
            result_map[r.chunk_id] = r

    merged = []
    for cid, score in scores.items():
        if cid in result_map:
            result = result_map[cid]
            result.score = score
            merged.append(result)

    return sorted(merged, key=lambda x: x.score, reverse=True)[:top_k]


def evaluate(results: list[RetrievalResult], expected: str) -> tuple[bool, bool, int]:
    """Return (hit3, hit5, rank)."""
    doc_ids = [r.document_id for r in results]
    hit3 = expected in doc_ids[:3]
    hit5 = expected in doc_ids[:5]
    rank = doc_ids.index(expected) + 1 if expected in doc_ids else 0
    return hit3, hit5, rank


def run_benchmark(name: str, strategy_fn, questions: list) -> dict:
    """Run benchmark for one strategy."""
    h3 = 0; h5 = 0; mrr = 0.0; lats = []
    per_query = []

    for qid, query, expected, qtype in questions:
        t0 = time.time()
        results = strategy_fn(query)
        lat = (time.time() - t0) * 1000
        lats.append(lat)

        hit3, hit5, rank = evaluate(results, expected)
        if hit3: h3 += 1
        if hit5: h5 += 1
        if rank > 0: mrr += 1.0 / rank
        per_query.append((qid, qtype, hit3, rank))

    n = len(questions)
    return {
        "name": name,
        "h3": h3, "h5": h5,
        "mrr": mrr / n,
        "avg_lat": sum(lats) / len(lats) if lats else 0,
        "per_query": per_query,
    }


def main() -> None:
    print("=" * 70)
    print("HYBRID RETRIEVAL WEIGHT BENCHMARK")
    print("=" * 70)

    print("Loading retrievers...")
    bm25 = DatabaseBM25Retriever()
    vec = VectorRetriever()

    # Pre-fetch BM25 and Vector results for all queries
    print("Pre-fetching BM25 and Vector results...")
    bm25_cache = {}
    vec_cache = {}
    for qid, query, _, _ in QUESTIONS:
        bm25_cache[query] = bm25.search(query, top_k=10)
        vec_cache[query] = vec.search(query, top_k=10)

    n = len(QUESTIONS)

    # Define strategies
    strategies = {}

    # 1. BM25 only
    strategies["BM25"] = lambda q: bm25_cache[q][:5]

    # 2. Vector only
    strategies["Vector"] = lambda q: vec_cache[q][:5]

    # 3. Current Hybrid (unnormalized 0.4/0.6)
    strategies["Hybrid(0.4/0.6)"] = lambda q: hybrid_weighted(bm25_cache[q], vec_cache[q], 0.4, 0.6, normalize=False)

    # 4. Normalized Hybrid variants
    for bw, vw in [(0.5, 0.5), (0.3, 0.7), (0.2, 0.8), (0.1, 0.9), (0.0, 1.0)]:
        label = f"Norm({bw}/{vw})"
        strategies[label] = lambda q, bw=bw, vw=vw: hybrid_weighted(bm25_cache[q], vec_cache[q], bw, vw, normalize=True)

    # 5. RRF
    strategies["RRF(k=60)"] = lambda q: rrf_fusion(bm25_cache[q], vec_cache[q], k=60)

    # Run all benchmarks
    print(f"\nBenchmarking {len(strategies)} strategies on {n} questions...\n")
    results = {}
    for name, fn in strategies.items():
        results[name] = run_benchmark(name, fn, QUESTIONS)

    # Print comparison table
    print("=" * 90)
    print(f"{'Strategy':25s} {'R@3':>8s} {'R@5':>8s} {'MRR':>8s} {'Avg Lat':>10s}")
    print("-" * 90)
    for name in strategies:
        r = results[name]
        print(f"{r['name']:25s} {r['h3']:2d}/{n}={r['h3']/n*100:5.1f}% {r['h5']:2d}/{n}={r['h5']/n*100:5.1f}% {r['mrr']:.3f} {r['avg_lat']:8.0f}ms")

    # Per-query winner analysis
    print("\n" + "=" * 90)
    print("PER-QUERY WINNER (among strategies that hit)")
    print("=" * 90)
    print(f"{'QID':5s} {'Type':12s} ", end="")
    for name in ["BM25", "Vector", "Norm(0.5/0.5)", "Norm(0.3/0.7)", "Norm(0.2/0.8)", "RRF(k=60)"]:
        print(f"{name[:10]:11s}", end="")
    print("Best")
    print("-" * 90)

    best_counts = defaultdict(int)
    for i, (qid, _, _, qtype) in enumerate(QUESTIONS):
        print(f"{qid:5s} {qtype:12s} ", end="")
        hits = []
        for name in ["BM25", "Vector", "Norm(0.5/0.5)", "Norm(0.3/0.7)", "Norm(0.2/0.8)", "RRF(k=60)"]:
            hit = results[name]["per_query"][i][2]
            rank = results[name]["per_query"][i][3]
            mark = f"r{rank}" if hit else "  -"
            print(f"{mark:11s}", end="")
            if hit:
                hits.append((name, rank))

        if not hits:
            best = "None"
        elif len(hits) == 1:
            best = hits[0][0]
        else:
            hits.sort(key=lambda x: x[1])
            best = hits[0][0] if hits[0][1] < hits[1][1] else "Tie"
        best_counts[best] += 1
        print(best)

    print("\nBest-strategy counts:")
    for s, c in sorted(best_counts.items(), key=lambda x: -x[1]):
        print(f"  {s:20s}: {c:2d}/{n}")

    # Key insight
    print("\n" + "=" * 90)
    print("KEY FINDING")
    print("=" * 90)
    print("""
The current HybridRetriever has a FUNDAMENTAL BUG:

  BM25 scores range 9-11 (raw BM25)
  Vector scores range 0.65-0.70 (cosine similarity)

  Current weights: BM25 * 0.4 + Vector * 0.6
  BM25 contribution: 9-11 * 0.4 = 3.6-4.4
  Vector contribution: 0.65-0.70 * 0.6 = 0.39-0.42

  BM25 DOMINATES by 10x even with 0.4 weight.

The fix is score normalization (min-max to 0-1) before fusion.
With normalization, the weights become meaningful.
""")


if __name__ == "__main__":
    main()
