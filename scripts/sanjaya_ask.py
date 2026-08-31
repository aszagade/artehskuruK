#!/usr/bin/env python
"""
SANJAYA Interactive CLI
=======================

Ask SANJAYA questions locally and receive evidence-grounded answers.

Usage:
    python scripts/sanjaya_ask.py "What is G3 Data Feed Configuration?"
    python scripts/sanjaya_ask.py --interactive

Requires: GX10 configured in .env (GX10_BASE_URL, GX10_API_KEY)
"""
from __future__ import annotations

import io
import sys
import time

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, ".")

from kurukshetra.retrieval.hybrid import HybridRetriever
from kurukshetra.retrieval.access_control import VisibilityFilter, VisibilityLevel
from kurukshetra.agent.answer_generator import AnswerGenerator
from kurukshetra.llm.client import GX10Client


def ask_sanjaya(question: str, verbose: bool = False) -> dict:
    """Ask SANJAYA a question and return the answer."""
    vf = VisibilityFilter(max_level=VisibilityLevel.INTERNAL)
    hybrid = vf.wrap(HybridRetriever())
    gen = AnswerGenerator()
    llm = GX10Client()

    # Retrieve
    start = time.time()
    results = hybrid.search(question, top_k=5)
    retrieval_ms = (time.time() - start) * 1000

    # Generate
    start = time.time()
    answer = gen.generate(
        query=question,
        results=results,
        strategy="hybrid",
        authorization_status="authorized",
        llm_client=llm,
    )
    gen_ms = (time.time() - start) * 1000

    return {
        "question": question,
        "answer": answer.answer,
        "confidence": answer.confidence,
        "abstained": answer.abstained,
        "citations": len(answer.citations),
        "evidence_count": answer.evidence_count,
        "strategy": answer.retrieval_strategy,
        "retrieval_ms": retrieval_ms,
        "generation_ms": gen_ms,
        "total_ms": retrieval_ms + gen_ms,
        "llm_used": any("LLM" in str(l) for l in answer.limitations),
        "limitations": answer.limitations,
        "source_documents": answer.source_documents,
    }


def print_result(result: dict):
    """Pretty-print a SANJAYA result."""
    print()
    print("=" * 70)
    print(f"  Q: {result['question']}")
    print("=" * 70)

    if result["abstained"]:
        print(f"  SANJAYA: {result['answer']}")
        print(f"  Status: ABSTAINED")
    else:
        print(f"  SANJAYA: {result['answer']}")
        print()
        print(f"  Confidence: {result['confidence']:.3f}")
        print(f"  Citations: {result['citations']}")
        print(f"  Evidence: {result['evidence_count']} chunks")
        print(f"  Strategy: {result['strategy']}")
        print(f"  LLM: {'GX10' if result['llm_used'] else 'extractive'}")
        if result["source_documents"]:
            print(f"  Sources: {', '.join(result['source_documents'][:3])}")

    print(f"  Latency: {result['total_ms']:.0f}ms "
          f"(retrieval: {result['retrieval_ms']:.0f}ms, "
          f"generation: {result['generation_ms']:.0f}ms)")
    print()


def interactive_mode():
    """Interactive question-answering loop."""
    print("SANJAYA Interactive Mode")
    print("Type your question and press Enter. Type 'quit' to exit.")
    print()

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            print("Goodbye.")
            break

        result = ask_sanjaya(question)
        print_result(result)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        interactive_mode()
    elif len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        result = ask_sanjaya(question)
        print_result(result)
    else:
        print("Usage:")
        print('  python scripts/sanjaya_ask.py "Your question here"')
        print("  python scripts/sanjaya_ask.py --interactive")


if __name__ == "__main__":
    main()
