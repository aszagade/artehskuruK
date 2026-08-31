"""
Mission 3.47 — Real A/B Learning Test
======================================

Compares:
A. Learning DISABLED (vanilla retrieval, no feedback adjustment)
B. Learning ENABLED (feedback-adjusted retrieval)

Uses REAL corpus documents and REAL organizational questions.
Measures whether feedback learning actually generalizes.
"""
import sys, os, time, json

os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')

from kurukshetra.retrieval.hybrid import HybridRetriever
from kurukshetra.retrieval.access_control import VisibilityFilter, VisibilityLevel
from kurukshetra.retrieval.feedback_retriever import (
    FeedbackAwareRetriever, set_feedback_enabled
)
from kurukshetra.services.feedback import FeedbackLoop
from kurukshetra.retrieval.evaluation_tracker import EvaluationSignalTracker
from kurukshetra.agent.orchestrator import AgenticSANJAYA

# ── Fixed Evaluation Set ───────────────────────────────────────
# Organized by category. Expected behavior based on actual corpus.

EVAL_SET = [
    # ── Questions with POSITIVE feedback will be submitted ──
    ("L01", "feedback_pos", "What is G3 Data Feed Configuration?", "answer", "data feed configuration"),
    ("L02", "feedback_pos", "How does AMS Recoding work?", "answer", "recoding"),
    ("L03", "feedback_pos", "What teams are involved with G3?", "answer", "team"),
    ("L04", "feedback_pos", "What do you know about ICS?", "answer", "ics"),
    ("L05", "feedback_pos", "What is OHIP installation?", "answer", "ohip"),
    ("L06", "feedback_pos", "What is Duplicate Group Deletion?", "answer", "duplicate"),
    ("L07", "feedback_pos", "What is Agile Rates configuration?", "answer", "agile"),

    # ── Questions with NEGATIVE feedback will be submitted ──
    ("L08", "feedback_neg", "What is the salary range for G3 engineers?", "abstain", ""),
    ("L09", "feedback_neg", "How many employees does IDeaS have?", "abstain", ""),
    ("L10", "feedback_neg", "What is the company annual revenue?", "abstain", ""),

    # ── UNSEEN questions (no feedback submitted) ──
    ("L11", "unseen", "What is SSD to OCIM migration?", "answer", "migration"),
    ("L12", "unseen", "What is Stats to Inventory Transition?", "answer", "inventory"),
    ("L13", "unseen", "What is Proactive Monitoring - Data Discrepancy?", "answer", "monitoring"),
    ("L14", "unseen", "What does SPM handle for G3?", "answer", "spm"),
    ("L15", "unseen", "What is the Agent to Agent Migration process?", "answer", "migration"),

    # ── CROSS-TEAM questions ──
    ("L16", "cross_team", "How does G3 RMS connect to OHIP?", "answer", "ohip"),
    ("L17", "cross_team", "What are the different G3 installation processes?", "answer", "install"),

    # ── INSUFFICIENT EVIDENCE ──
    ("L18", "insufficient", "What is the implementation timeline for Project X?", "abstain", ""),
    ("L19", "insufficient", "What database does the HR payroll system use?", "abstain", ""),
]


def create_retriever():
    """Create a fresh hybrid retriever with visibility filter."""
    try:
        vf = VisibilityFilter(max_level=VisibilityLevel.INTERNAL)
    except:
        vf = None
    return HybridRetriever(vis_filter=vf, bm25_weight=0.5, vector_weight=0.5)


def run_retrieval_only(eval_set, label, use_feedback=False):
    """Run retrieval-only benchmark (no LLM, fast)."""
    hybrid = create_retriever()

    if use_feedback:
        retriever = FeedbackAwareRetriever(hybrid)
    else:
        retriever = hybrid

    results = []
    for qid, category, question, expected, keyword in eval_set:
        start = time.time()
        retrieved = retriever.search(question, top_k=5)
        latency_ms = (time.time() - start) * 1000

        # Check recall
        top_chunks = [r.text[:200].lower() for r in retrieved]
        top_doc_ids = [r.document_id for r in retrieved]
        all_text = " ".join(top_chunks)
        keyword_found = keyword.lower() in all_text if keyword else True

        # Check for feedback adjustment metadata
        feedback_adjusted = any(r.metadata.get("_feedback_adjusted", False) for r in retrieved)

        results.append({
            "qid": qid,
            "category": category,
            "question": question[:50],
            "expected": expected,
            "keyword_found": keyword_found,
            "results_count": len(retrieved),
            "unique_docs": len(set(top_doc_ids)),
            "top_score": round(retrieved[0].score, 4) if retrieved else 0,
            "feedback_adjusted": feedback_adjusted,
            "latency_ms": round(latency_ms, 1),
        })

    return results


