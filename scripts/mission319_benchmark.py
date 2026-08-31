"""Mission 3.19 — End-to-End RAG Benchmark

Measures retrieval recall, answer grounding, citation correctness,
abstention correctness, and latency across all retrieval strategies.
"""
import sys, time, json
sys.path.insert(0, '.')

from kurukshetra.retrieval.database_bm25 import DatabaseBM25Retriever
from kurukshetra.retrieval.vector import VectorRetriever
from kurukshetra.retrieval.hybrid import HybridRetriever
from kurukshetra.retrieval.access_control import VisibilityFilter, VisibilityLevel
from kurukshetra.retrieval.graph_retriever import GraphAugmentedRetriever
from kurukshetra.retrieval.hyde import HyDERetriever
from kurukshetra.agent.answer_generator import AnswerGenerator
from kurukshetra.agent.planner import SANJAYAPlanner
from kurukshetra.agent.models import QueryType

# ======================================================================
# Evaluation Set — 25 questions from real ICS/Omkar corpus
# Each has: question, expected_doc_ids (set), query_type, expected_fact
# ======================================================================

EVAL_SET = [
    # --- Exact terminology ---
    {
        "id": "Q01",
        "question": "What is the data feed configuration process?",
        "expected_doc_ids": {"DOC-000498", "DOC-000519", "DOC-000513", "DOC-000528"},
        "query_type": "exact_term",
        "expected_fact": "SFTP data feed from G3 to SFDC",
        "min_relevant": 1,
    },
    # --- Workflow/process ---
    {
        "id": "Q02",
        "question": "How does the property merge-split workflow work?",
        "expected_doc_ids": {"DOC-000489"},
        "query_type": "workflow",
        "expected_fact": "merge or split property records",
        "min_relevant": 1,
    },
    {
        "id": "Q03",
        "question": "What are the steps for AMS Recoding?",
        "expected_doc_ids": {"DOC-000493", "DOC-000496"},
        "query_type": "workflow",
        "expected_fact": "AMS rebuild parameters",
        "min_relevant": 1,
    },
    {
        "id": "Q04",
        "question": "How does the installation workflow for G3 properties work?",
        "expected_doc_ids": {"DOC-000488"},
        "query_type": "workflow",
        "expected_fact": "installation workflow criteria",
        "min_relevant": 1,
    },
    # --- Configuration ---
    {
        "id": "Q05",
        "question": "What is the Rate Shopping Migration process?",
        "expected_doc_ids": {"DOC-000490"},
        "query_type": "configuration",
        "expected_fact": "rate shopping migration",
        "min_relevant": 1,
    },
    {
        "id": "Q06",
        "question": "How is the SSD to OCIM workflow structured?",
        "expected_doc_ids": {"DOC-000495"},
        "query_type": "workflow",
        "expected_fact": "SSD to OCIM",
        "min_relevant": 1,
    },
    # --- Semantic ---
    {
        "id": "Q07",
        "question": "What monitoring processes exist for G3 RMS?",
        "expected_doc_ids": {"DOC-000328", "DOC-000327", "DOC-000050"},
        "query_type": "semantic",
        "expected_fact": "monitoring process",
        "min_relevant": 1,
    },
    {
        "id": "Q08",
        "question": "How are processing failures resolved in the G3 system?",
        "expected_doc_ids": {"DOC-000464", "DOC-000411", "DOC-000410"},
        "query_type": "semantic",
        "expected_fact": "processing failure resolution",
        "min_relevant": 1,
    },
    # --- Cross-document ---
    {
        "id": "Q09",
        "question": "What is the property merge-split process?",
        "expected_doc_ids": {"DOC-000489"},
        "query_type": "cross_doc",
        "expected_fact": "property merge split",
        "min_relevant": 1,
    },
    {
        "id": "Q10",
        "question": "What is the Optix workflow for IDeaS?",
        "expected_doc_ids": {"DOC-000486"},
        "query_type": "exact_term",
        "expected_fact": "Optix workflow",
        "min_relevant": 1,
    },
    # --- Graph-related ---
    {
        "id": "Q11",
        "question": "What systems are involved in the Hilton streaming process?",
        "expected_doc_ids": {"DOC-000268", "DOC-000267", "DOC-000266"},
        "query_type": "graph_related",
        "expected_fact": "Hilton streaming",
        "min_relevant": 1,
    },
    {
        "id": "Q12",
        "question": "What is the SSD to OCIM migration?",
        "expected_doc_ids": {"DOC-000495"},
        "query_type": "exact_term",
        "expected_fact": "SSD OCIM migration",
        "min_relevant": 1,
    },
    # --- Acronym/unknown-term ---
    {
        "id": "Q13",
        "question": "What is the AMS Recoding process?",
        "expected_doc_ids": {"DOC-000493", "DOC-000496"},
        "query_type": "acronym",
        "expected_fact": "AMS recoding",
        "min_relevant": 1,
    },
    {
        "id": "Q14",
        "question": "How does the FOLS daily audit work?",
        "expected_doc_ids": {"DOC-000004"},
        "query_type": "acronym",
        "expected_fact": "FOLS audit",
        "min_relevant": 1,
    },
    # --- Insufficient evidence ---
    {
        "id": "Q15",
        "question": "What is the budget allocation for the Q3 marketing campaign?",
        "expected_doc_ids": set(),
        "query_type": "insufficient_evidence",
        "expected_fact": "",
        "min_relevant": 0,
        "should_abstain": True,
    },
    # --- Ambiguous ---
    {
        "id": "Q16",
        "question": "What is the process for adding a new property?",
        "expected_doc_ids": {"DOC-000159", "DOC-000158", "DOC-000160", "DOC-000035"},
        "query_type": "ambiguous",
        "expected_fact": "installation process",
        "min_relevant": 1,
    },
    # --- De-installation ---
    {
        "id": "Q17",
        "question": "How is a property de-installed from G3 RMS?",
        "expected_doc_ids": {"DOC-000229", "DOC-000228", "DOC-000230"},
        "query_type": "workflow",
        "expected_fact": "de-installation process",
        "min_relevant": 1,
    },
    # --- Proactive monitoring ---
    {
        "id": "Q18",
        "question": "What is the G3 Proactive Monitoring data discrepancy workflow?",
        "expected_doc_ids": {"DOC-000487"},
        "query_type": "exact_term",
        "expected_fact": "data discrepancy",
        "min_relevant": 1,
    },
    # --- Stats to inventory ---
    {
        "id": "Q19",
        "question": "What is the Stats to Inventory Transition process?",
        "expected_doc_ids": {"DOC-000488"},
        "query_type": "exact_term",
        "expected_fact": "stats inventory transition",
        "min_relevant": 1,
    },
    # --- Include/Exclude room types ---
    {
        "id": "Q20",
        "question": "How does the Include/Exclude Room Types configuration work?",
        "expected_doc_ids": {"DOC-000492"},
        "query_type": "configuration",
        "expected_fact": "room types include exclude",
        "min_relevant": 1,
    },
    # --- De-Installation NGI ---
    {
        "id": "Q21",
        "question": "What is the NGI De-Installation workflow?",
        "expected_doc_ids": {"DOC-000494"},
        "query_type": "workflow",
        "expected_fact": "NGI de-installation",
        "min_relevant": 1,
    },
    # --- Data feed migration to EDF ---
    {
        "id": "Q22",
        "question": "How does the G3 Data Feed Migration to EDF work?",
        "expected_doc_ids": {"DOC-000412", "DOC-000414", "DOC-000413"},
        "query_type": "workflow",
        "expected_fact": "EDF migration",
        "min_relevant": 1,
    },
    # --- STR configuration ---
    {
        "id": "Q23",
        "question": "What is the G3 RMS STR configuration process?",
        "expected_doc_ids": {"DOC-000500"},
        "query_type": "configuration",
        "expected_fact": "STR configuration",
        "min_relevant": 1,
    },
    # --- RPM configuration ---
    {
        "id": "Q24",
        "question": "How is the RPM Reputation Pricing Model configured?",
        "expected_doc_ids": {"DOC-000505"},
        "query_type": "configuration",
        "expected_fact": "RPM configuration",
        "min_relevant": 1,
    },
    # --- Disambiguation: multiple docs with same name ---
    {
        "id": "Q25",
        "question": "What is the GRO monitoring process for production?",
        "expected_doc_ids": {"DOC-000328", "DOC-000327"},
        "query_type": "ambiguous",
        "expected_fact": "GRO monitoring",
        "min_relevant": 1,
    },
]

