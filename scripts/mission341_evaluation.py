"""
Mission 3.41 Evaluation Script
==============================

Comprehensive evaluation of SANJAYA's multi-document reasoning capabilities.

Categories:
1. Single-document factual
2. Cross-document synthesis
3. Cross-team reasoning
4. Workflow/procedural
5. Configuration
6. Mention-vs-answer traps
7. Insufficient evidence (should abstain)
8. Citation correctness
"""
import sys
import io
import os
import time
import json

os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')

from kurukshetra.retrieval.hybrid import HybridRetriever
from kurukshetra.retrieval.access_control import VisibilityFilter, VisibilityLevel
from kurukshetra.agent.orchestrator import AgenticSANJAYA
from kurukshetra.agent.answer_generator import AnswerGenerator

# ── Evaluation Set ──────────────────────────────────────────

EVALUATION_SET = [
    # ── Category 1: Single-document factual ──────────────
    {
        "id": "E01",
        "category": "single_doc",
        "question": "What is G3 Data Feed Configuration?",
        "expected": "answer",
        "expected_keywords": ["data feed", "configuration", "g3"],
        "min_source_docs": 1,
        "description": "Single-document factual question about G3 Data Feed",
    },
    {
        "id": "E02",
        "category": "single_doc",
        "question": "What is the process for AMS Recoding?",
        "expected": "answer",
        "expected_keywords": ["ams", "recoding", "sfdc"],
        "min_source_docs": 1,
        "description": "Workflow question about AMS Recoding",
    },
    {
        "id": "E03",
        "category": "single_doc",
        "question": "What is Duplicate Group Deletion?",
        "expected": "answer",
        "expected_keywords": ["duplicate", "group", "deletion"],
        "min_source_docs": 1,
        "description": "Process question about duplicate handling",
    },

    # ── Category 2: Cross-document synthesis ─────────────
    {
        "id": "E04",
        "category": "cross_doc",
        "question": "What teams are involved with G3?",
        "expected": "answer",
        "expected_keywords": ["team"],
        "min_source_docs": 2,
        "description": "Requires synthesizing team info from multiple G3 documents across ICS, SPM, IT, ROA",
    },
    {
        "id": "E05",
        "category": "cross_doc",
        "question": "What are the different G3 installation processes?",
        "expected": "answer",
        "expected_keywords": ["install", "property", "process"],
        "min_source_docs": 2,
        "description": "Requires combining add-property and de-install processes",
    },
    {
        "id": "E06",
        "category": "cross_doc",
        "question": "How does G3 RMS connect to OHIP?",
        "expected": "answer",
        "expected_keywords": ["ohip", "rms", "integration", "connection"],
        "min_source_docs": 2,
        "description": "Requires combining OHIP installation and RMS configuration docs",
    },

    # ── Category 3: Cross-team reasoning ─────────────────
    {
        "id": "E07",
        "category": "cross_team",
        "question": "What does ICS handle in the G3 ecosystem?",
        "expected": "answer",
        "expected_keywords": ["ics", "installation", "configuration", "support"],
        "min_source_docs": 2,
        "description": "ICS team's role across multiple G3 documents",
    },
    {
        "id": "E08",
        "category": "cross_team",
        "question": "What does SPM handle for G3?",
        "expected": "answer",
        "expected_keywords": ["spm", "g3"],
        "min_source_docs": 2,
        "description": "SPM team's role across G3 documents",
    },
    {
        "id": "E09",
        "category": "cross_team",
        "question": "What pricing and forecasting capabilities does IDeaS provide?",
        "expected": "answer",
        "expected_keywords": ["pricing", "forecast", "optimization"],
        "min_source_docs": 2,
        "description": "Pricing capabilities from IT and ROA documents",
    },

    # ── Category 4: Workflow/procedural ──────────────────
    {
        "id": "E10",
        "category": "workflow",
        "question": "How does Rate Shopping Migration work?",
        "expected": "answer",
        "expected_keywords": ["rate", "shopping", "migration"],
        "min_source_docs": 1,
        "description": "Process documentation for rate shopping",
    },
    {
        "id": "E11",
        "category": "workflow",
        "question": "What is the Agent to Agent Migration process?",
        "expected": "answer",
        "expected_keywords": ["agent", "migration"],
        "min_source_docs": 1,
        "description": "ICS migration process documentation",
    },
    {
        "id": "E12",
        "category": "workflow",
        "question": "How do you add a new property to G3?",
        "expected": "answer",
        "expected_keywords": ["add", "property", "installation"],
        "min_source_docs": 1,
        "description": "G3 property addition process",
    },

    # ── Category 5: Configuration ────────────────────────
    {
        "id": "E13",
        "category": "configuration",
        "question": "What is the G3 GA Update Group Evaluation Window?",
        "expected": "answer",
        "expected_keywords": ["group", "evaluation", "window"],
        "min_source_docs": 1,
        "description": "G3 group evaluation configuration",
    },
    {
        "id": "E14",
        "category": "configuration",
        "question": "What is Agile Rates configuration?",
        "expected": "answer",
        "expected_keywords": ["agile", "rates", "configuration"],
        "min_source_docs": 1,
        "description": "Agile rates setup process",
    },

    # ── Category 6: Mention-vs-answer traps ──────────────
    {
        "id": "E15",
        "category": "mva_trap",
        "question": "How many employees does IDeaS have?",
        "expected": "abstain",
        "expected_keywords": [],
        "min_source_docs": 0,
        "description": "HR docs mention 'employees' but don't give headcount — should abstain",
    },
    {
        "id": "E16",
        "category": "mva_trap",
        "question": "What is the company annual revenue?",
        "expected": "abstain",
        "expected_keywords": [],
        "min_source_docs": 0,
        "description": "No revenue data in knowledge base — should abstain",
    },
    {
        "id": "E17",
        "category": "mva_trap",
        "question": "What is the salary range for G3 engineers?",
        "expected": "abstain",
        "expected_keywords": [],
        "min_source_docs": 0,
        "description": "Salary info not in knowledge base — should abstain",
    },

    # ── Category 7: Insufficient evidence ────────────────
    {
        "id": "E18",
        "category": "insufficient",
        "question": "What is quantum computing?",
        "expected": "abstain",
        "expected_keywords": [],
        "min_source_docs": 0,
        "description": "Completely outside knowledge base",
    },
    {
        "id": "E19",
        "category": "insufficient",
        "question": "What is the weather in New York?",
        "expected": "abstain",
        "expected_keywords": [],
        "min_source_docs": 0,
        "description": "Outside knowledge base scope",
    },
    {
        "id": "E20",
        "category": "insufficient",
        "question": "What are the latest G3 release notes?",
        "expected": "answer_or_abstain",
        "expected_keywords": ["g3"],
        "min_source_docs": 0,
        "description": "May or may not have release notes — either answer or abstain is acceptable",
    },

    # ── Category 8: Citation correctness ─────────────────
    {
        "id": "E21",
        "category": "citation",
        "question": "What is OHIP installation?",
        "expected": "answer",
        "expected_keywords": ["ohip", "installation", "oracle"],
        "min_source_docs": 1,
        "description": "Should cite OHIP installation document",
    },
    {
        "id": "E22",
        "category": "citation",
        "question": "What are the mass mail notification procedures?",
        "expected": "answer",
        "expected_keywords": ["mass", "mail", "notification"],
        "min_source_docs": 1,
        "description": "Should cite mass mail documentation",
    },

    # ── Category 9: Additional grounding tests ───────────
    {
        "id": "E23",
        "category": "grounding",
        "question": "What is Proactive Monitoring - Data Discrepancy?",
        "expected": "answer",
        "expected_keywords": ["proactive", "monitoring", "discrepancy"],
        "min_source_docs": 1,
        "description": "Should answer from monitoring documentation",
    },
    {
        "id": "E24",
        "category": "grounding",
        "question": "What is Stats to Inventory Transition?",
        "expected": "answer",
        "expected_keywords": ["stats", "inventory", "transition"],
        "min_source_docs": 1,
        "description": "Should answer from transition documentation",
    },
    {
        "id": "E25",
        "category": "grounding",
        "question": "What is SSD to OCIM migration?",
        "expected": "answer",
        "expected_keywords": ["ssd", "ocim", "migration"],
        "min_source_docs": 1,
        "description": "Should answer from migration documentation",
    },

    # ── Category 10: Edge cases ──────────────────────────
    {
        "id": "E26",
        "category": "edge",
        "question": "G3",
        "expected": "answer",
        "expected_keywords": ["g3"],
        "min_source_docs": 1,
        "description": "Single-term query — should still retrieve relevant docs",
    },
    {
        "id": "E27",
        "category": "edge",
        "question": "What?",
        "expected": "abstain",
        "expected_keywords": [],
        "min_source_docs": 0,
        "description": "Ambiguous single-word query — should abstain",
    },
]


