"""
SANJAYA Enterprise Readiness Evaluation — Mission 3.45
======================================================

Comprehensive end-to-end evaluation of everything built across all missions.
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

# ── 30-Question Enterprise Evaluation Set ─────────────────────

EVAL = [
    # EASY — direct factual (should answer)
    ("E01", "easy", "What is G3 Data Feed Configuration?", "answer", "data feed"),
    ("E02", "easy", "What is OHIP installation?", "answer", "ohip"),
    ("E03", "easy", "What is Duplicate Group Deletion?", "answer", "duplicate"),
    ("E04", "easy", "What is the G3 GA Update Group Evaluation Window?", "answer", "evaluation"),

    # PROCEDURE — workflow/process questions
    ("E05", "procedure", "How does AMS Recoding work?", "answer", "recoding"),
    ("E06", "procedure", "How does Rate Shopping Migration work?", "answer", "migration"),
    ("E07", "procedure", "What is the Agent to Agent Migration process?", "answer", "migration"),
    ("E08", "procedure", "How do you add a new property to G3?", "answer", "property"),

    # CROSS-DOCUMENT — requires multiple sources
    ("E09", "cross_doc", "What teams are involved with G3?", "answer", "team"),
    ("E10", "cross_doc", "What are the different G3 installation processes?", "answer", "install"),
    ("E11", "cross_doc", "How does G3 RMS connect to OHIP?", "answer", "ohip"),

    # CROSS-TEAM — team-specific knowledge
    ("E12", "cross_team", "What does ICS handle in the G3 ecosystem?", "answer", "ics"),
    ("E13", "cross_team", "What does SPM handle for G3?", "answer", "spm"),
    ("E14", "cross_team", "What pricing and forecasting capabilities does IDeaS provide?", "answer", "pricing"),

    # CONFIGURATION — settings/parameters
    ("E15", "config", "What is Agile Rates configuration?", "answer", "agile"),
    ("E16", "config", "What is Proactive Monitoring - Data Discrepancy?", "answer", "monitoring"),

    # DIFFICULT — requires deep understanding
    ("E17", "difficult", "What is SSD to OCIM migration?", "answer", "migration"),
    ("E18", "difficult", "What is Stats to Inventory Transition?", "answer", "inventory"),

    # MISLEADING — mentions topic but doesn't answer
    ("E19", "misleading", "How many employees does IDeaS have?", "abstain", ""),
    ("E20", "misleading", "What is the company annual revenue?", "abstain", ""),
    ("E21", "misleading", "What is the salary range for G3 engineers?", "abstain", ""),

    # INSUFFICIENT EVIDENCE — should abstain
    ("E22", "insufficient", "What is quantum computing?", "abstain", ""),
    ("E23", "insufficient", "What is the weather in New York?", "abstain", ""),
    ("E24", "insufficient", "What are the latest G3 release notes?", "answer_or_abstain", "g3"),

    # CITATION — should cite sources
    ("E25", "citation", "What are the mass mail notification procedures?", "answer", "mail"),
    ("E26", "citation", "What is the process for de-installing a G3 property?", "answer", "de-install"),

    # GROUNDING — answer must be grounded
    ("E27", "grounding", "What is the OHIP data flow process?", "answer", "ohip"),
    ("E28", "grounding", "How does the forecasting optimization work?", "answer", "forecast"),

    # EDGE CASES
    ("E29", "edge", "G3", "answer", "g3"),
    ("E30", "edge", "What?", "abstain", ""),
]


def run_eval(retriever, label):
    vis = VisibilityFilter(max_level=VisibilityLevel.INTERNAL)
    filtered = vis.wrap(retriever)
    gen = AnswerGenerator()

    results = []
    for qid, category, question, expected, keyword in EVAL:
        t0 = time.time()
        raw = filtered.search(question, top_k=10)
        r = gen.generate(query=question, results=raw, strategy="hybrid")
        elapsed = time.time() - t0

        is_abstained = r.abstained
        if expected == "answer":
            correct = not is_abstained
        elif expected == "abstain":
            correct = is_abstained
        else:
            correct = True

        # Citation check
        citation_ok = True
        if not is_abstained and r.citations:
            evidence_docs = {e.document_id for e in r.evidence}
            for c in r.citations:
                if c.document_id not in evidence_docs:
                    citation_ok = False

        # Keyword check
        answer_text = (r.answer or "").lower()
        kw_found = keyword.lower() in answer_text if keyword else True

        # Trustworthiness classification
        if is_abstained and expected == "abstain":
            trust = "GREEN"
        elif not is_abstained and expected == "answer" and r.confidence >= 0.6 and citation_ok:
            trust = "GREEN"
        elif not is_abstained and expected == "answer" and r.confidence >= 0.4:
            trust = "YELLOW"
        elif not is_abstained and expected == "answer":
            trust = "YELLOW"
        elif is_abstained and expected == "answer":
            trust = "RED"
        elif not is_abstained and expected == "abstain":
            trust = "RED"
        else:
            trust = "YELLOW"

        results.append({
            "id": qid, "category": category, "question": question,
            "expected": expected, "status": "ABSTAIN" if is_abstained else "ANSWER",
            "correct": correct, "confidence": r.confidence,
            "evidence_count": r.evidence_count,
            "citations": len(r.citations), "citation_ok": citation_ok,
            "keyword_ok": kw_found, "trust": trust, "latency": elapsed,
            "knowledge_source": r.knowledge_source,
            "answer_preview": (r.answer or "")[:80].replace("\n", " "),
        })
    return results


def compute_metrics(results):
    total = len(results)
    correct = sum(1 for r in results if r["correct"])
    answered = sum(1 for r in results if r["status"] == "ANSWER")
    abstained = sum(1 for r in results if r["status"] == "ABSTAIN")

    green = sum(1 for r in results if r["trust"] == "GREEN")
    yellow = sum(1 for r in results if r["trust"] == "YELLOW")
    red = sum(1 for r in results if r["trust"] == "RED")

    answered_results = [r for r in results if r["status"] == "ANSWER"]
    citation_ok = sum(1 for r in answered_results if r["citation_ok"])
    citation_acc = citation_ok / max(len(answered_results), 1)

    avg_conf = sum(r["confidence"] for r in answered_results) / max(len(answered_results), 1)
    avg_lat = sum(r["latency"] for r in results) / max(len(results), 1)

    # MRR
    mrr = 0.0
    for r in results:
        if r["correct"] and r["status"] == "ANSWER":
            mrr += 1.0  # rank 1 assumed for single-pass
    mrr /= max(total, 1)

    # By category
    cats = {}
    for r in results:
        c = r["category"]
        if c not in cats:
            cats[c] = {"total": 0, "correct": 0, "green": 0, "yellow": 0, "red": 0}
        cats[c]["total"] += 1
        if r["correct"]: cats[c]["correct"] += 1
        if r["trust"] == "GREEN": cats[c]["green"] += 1
        elif r["trust"] == "YELLOW": cats[c]["yellow"] += 1
        else: cats[c]["red"] += 1

    return {
        "total": total, "correct": correct, "accuracy": correct / max(total, 1),
        "answered": answered, "abstained": abstained,
        "green": green, "yellow": yellow, "red": red,
        "citation_accuracy": citation_acc,
        "avg_confidence": avg_conf, "avg_latency": avg_lat,
        "mrr": mrr, "by_category": cats,
    }


if __name__ == "__main__":
    from kurukshetra.retrieval.hybrid import HybridRetriever
    hybrid = HybridRetriever()

    print("Running SANJAYA Enterprise Readiness Evaluation...")
    results = run_eval(hybrid, "SANJAYA")
    metrics = compute_metrics(results)

    print(f"\n{'='*70}")
    print(f"  SANJAYA ENTERPRISE READINESS EVALUATION")
    print(f"{'='*70}")

    for r in results:
        icon = {"GREEN": "G", "YELLOW": "Y", "RED": "R"}[r["trust"]]
        print(f"  {r['id']} [{r['category']:12s}] {icon} {r['status']:7s} "
              f"conf={r['confidence']:.3f} cit={'OK' if r['citation_ok'] else 'X'} "
              f"lat={r['latency']:.2f}s | {r['question'][:50]}")

    print(f"\n  === METRICS ===")
    print(f"  Accuracy:         {metrics['correct']}/{metrics['total']} ({metrics['accuracy']*100:.0f}%)")
    print(f"  Answered:         {metrics['answered']}, Abstained: {metrics['abstained']}")
    print(f"  GREEN:            {metrics['green']}/{metrics['total']} ({metrics['green']/metrics['total']*100:.0f}%)")
    print(f"  YELLOW:           {metrics['yellow']}/{metrics['total']}")
    print(f"  RED:              {metrics['red']}/{metrics['total']}")
    print(f"  Citation accuracy: {metrics['citation_accuracy']*100:.0f}%")
    print(f"  MRR:              {metrics['mrr']:.3f}")
    print(f"  Avg confidence:   {metrics['avg_confidence']:.3f}")
    print(f"  Avg latency:      {metrics['avg_latency']:.2f}s")

    print(f"\n  === BY CATEGORY ===")
    for cat, stats in sorted(metrics["by_category"].items()):
        print(f"  {cat:15s}: {stats['correct']}/{stats['total']} correct, "
              f"G={stats['green']} Y={stats['yellow']} R={stats['red']}")

    # Save
    with open("reports/mission345_evaluation.json", "w") as f:
        json.dump({"metrics": metrics, "results": results}, f, indent=2)
    print(f"\n  Saved to reports/mission345_evaluation.json")