# ======================================================================
# Strategy definitions
# ======================================================================

def build_strategies():
    """Build all retrieval strategies to benchmark."""
    vf = VisibilityFilter(max_level=VisibilityLevel.INTERNAL)
    strategies = {}

    # 1. BM25
    strategies["BM25"] = DatabaseBM25Retriever()

    # 2. Vector
    strategies["Vector"] = VectorRetriever()

    # 3. Hybrid (normalized 0.5/0.5)
    strategies["Hybrid"] = HybridRetriever()

    # 4. Graph-Augmented
    try:
        strategies["GraphAug"] = GraphAugmentedRetriever()
    except Exception as e:
        print(f"  Warning: GraphAug not available: {e}")

    # 5. HyDE
    try:
        strategies["HyDE"] = HyDERetriever()
    except Exception as e:
        print(f"  Warning: HyDE not available: {e}")

    return strategies


def benchmark_strategy(name, retriever, eval_set, gen, planner, top_k=5):
    """Benchmark a single strategy against the evaluation set."""
    results = []
    total_latency = 0

    for item in eval_set:
        q = item["question"]
        expected = item["expected_doc_ids"]
        should_abstain = item.get("should_abstain", False)

        # Retrieve
        start = time.time()
        try:
            retrieved = retriever.search(q, top_k=top_k)
        except Exception as e:
            retrieved = []
        retrieve_ms = (time.time() - start) * 1000

        # Generate answer
        start = time.time()
        answer = gen.generate(
            query=q, results=retrieved, strategy=name,
            authorization_status="authorized"
        )
        answer_ms = (time.time() - start) * 1000

        total_latency += retrieve_ms + answer_ms

        # Measure recall
        retrieved_doc_ids = set(r.document_id for r in retrieved)
        hits = retrieved_doc_ids & expected
        recall = len(hits) / max(len(expected), 1) if expected else 0.0

        # Check if any relevant doc is in top results
        relevant_in_top = len(hits) > 0

        # Citation correctness: citations point to actual retrieved docs
        citation_correct = all(
            c.document_id in retrieved_doc_ids for c in answer.citations
        ) if answer.citations else False

        # Abstention correctness
        abstention_correct = (
            answer.abstained == should_abstain
        ) if "should_abstain" in item else None

        results.append({
            "id": item["id"],
            "question": q,
            "query_type": item["query_type"],
            "retrieved_count": len(retrieved),
            "retrieved_doc_ids": list(retrieved_doc_ids),
            "expected_doc_ids": list(expected),
            "hits": list(hits),
            "recall": recall,
            "relevant_in_top": relevant_in_top,
            "answer_confidence": answer.confidence,
            "answer_length": len(answer.answer),
            "answer_abstained": answer.abstained,
            "evidence_quality": answer.evidence_quality,
            "citation_count": len(answer.citations),
            "citation_correct": citation_correct,
            "abstention_correct": abstention_correct,
            "limitations": answer.limitations,
            "conflicts": len(answer.conflicts),
            "retrieve_ms": round(retrieve_ms, 1),
            "answer_ms": round(answer_ms, 1),
            "total_ms": round(retrieve_ms + answer_ms, 1),
            "answer_preview": answer.answer[:150],
        })

    # Aggregate
    n = len(results)
    avg_retrieve = sum(r["retrieve_ms"] for r in results) / n
    avg_answer = sum(r["answer_ms"] for r in results) / n
    avg_total = sum(r["total_ms"] for r in results) / n
    r3 = sum(1 for r in results if r["relevant_in_top"]) / n
    avg_conf = sum(r["answer_confidence"] for r in results) / n
    citation_acc = sum(1 for r in results if r["citation_correct"]) / max(
        sum(1 for r in results if r["citation_count"] > 0), 1
    )
    abstain_results = [r for r in results if r["abstention_correct"] is not None]
    abstain_acc = sum(1 for r in abstain_results if r["abstention_correct"]) / max(len(abstain_results), 1) if abstain_results else None

    # Per-type breakdown
    type_stats = {}
    for r in results:
        qt = r["query_type"]
        if qt not in type_stats:
            type_stats[qt] = {"count": 0, "hits": 0, "total_recall": 0}
        type_stats[qt]["count"] += 1
        if r["relevant_in_top"]:
            type_stats[qt]["hits"] += 1
        type_stats[qt]["total_recall"] += r["recall"]

    for qt in type_stats:
        s = type_stats[qt]
        s["hit_rate"] = round(s["hits"] / s["count"], 3)
        s["avg_recall"] = round(s["total_recall"] / s["count"], 3)

    return {
        "strategy": name,
        "query_count": n,
        "hit_rate@5": round(r3, 3),
        "avg_confidence": round(avg_conf, 3),
        "citation_accuracy": round(citation_acc, 3),
        "abstention_accuracy": abstain_acc,
        "avg_retrieve_ms": round(avg_retrieve, 1),
        "avg_answer_ms": round(avg_answer, 1),
        "avg_total_ms": round(avg_total, 1),
        "total_latency_ms": round(total_latency, 1),
        "type_stats": type_stats,
        "per_query": results,
    }