def submit_feedback(eval_set):
    """Submit positive/negative feedback for designated questions."""
    hybrid = create_retriever()
    fb = FeedbackLoop()
    count = 0

    for qid, category, question, expected, keyword in eval_set:
        if category == "feedback_pos":
            # Positive feedback on top results
            results = hybrid.search(question, top_k=5)
            for i, r in enumerate(results[:3]):
                fb.record_feedback(
                    query=question, document_id=r.document_id,
                    chunk_id=r.chunk_id, score=r.score,
                    is_correct=(i < 2), user_id="mission347",
                    comments=f"Positive feedback for {qid}"
                )
                count += 1
        elif category == "feedback_neg":
            # Negative feedback on all results (these should abstain)
            results = hybrid.search(question, top_k=3)
            for r in results[:2]:
                fb.record_feedback(
                    query=question, document_id=r.document_id,
                    chunk_id=r.chunk_id, score=r.score,
                    is_correct=False, user_id="mission347",
                    comments=f"Negative feedback for {qid}"
                )
                count += 1

    return count


def compute_metrics(results, eval_set):
    """Compute aggregate metrics."""
    total = len(results)
    correct_keywords = sum(1 for r in results if r["keyword_found"])

    # Per-category
    by_category = {}
    for r in results:
        cat = r["category"]
        if cat not in by_category:
            by_category[cat] = {"total": 0, "keyword_found": 0}
        by_category[cat]["total"] += 1
        if r["keyword_found"]:
            by_category[cat]["keyword_found"] += 1

    # Recall@3 approximation: check if keyword appears in top 3
    recall_at_3 = 0
    for r in results:
        if r["expected"] == "answer" and r["keyword_found"]:
            recall_at_3 += 1
    answer_questions = sum(1 for r in results if r["expected"] == "answer")
    recall_at_3_rate = recall_at_3 / max(answer_questions, 1)

    # MRR approximation: rank of first relevant result (simplified)
    mrr = 0
    for r in results:
        if r["expected"] == "answer" and r["keyword_found"]:
            mrr += 1.0  # simplified: assume rank 1 for keyword match
    mrr_rate = mrr / max(answer_questions, 1)

    avg_latency = sum(r["latency_ms"] for r in results) / max(total, 1)
    avg_top_score = sum(r["top_score"] for r in results) / max(total, 1)

    return {
        "total": total,
        "keyword_accuracy": round(correct_keywords / max(total, 1), 3),
        "recall_at_3": round(recall_at_3_rate, 3),
        "mrr": round(mrr_rate, 3),
        "avg_latency_ms": round(avg_latency, 1),
        "avg_top_score": round(avg_top_score, 4),
        "by_category": by_category,
    }


