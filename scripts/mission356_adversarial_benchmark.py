#!/usr/bin/env python3
"""
Mission 3.56 — Evidence Sufficiency V2 Adversarial Benchmark
=============================================================
Tests the V2 gate against real corpus retrieval results.
"""

import sys
import time
from pathlib import Path
from dataclasses import dataclass, field

sys.path.insert(0, str(Path(__file__).parent.parent))

from kurukshetra.registry.database import get_connection
from kurukshetra.agent.sufficiency_gate import EvidenceSufficiencyGate, SufficiencyLevel


# ---------------------------------------------------------------------------
# Benchmark questions — adversarial + real corpus
# ---------------------------------------------------------------------------

BENCHMARK_QUESTIONS = [
    # ── Category A: Direct factual (should ANSWER) ──
    {"id": "A01", "question": "What is G3 Data Feed Configuration?", "expect": "answer", "category": "direct_factual"},
    {"id": "A02", "question": "What is the FOLS processing issue?", "expect": "answer", "category": "direct_factual"},
    {"id": "A03", "question": "What is the Agent to Agent Migration process?", "expect": "answer", "category": "direct_factual"},
    {"id": "A04", "question": "What is OHIP?", "expect": "answer", "category": "definition"},
    {"id": "A05", "question": "What is a Component Room in G3 RMS?", "expect": "answer", "category": "definition"},

    # ── Category B: Procedures (should ANSWER) ──
    {"id": "B01", "question": "How does the ACCOR Full Upload Process work?", "expect": "answer", "category": "procedure"},
    {"id": "B02", "question": "How does AMS Recoding work?", "expect": "answer", "category": "procedure"},
    {"id": "B03", "question": "How do you enable monitoring for a G3 property?", "expect": "answer", "category": "procedure"},

    # ── Category C: Ownership (should ANSWER or PARTIAL) ──
    {"id": "C01", "question": "Who is responsible for FOLS processing?", "expect": "answer", "category": "ownership"},
    {"id": "C02", "question": "Which teams are involved with G3?", "expect": "partial_or_answer", "category": "cross_team"},

    # ── Category D: Team/entity overview (should PARTIAL or ANSWER) ──
    {"id": "D01", "question": "What do you know about ICS?", "expect": "partial_or_answer", "category": "entity_overview"},
    {"id": "D02", "question": "What do you know about SPM?", "expect": "partial_or_answer", "category": "entity_overview"},

    # ── Category E: Count (should ABSTAIN unless numbers exist) ──
    {"id": "E01", "question": "How many employees does IDeaS have?", "expect": "abstain", "category": "count"},
    {"id": "E02", "question": "How many properties use G3 RMS globally?", "expect": "abstain", "category": "count"},

    # ── Category F: Specific value (should ABSTAIN unless value exists) ──
    {"id": "F01", "question": "What is the pricing for G3 RMS licensing?", "expect": "abstain", "category": "specific_value"},
    {"id": "F02", "question": "What is the SLA for OHIP installation?", "expect": "abstain", "category": "specific_value"},

    # ── Category G: Out-of-scope (should ABSTAIN) ──
    {"id": "G01", "question": "What is the company's annual revenue?", "expect": "abstain", "category": "out_of_scope"},
    {"id": "G02", "question": "How many employees does the company have?", "expect": "abstain", "category": "out_of_scope"},
    {"id": "G03", "question": "What is the stock price of IDeaS?", "expect": "abstain", "category": "out_of_scope"},

    # ── Category H: Aspect mismatch (should ABSTAIN) ──
    {"id": "H01", "question": "What programming language is G3 written in?", "expect": "abstain", "category": "aspect_mismatch"},
    {"id": "H02", "question": "What database does G3 use?", "expect": "abstain", "category": "aspect_mismatch"},

    # ── Category I: Cross-document (should ANSWER or PARTIAL) ──
    {"id": "I01", "question": "What workflows involve both ICS and SPM?", "expect": "partial_or_answer", "category": "cross_document"},
    {"id": "I02", "question": "Which systems are shared between SPM and ICS?", "expect": "partial_or_answer", "category": "cross_document"},
]