def run_evaluation(retriever, llm_client=None, use_agentic=True, max_rounds=2):
    """Run the evaluation set against a retriever/generator configuration."""
    vis = VisibilityFilter(max_level=VisibilityLevel.INTERNAL)
    filtered = vis.wrap(retriever)

    if use_agentic:
        pipeline = AgenticSANJAYA(retriever=filtered, llm_client=llm_client, max_rounds=max_rounds)
    else:
        pipeline = AnswerGenerator()

    results = []
    for item in EVALUATION_SET:
        query = item["question"]
        expected = item["expected"]

        t0 = time.time()
        if use_agentic:
            agentic_result = pipeline.ask(query)
            answer_result = agentic_result.answer_result
            rounds = len(agentic_result.rounds)
            unique_docs = agentic_result.unique_documents
            mva = agentic_result.mention_vs_answer_detected
            verify = agentic_result.verification_passed
        else:
            raw_results = filtered.search(query, top_k=10)
            answer_result = pipeline.generate(
                query=query, results=raw_results, strategy="hybrid"
            )
            rounds = 1
            unique_docs = len(set(r.document_id for r in raw_results))
            mva = False
            verify = True
        elapsed = time.time() - t0

        # Determine correctness
        is_abstained = answer_result.abstained
        if expected == "answer":
            correct = not is_abstained
        elif expected == "abstain":
            correct = is_abstained
        else:  # answer_or_abstain
            correct = True

        # Check citation correctness
        citation_correct = True
        if not is_abstained and answer_result.citations:
            evidence_doc_ids = {e.document_id for e in answer_result.evidence}
            for c in answer_result.citations:
                if c.document_id not in evidence_doc_ids:
                    citation_correct = False

        # Check keyword presence
        answer_text = (answer_result.answer or "").lower()
        keywords_found = sum(1 for kw in item["expected_keywords"] if kw.lower() in answer_text)
        keyword_ratio = keywords_found / max(len(item["expected_keywords"]), 1)

        results.append({
            "id": item["id"],
            "category": item["category"],
            "question": query,
            "expected": expected,
            "status": "ABSTAIN" if is_abstained else "ANSWER",
            "correct": correct,
            "confidence": answer_result.confidence,
            "evidence_count": answer_result.evidence_count,
            "unique_docs": unique_docs,
            "citations": len(answer_result.citations),
            "citation_correct": citation_correct,
            "keyword_ratio": keyword_ratio,
            "rounds": rounds,
            "mva_detected": mva,
            "verification": verify,
            "latency": elapsed,
            "answer_preview": (answer_result.answer or "")[:100].replace("\n", " "),
            "conflicts": len(answer_result.conflicts),
        })

    return results