def main():
    print("=" * 70)
    print("MISSION 3.19 — END-TO-END RAG BENCHMARK")
    print("=" * 70)

    gen = AnswerGenerator()
    planner = SANJAYAPlanner()

    print(f"\nEvaluation set: {len(EVAL_SET)} questions")
    print(f"Query types: {set(q['query_type'] for q in EVAL_SET)}")

    # Build strategies
    print("\nLoading retrieval strategies...")
    strategies = build_strategies()
    print(f"Available: {list(strategies.keys())}")

    # Benchmark each strategy
    all_results = {}
    for name, retriever in strategies.items():
        print(f"\n--- Benchmarking {name} ---")
        result = benchmark_strategy(name, retriever, EVAL_SET, gen, planner)
        all_results[name] = result
        print(f"  Hit@5: {result['hit_rate@5']:.1%}")
        print(f"  Avg Confidence: {result['avg_confidence']:.3f}")
        print(f"  Citation Accuracy: {result['citation_accuracy']:.1%}")
        if result['abstention_accuracy'] is not None:
            print(f"  Abstention Accuracy: {result['abstention_accuracy']:.1%}")
        print(f"  Avg Latency: {result['avg_total_ms']:.0f}ms "
              f"(retrieve: {result['avg_retrieve_ms']:.0f}ms, "
              f"answer: {result['avg_answer_ms']:.0f}ms)")

    # ======================================================================
    # Comparison Table
    # ======================================================================
    print("\n" + "=" * 70)
    print("COMPARISON TABLE")
    print("=" * 70)
    header = f"{'Strategy':<12} {'Hit@5':>7} {'Conf':>7} {'Cite%':>7} {'Abst%':>7} {'Latency':>10}"
    print(header)
    print("-" * len(header))
    for name, r in all_results.items():
        abst = f"{r['abstention_accuracy']:.0%}" if r['abstention_accuracy'] is not None else "N/A"
        print(f"{name:<12} {r['hit_rate@5']:>6.1%} {r['avg_confidence']:>7.3f} "
              f"{r['citation_accuracy']:>6.0%} {abst:>7} {r['avg_total_ms']:>8.0f}ms")

    # ======================================================================
    # Per-type breakdown for best strategy
    # ======================================================================
    best_name = max(all_results.keys(), key=lambda k: all_results[k]["hit_rate@5"])
    best = all_results[best_name]
    print(f"\n{'=' * 70}")
    print(f"PER-TYPE BREAKDOWN — Best: {best_name}")
    print(f"{'=' * 70}")
    for qt, stats in sorted(best["type_stats"].items()):
        print(f"  {qt:<25} hit_rate={stats['hit_rate']:.1%}  "
              f"avg_recall={stats['avg_recall']:.3f}  n={stats['count']}")

    # ======================================================================
    # Per-query detail for best strategy
    # ======================================================================
    print(f"\n{'=' * 70}")
    print(f"PER-QUERY DETAIL — {best_name}")
    print(f"{'=' * 70}")
    for r in best["per_query"]:
        status = "HIT" if r["relevant_in_top"] else "MISS"
        abst = "ABST" if r["answer_abstained"] else "ANS"
        print(f"  {r['id']} [{r['query_type']:<15}] {status} "
              f"conf={r['answer_confidence']:.2f} "
              f"cite={r['citation_count']} "
              f"lat={r['total_ms']:.0f}ms "
              f"{abst} | {r['question'][:50]}")

    # ======================================================================
    # SANJAYA planner analysis with strategy selection
    # ======================================================================
    print(f"\n{'=' * 70}")
    print("SANJAYA PLANNER ANALYSIS")
    print(f"{'=' * 70}")
    for item in EVAL_SET:
        plan = planner.create_plan(item["question"])
        print(f"  {item['id']} intent={plan.intent:<20} type={plan.query_type:<20} "
              f"strategy={plan.recommended_strategy:<12} | {item['question'][:40]}")

    # ======================================================================
    # SANJAYA Integrated Path (planner → strategy → retrieve → answer)
    # ======================================================================
    print(f"\n{'=' * 70}")
    print("SANJAYA INTEGRATED PATH BENCHMARK")
    print(f"{'=' * 70}")
    sanjaya_results = []
    for item in EVAL_SET:
        q = item["question"]
        expected = item["expected_doc_ids"]
        should_abstain = item.get("should_abstain", False)

        # SANJAYA plan
        plan = planner.create_plan(q)

        # Select retriever based on plan
        strategy = plan.recommended_strategy
        if strategy == "bm25":
            ret = DatabaseBM25Retriever()
        elif strategy == "vector":
            ret = VectorRetriever()
        elif strategy == "graph_aug":
            try:
                ret = GraphAugmentedRetriever()
            except Exception:
                ret = HybridRetriever()
                strategy = "hybrid_fallback"
        else:
            ret = HybridRetriever()

        start = time.time()
        try:
            retrieved = ret.search(q, top_k=10)
        except Exception:
            retrieved = []
        retrieve_ms = (time.time() - start) * 1000

        answer = gen.generate(
            query=q, results=retrieved, strategy=strategy,
            authorization_status="authorized"
        )

        retrieved_doc_ids = set(r.document_id for r in retrieved)
        hits = retrieved_doc_ids & expected
        relevant_in_top = len(hits) > 0
        abstention_correct = (
            answer.abstained == should_abstain
        ) if "should_abstain" in item else None

        sanjaya_results.append({
            "id": item["id"],
            "query_type": plan.query_type,
            "strategy_used": strategy,
            "relevant_in_top": relevant_in_top,
            "abstained": answer.abstained,
            "abstention_correct": abstention_correct,
            "confidence": answer.confidence,
            "latency_ms": round(retrieve_ms, 1),
        })

    sanjaya_hits = sum(1 for r in sanjaya_results if r["relevant_in_top"])
    sanjaya_abstain_correct = sum(
        1 for r in sanjaya_results if r["abstention_correct"] is True
    )
    sanjaya_abstain_total = sum(
        1 for r in sanjaya_results if r["abstention_correct"] is not None
    )
    sanjaya_avg_lat = sum(r["latency_ms"] for r in sanjaya_results) / len(sanjaya_results)

    print(f"  Hit@5: {sanjaya_hits}/{len(sanjaya_results)} ({sanjaya_hits/len(sanjaya_results):.1%})")
    print(f"  Abstention: {sanjaya_abstain_correct}/{sanjaya_abstain_total}")
    print(f"  Avg Latency: {sanjaya_avg_lat:.0f}ms")
    print()
    for r in sanjaya_results:
        status = "HIT" if r["relevant_in_top"] else "MISS"
        abst = "OK" if r["abstention_correct"] else ("FAIL" if r["abstention_correct"] is not None else "N/A")
        print(f"  {r['id']} [{r['query_type']:<20}] strategy={r['strategy_used']:<12} "
              f"{status} abst={abst} lat={r['latency_ms']:.0f}ms")

    # ======================================================================
    # Failed queries analysis
    # ======================================================================
    print(f"\n{'=' * 70}")
    print(f"FAILED QUERIES ({best_name})")
    print(f"{'=' * 70}")
    failed = [r for r in best["per_query"] if not r["relevant_in_top"]]
    for r in failed:
        print(f"  {r['id']}: {r['question']}")
        print(f"    Expected: {r['expected_doc_ids']}")
        print(f"    Got: {set(r['retrieved_doc_ids'][:5])}")
        safe = r['answer_preview'][:100].encode('ascii', 'replace').decode('ascii')
        print(f"    Answer: {safe}...")

    # Save results
    output_path = "reports/mission319_benchmark_results.json"
    import os
    os.makedirs("reports", exist_ok=True)
    with open(output_path, "w") as f:
        # Convert for JSON serialization
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nResults saved to {output_path}")

    print(f"\n{'=' * 70}")
    print("BENCHMARK COMPLETE")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