def get_retrieval_results(query: str, top_k: int = 5):
    """Retrieve evidence from the real corpus using keyword matching."""
    conn = get_connection()

    # Get chunks
    rows = conn.execute("SELECT chunk_id, document_id, text FROM chunks LIMIT 100000").fetchall()
    chunk_index = {r[0]: {"document_id": r[1], "text": r[2]} for r in rows}

    # Simple keyword retrieval
    search_terms = query.lower().split()
    results = []
    for cid, cdata in chunk_index.items():
        text_lower = cdata["text"].lower()
        matches = sum(1 for t in search_terms if t in text_lower)
        if matches >= 2:
            results.append({
                "chunk_id": cid,
                "document_id": cdata["document_id"],
                "text": cdata["text"],
                "score": matches / len(search_terms),
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


def run_benchmark():
    """Run the adversarial benchmark."""
    gate = EvidenceSufficiencyGate()

    class MockEv:
        def __init__(self, chunk_id, document_id, text, score):
            self.chunk_id = chunk_id
            self.document_id = document_id
            self.source_path = ""
            self.text = text
            self.score = score
            self.rank = 1
            self.metadata = {}

    results = []
    for q in BENCHMARK_QUESTIONS:
        t0 = time.time()
        retrieval = get_retrieval_results(q["question"])
        evidence = [MockEv(r["chunk_id"], r["document_id"], r["text"], r["score"]) for r in retrieval]

        gate_result = gate.check(q["question"], evidence)
        latency_ms = (time.time() - t0) * 1000

        # Classify the gate's decision
        if gate_result.should_abstain:
            gate_decision = "abstain"
        elif gate_result.level == SufficiencyLevel.SUFFICIENT:
            gate_decision = "answer"
        else:
            gate_decision = "partial"

        # Check if gate matched expectation
        expected = q["expect"]
        if expected == "abstain":
            correct = gate_decision == "abstain"
        elif expected == "answer":
            correct = gate_decision in ("answer", "partial")
        elif expected == "partial_or_answer":
            correct = gate_decision in ("partial", "answer")
        else:
            correct = False

        results.append({
            "id": q["id"],
            "question": q["question"][:60],
            "category": q["category"],
            "expected": expected,
            "gate_decision": gate_decision,
            "correct": correct,
            "score": gate_result.score,
            "answer_pattern": gate_result.answer_pattern_match,
            "topical_relevance": gate_result.topical_relevance,
            "topic_coverage": gate_result.topic_coverage,
            "semantic_match": gate_result.semantic_match,
            "evidence_quality": gate_result.evidence_quality,
            "evidence_count": len(evidence),
            "latency_ms": round(latency_ms, 1),
        })

    return results


def print_report(results):
    """Print the benchmark report."""
    total = len(results)
    correct = sum(1 for r in results if r["correct"])
    accuracy = correct / total * 100

    # Category breakdown
    categories = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"total": 0, "correct": 0}
        categories[cat]["total"] += 1
        if r["correct"]:
            categories[cat]["correct"] += 1

    # Abstention accuracy
    abstain_expected = [r for r in results if r["expected"] == "abstain"]
    abstain_correct = sum(1 for r in abstain_expected if r["gate_decision"] == "abstain")
    abstain_accuracy = abstain_correct / max(len(abstain_expected), 1) * 100

    # False answer rate (answered when should abstain)
    false_answers = sum(1 for r in results if r["expected"] == "abstain" and r["gate_decision"] != "abstain")
    false_answer_rate = false_answers / max(len(abstain_expected), 1) * 100

    # Latency
    latencies = [r["latency_ms"] for r in results]
    p50 = sorted(latencies)[len(latencies) // 2]
    p95 = sorted(latencies)[int(len(latencies) * 0.95)]

    print(f"\n{'='*70}")
    print(f"EVIDENCE SUFFICIENCY GATE V2 — ADVERSARIAL BENCHMARK")
    print(f"{'='*70}")
    print(f"\nTotal questions: {total}")
    print(f"Correct: {correct}/{total} ({accuracy:.1f}%)")
    print(f"\nAbstention accuracy: {abstain_correct}/{len(abstain_expected)} ({abstain_accuracy:.1f}%)")
    print(f"False answer rate: {false_answers}/{len(abstain_expected)} ({false_answer_rate:.1f}%)")

    print(f"\nLatency: p50={p50:.0f}ms, p95={p95:.0f}ms")

    print(f"\n{'Category':<20} {'Correct':<10} {'Total':<10} {'Rate':<10}")
    print(f"{'-'*50}")
    for cat, data in sorted(categories.items()):
        rate = data["correct"] / max(data["total"], 1) * 100
        print(f"{cat:<20} {data['correct']:<10} {data['total']:<10} {rate:.0f}%")

    print(f"\n{'='*70}")
    print(f"PER-QUESTION DETAIL")
    print(f"{'='*70}")
    print(f"{'ID':<6} {'Expected':<12} {'Decision':<10} {'Score':<8} {'Pattern':<8} {'Topical':<8} {'Coverage':<9} {'Correct':<8}")
    print(f"{'-'*80}")
    for r in results:
        mark = "✓" if r["correct"] else "✗"
        print(f"{r['id']:<6} {r['expected']:<12} {r['gate_decision']:<10} {r['score']:.3f}  {r['answer_pattern']:.2f}    {r['topical_relevance']:.2f}    {r['topic_coverage']:.2f}     {mark}")

    # Failures
    failures = [r for r in results if not r["correct"]]
    if failures:
        print(f"\n{'='*70}")
        print(f"FAILURES ({len(failures)})")
        print(f"{'='*70}")
        for f in failures:
            print(f"  {f['id']}: {f['question']}")
            print(f"    Expected: {f['expected']}, Got: {f['gate_decision']}")
            print(f"    Score: {f['score']:.3f}, Pattern: {f['answer_pattern']:.2f}, Topical: {f['topical_relevance']:.2f}")
            print()

    return accuracy, abstain_accuracy, false_answer_rate


if __name__ == "__main__":
    results = run_benchmark()
    accuracy, abstain_acc, false_answer = print_report(results)