def compute_metrics(results):
    """Compute aggregate metrics from evaluation results."""
    total = len(results)
    correct = sum(1 for r in results if r["correct"])
    answered = sum(1 for r in results if r["status"] == "ANSWER")
    abstained = sum(1 for r in results if r["status"] == "ABSTAIN")

    # By category
    by_category = {}
    for r in results:
        cat = r["category"]
        if cat not in by_category:
            by_category[cat] = {"total": 0, "correct": 0, "answered": 0, "abstained": 0}
        by_category[cat]["total"] += 1
        if r["correct"]:
            by_category[cat]["correct"] += 1
        if r["status"] == "ANSWER":
            by_category[cat]["answered"] += 1
        else:
            by_category[cat]["abstained"] += 1

    # Citation accuracy
    answered_results = [r for r in results if r["status"] == "ANSWER"]
    citation_correct = sum(1 for r in answered_results if r["citation_correct"])
    citation_accuracy = citation_correct / max(len(answered_results), 1)

    # Average metrics
    avg_confidence = sum(r["confidence"] for r in answered_results) / max(len(answered_results), 1)
    avg_latency = sum(r["latency"] for r in results) / max(len(results), 1)
    avg_keywords = sum(r["keyword_ratio"] for r in answered_results) / max(len(answered_results), 1)

    return {
        "total": total,
        "correct": correct,
        "accuracy": correct / max(total, 1),
        "answered": answered,
        "abstained": abstained,
        "by_category": by_category,
        "citation_accuracy": citation_accuracy,
        "avg_confidence": avg_confidence,
        "avg_latency": avg_latency,
        "avg_keyword_ratio": avg_keywords,
    }