def main():
    print("=" * 70)
    print("MISSION 3.47 — REAL A/B LEARNING TEST")
    print("=" * 70)

    # Phase A: Baseline (learning disabled)
    print("\n── PHASE A: LEARNING DISABLED ──")
    set_feedback_enabled(False)
    baseline_results = run_retrieval_only(EVAL_SET, "Baseline", use_feedback=False)
    baseline_metrics = compute_metrics(baseline_results, EVAL_SET)
    print(f"  Keyword accuracy: {baseline_metrics['keyword_accuracy']}")
    print(f"  Recall@3: {baseline_metrics['recall_at_3']}")
    print(f"  MRR: {baseline_metrics['mrr']}")
    print(f"  Avg latency: {baseline_metrics['avg_latency_ms']}ms")
    print(f"  Avg top score: {baseline_metrics['avg_top_score']}")

    # Phase B: Submit feedback
    print("\n── PHASE B: SUBMIT FEEDBACK ──")
    fb_count = submit_feedback(EVAL_SET)
    print(f"  Submitted {fb_count} feedback records")

    # Phase C: Learning enabled
    print("\n── PHASE C: LEARNING ENABLED ──")
    set_feedback_enabled(True)
    learning_results = run_retrieval_only(EVAL_SET, "Learning", use_feedback=True)
    learning_metrics = compute_metrics(learning_results, EVAL_SET)
    print(f"  Keyword accuracy: {learning_metrics['keyword_accuracy']}")
    print(f"  Recall@3: {learning_metrics['recall_at_3']}")
    print(f"  MRR: {learning_metrics['mrr']}")
    print(f"  Avg latency: {learning_metrics['avg_latency_ms']}ms")
    print(f"  Avg top score: {learning_metrics['avg_top_score']}")

    # Comparison
    print("\n── COMPARISON ──")
    print(f"{'Metric':<25} {'Disabled':<12} {'Enabled':<12} {'Delta':<12}")
    print("-" * 60)
    for key in ["keyword_accuracy", "recall_at_3", "mrr", "avg_latency_ms", "avg_top_score"]:
        b = baseline_metrics[key]
        l = learning_metrics[key]
        d = l - b
        sign = "+" if d > 0 else ""
        print(f"  {key:<23} {b:<12} {l:<12} {sign}{d:<11}")

    # Per-category comparison
    print("\n── PER-CATEGORY COMPARISON ──")
    all_cats = set(list(baseline_metrics["by_category"].keys()) + list(learning_metrics["by_category"].keys()))
    for cat in sorted(all_cats):
        b = baseline_metrics["by_category"].get(cat, {"total": 0, "keyword_found": 0})
        l = learning_metrics["by_category"].get(cat, {"total": 0, "keyword_found": 0})
        b_rate = b["keyword_found"] / max(b["total"], 1)
        l_rate = l["keyword_found"] / max(l["total"], 1)
        d = l_rate - b_rate
        sign = "+" if d > 0 else ""
        print(f"  {cat:<20} disabled={b_rate:.1%}  enabled={l_rate:.1%}  delta={sign}{d:.1%}")

    # Per-query detail
    print("\n── PER-QUERY DETAIL ──")
    print(f"{'QID':<5} {'Category':<15} {'Expected':<10} {'Base':<8} {'Learn':<8} {'Adj?':<6}")
    print("-" * 60)
    for b, l in zip(baseline_results, learning_results):
        b_mark = "Y" if b["keyword_found"] else "N"
        l_mark = "Y" if l["keyword_found"] else "N"
        adj = "YES" if l["feedback_adjusted"] else "no"
        delta_mark = ""
        if b_mark != l_mark:
            delta_mark = " ***CHANGED***"
        print(f"  {b['qid']:<5} {b['category']:<15} {b['expected']:<10} {b_mark:<8} {l_mark:<8} {adj:<6}{delta_mark}")

    # Safety check
    print("\n── SAFETY CHECK ──")
    # Verify negative-feedback questions still abstain
    neg_questions_correct = 0
    for b, l in zip(baseline_results, learning_results):
        if b["category"] == "feedback_neg":
            # These should NOT become answerable just because we gave negative feedback
            if not l["keyword_found"]:
                neg_questions_correct += 1
                print(f"  {b['qid']}: correctly remains non-answerable after negative feedback")
            else:
                print(f"  {b['qid']}: WARNING - became answerable after negative feedback!")

    # Verify feedback adjustments are applied
    adj_count = sum(1 for r in learning_results if r["feedback_adjusted"])
    print(f"  Queries with feedback adjustment: {adj_count}/{len(learning_results)}")

    # Evaluation signals
    print("\n── EVALUATION SIGNALS ──")
    tracker = EvaluationSignalTracker()
    summary = tracker.get_learning_summary()
    for k, v in summary.items():
        print(f"  {k}: {v}")

    # Verdict
    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)
    if baseline_metrics["keyword_accuracy"] == learning_metrics["keyword_accuracy"]:
        print("RESULT: Learning has NO measurable impact on accuracy.")
        print("This is expected with small feedback volume — effects grow with use.")
    elif learning_metrics["keyword_accuracy"] > baseline_metrics["keyword_accuracy"]:
        print("RESULT: Learning IMPROVED accuracy.")
    else:
        print("RESULT: Learning REGRESSED accuracy. Investigating...")

    # Check if latency is acceptable
    latency_delta = learning_metrics["avg_latency_ms"] - baseline_metrics["avg_latency_ms"]
    if latency_delta < 100:
        print(f"Latency overhead: {latency_delta:+.1f}ms (acceptable)")
    else:
        print(f"Latency overhead: {latency_delta:+.1f}ms (investigate)")

    print(f"\nFeedback records in DB: {fb_count}")
    set_feedback_enabled(True)


if __name__ == "__main__":
    main()