def print_results(results, metrics, label):
    """Print formatted evaluation results."""
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}")

    for r in results:
        status_icon = "OK" if r["correct"] else "FAIL"
        cit_icon = "C" if r["citation_correct"] else "X"
        print(f"  {r['id']} [{r['category']:12s}] {status_icon} {r['status']:7s} "
              f"conf={r['confidence']:.3f} docs={r['unique_docs']} "
              f"cit={r['citations']}({cit_icon}) rounds={r['rounds']} "
              f"lat={r['latency']:.2f}s | {r['question'][:50]}")

    print(f"\n  Accuracy:     {metrics['correct']}/{metrics['total']} ({metrics['accuracy']*100:.0f}%)")
    print(f"  Answered:     {metrics['answered']}, Abstained: {metrics['abstained']}")
    print(f"  Citation:     {metrics['citation_accuracy']*100:.0f}%")
    print(f"  Avg Latency:  {metrics['avg_latency']:.2f}s")
    print(f"  Avg Keywords: {metrics['avg_keyword_ratio']*100:.0f}%")

    print(f"\n  By Category:")
    for cat, stats in sorted(metrics["by_category"].items()):
        print(f"    {cat:15s}: {stats['correct']}/{stats['total']} correct, "
              f"{stats['answered']} answered, {stats['abstained']} abstained")


if __name__ == "__main__":
    from kurukshetra.retrieval.hybrid import HybridRetriever
    hybrid = HybridRetriever()

    # ── Baseline: Single-pass ──────────────────────────
    print("\nRunning baseline (single-pass extractive)...")
    base_results = run_evaluation(hybrid, llm_client=None, use_agentic=False)
    base_metrics = compute_metrics(base_results)
    print_results(base_results, base_metrics, "BASELINE (Single-pass Extractive)")

    # ── Agentic: Multi-round ──────────────────────────
    print("\nRunning agentic (multi-round extractive)...")
    agentic_results = run_evaluation(hybrid, llm_client=None, use_agentic=True, max_rounds=2)
    agentic_metrics = compute_metrics(agentic_results)
    print_results(agentic_results, agentic_metrics, "AGENTIC (Multi-round Extractive)")

    # ── Comparison ─────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  COMPARISON")
    print(f"{'='*70}")
    print(f"  {'Metric':<25s} {'Baseline':>10s} {'Agentic':>10s} {'Delta':>10s}")
    print(f"  {'-'*55}")
    print(f"  {'Accuracy':<25s} {base_metrics['accuracy']*100:>9.0f}% {agentic_metrics['accuracy']*100:>9.0f}% {((agentic_metrics['accuracy']-base_metrics['accuracy'])*100):>+9.0f}%")
    print(f"  {'Correct answers':<25s} {base_metrics['correct']:>10d} {agentic_metrics['correct']:>10d} {(agentic_metrics['correct']-base_metrics['correct']):>+10d}")
    print(f"  {'Citation accuracy':<25s} {base_metrics['citation_accuracy']*100:>9.0f}% {agentic_metrics['citation_accuracy']*100:>9.0f}% {((agentic_metrics['citation_accuracy']-base_metrics['citation_accuracy'])*100):>+9.0f}%")
    print(f"  {'Avg latency':<25s} {base_metrics['avg_latency']:>9.2f}s {agentic_metrics['avg_latency']:>9.2f}s {(agentic_metrics['avg_latency']-base_metrics['avg_latency']):>+9.2f}s")
    print(f"  {'Avg keyword coverage':<25s} {base_metrics['avg_keyword_ratio']*100:>9.0f}% {agentic_metrics['avg_keyword_ratio']*100:>9.0f}% {((agentic_metrics['avg_keyword_ratio']-base_metrics['avg_keyword_ratio'])*100):>+9.0f}%")

    # Save results
    report = {
        "baseline": base_metrics,
        "agentic": agentic_metrics,
        "details": {
            "baseline": base_results,
            "agentic": agentic_results,
        },
    }
    with open("reports/mission341_evaluation.json", "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Results saved to reports/mission341_evaluation.json")
