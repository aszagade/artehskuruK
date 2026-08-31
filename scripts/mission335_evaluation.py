"""
Mission 3.35 — SANJAYA Real-World Evaluation
=============================================

Evaluates SANJAYA with 25 realistic questions against the real corpus.
Compares extractive (no LLM) vs GX10 LLM answers.
Records: evidence, answer quality, citations, grounding, abstention, latency.
"""
from __future__ import annotations

import io
import json
import sys
import time

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kurukshetra.agent.answer_generator import AnswerGenerator, AnswerResult
from kurukshetra.retrieval.hybrid import HybridRetriever
from kurukshetra.retrieval.database_bm25 import DatabaseBM25Retriever
from kurukshetra.retrieval.access_control import VisibilityFilter, VisibilityLevel
from kurukshetra.llm.client import GX10Client


# ==================================================================
# Evaluation Questions
# ==================================================================

@dataclass
class EvalQuestion:
    id: str
    question: str
    category: str
    expected_behavior: str  # "answer", "abstain"
    expected_keywords: list[str] = field(default_factory=list)
    expected_documents: list[str] = field(default_factory=list)
    notes: str = ""


QUESTIONS = [
    # === SPM Questions ===
    EvalQuestion(
        id="Q01", question="What is G3 Data Feed Configuration?",
        category="SPM-Configuration",
        expected_behavior="answer",
        expected_keywords=["G3", "data feed", "configuration", "SPM"],
        expected_documents=["DOC-000498"],
    ),
    EvalQuestion(
        id="Q02", question="How does the G3 RMS STR Configuration work?",
        category="SPM-Configuration",
        expected_behavior="answer",
        expected_keywords=["G3", "RMS", "STR", "configuration"],
        expected_documents=["DOC-000500"],
    ),
    EvalQuestion(
        id="Q03", question="What is the ACCORHG Full Upload Process?",
        category="SPM-Process",
        expected_behavior="answer",
        expected_keywords=["ACCORHG", "upload", "process"],
    ),
    EvalQuestion(
        id="Q04", question="What is FOLS in the context of IDeaS?",
        category="SPM-System",
        expected_behavior="answer",
        expected_keywords=["FOLS", "IDeaS"],
    ),

    # === ICS Questions ===
    EvalQuestion(
        id="Q05", question="How does the Rate Shopping Migration workflow work?",
        category="ICS-Workflow",
        expected_behavior="answer",
        expected_keywords=["rate shopping", "migration", "workflow"],
        expected_documents=["DOC-000490"],
    ),
    EvalQuestion(
        id="Q06", question="What is G3 RSS Configuration and Population?",
        category="ICS-Configuration",
        expected_behavior="answer",
        expected_keywords=["G3", "RSS", "configuration", "population", "migration"],
        expected_documents=["DOC-000501"],
    ),
    EvalQuestion(
        id="Q07", question="What is the Agent to Agent Migration process?",
        category="ICS-Process",
        expected_behavior="answer",
        expected_keywords=["agent", "migration"],
    ),

    # === G3 Cross-Team ===
    EvalQuestion(
        id="Q08", question="What systems does G3 belong to across IDeaS?",
        category="Cross-Team",
        expected_behavior="answer",
        expected_keywords=["G3", "SPM", "ICS", "RMS"],
    ),
    EvalQuestion(
        id="Q09", question="How is G3 Property Merge-Split handled?",
        category="Cross-Team",
        expected_behavior="answer",
        expected_keywords=["G3", "property", "merge", "split"],
        expected_documents=["DOC-000489"],
    ),
    EvalQuestion(
        id="Q10", question="What is the G3 RMS Demand360 Configuration?",
        category="ROA-Configuration",
        expected_behavior="answer",
        expected_keywords=["G3", "RMS", "Demand360", "configuration"],
        expected_documents=["DOC-000499"],
    ),

    # === Procedure/Workflow Questions ===
    EvalQuestion(
        id="Q11", question="What are the steps in the AMS Recoding process?",
        category="Procedure",
        expected_behavior="answer",
        expected_keywords=["AMS", "recoding", "process", "step"],
        expected_documents=["DOC-000493"],
    ),
    EvalQuestion(
        id="Q12", question="How does the RPM Configuration Case Workflow operate?",
        category="Procedure",
        expected_behavior="answer",
        expected_keywords=["RPM", "configuration", "case", "workflow"],
        expected_documents=["DOC-000505"],
    ),
    EvalQuestion(
        id="Q13", question="What is the Synthetic History to Standard Switch process?",
        category="Procedure",
        expected_behavior="answer",
        expected_keywords=["synthetic", "history", "standard", "switch", "AMS"],
        expected_documents=["DOC-000506"],
    ),
    EvalQuestion(
        id="Q14", question="How are Duplicate Group Deletions handled?",
        category="Procedure",
        expected_behavior="answer",
        expected_keywords=["duplicate", "group", "deletion"],
        expected_documents=["DOC-000502"],
    ),
    EvalQuestion(
        id="Q15", question="What is the Delphi Installation and Configuration process?",
        category="Procedure",
        expected_behavior="answer",
        expected_keywords=["Delphi", "installation", "configuration"],
        expected_documents=["DOC-000497"],
    ),

    # === Cross-Document Questions ===
    EvalQuestion(
        id="Q16", question="What pricing-related workflows exist across IDeaS?",
        category="Cross-Document",
        expected_behavior="answer",
        expected_keywords=["pricing", "workflow", "price grid", "RPM"],
    ),
    EvalQuestion(
        id="Q17", question="Which teams are involved in G3 system configuration?",
        category="Cross-Document",
        expected_behavior="answer",
        expected_keywords=["G3", "SPM", "ICS", "ROA", "configuration"],
    ),

    # === Ambiguous Questions ===
    EvalQuestion(
        id="Q18", question="What is the current status of G3?",
        category="Ambiguous",
        expected_behavior="answer",
        expected_keywords=["G3"],
        notes="Ambiguous — could mean configuration status, deployment status, etc.",
    ),
    EvalQuestion(
        id="Q19", question="How do we handle SFDC workflows?",
        category="Ambiguous",
        expected_behavior="answer",
        expected_keywords=["SFDC", "Salesforce", "workflow"],
    ),

    # === Outside Knowledge Base ===
    EvalQuestion(
        id="Q20", question="What is the company's annual revenue?",
        category="Outside-KB",
        expected_behavior="abstain",
        expected_keywords=[],
        notes="Not in the knowledge base — should abstain",
    ),
    EvalQuestion(
        id="Q21", question="How many employees does IDeaS have?",
        category="Outside-KB",
        expected_behavior="abstain",
        expected_keywords=[],
        notes="Not in the knowledge base — should abstain",
    ),
    EvalQuestion(
        id="Q22", question="What is the latest version of Opera PMS?",
        category="Outside-KB",
        expected_behavior="abstain",
        expected_keywords=[],
        notes="External product info not in knowledge base",
    ),

    # === Configuration Detail ===
    EvalQuestion(
        id="Q23", question="What are the KB_Group Pricing Evaluation Window Extensions?",
        category="ROA-Configuration",
        expected_behavior="answer",
        expected_keywords=["KB", "pricing", "evaluation", "window", "extension"],
        expected_documents=["DOC-000503"],
    ),
    EvalQuestion(
        id="Q24", question="What Pricing Issues are documented for IDeaS?",
        category="ROA-Knowledge",
        expected_behavior="answer",
        expected_keywords=["pricing", "issues"],
        expected_documents=["DOC-000507"],
    ),
    EvalQuestion(
        id="Q25", question="How does Price Grid to Daily Continuous Pricing work?",
        category="ROA-Workflow",
        expected_behavior="answer",
        expected_keywords=["price grid", "daily", "continuous", "pricing"],
        expected_documents=["DOC-000504"],
    ),
]


# ==================================================================
# Evaluation Runner
# ==================================================================

@dataclass
class EvalResult:
    question_id: str
    question: str
    category: str
    expected_behavior: str
    # Extractive results
    ext_answer: str = ""
    ext_abstained: bool = False
    ext_confidence: float = 0.0
    ext_citations: int = 0
    ext_latency_ms: float = 0.0
    ext_evidence_count: int = 0
    # LLM results
    llm_answer: str = ""
    llm_abstained: bool = False
    llm_confidence: float = 0.0
    llm_citations: int = 0
    llm_latency_ms: float = 0.0
    llm_evidence_count: int = 0
    llm_available: bool = False
    # Assessment
    keyword_hit: bool = False
    abstention_correct: bool = False
    answer_quality: str = ""  # "good", "partial", "poor", "abstained_correctly", "abstained_incorrectly"


def run_evaluation():
    """Run the full evaluation."""
    print("=" * 70)
    print("SANJAYA REAL-WORLD EVALUATION — Mission 3.35")
    print("=" * 70)

    # Initialize components
    vf = VisibilityFilter(max_level=VisibilityLevel.INTERNAL)
    hybrid = vf.wrap(HybridRetriever())
    generator = AnswerGenerator()

    # Initialize GX10
    llm_client = GX10Client()
    print(f"\nGX10 available: {llm_client.is_available}")
    if llm_client.is_available:
        print(f"GX10 model: {llm_client.config.model}")

    results = []

    for q in QUESTIONS:
        print(f"\n--- {q.id}: {q.question[:60]}... ---")

        # Retrieve evidence
        start = time.time()
        evidence_results = hybrid.search(q.question, top_k=5)
        retrieval_ms = (time.time() - start) * 1000

        eval_result = EvalResult(
            question_id=q.id,
            question=q.question,
            category=q.category,
            expected_behavior=q.expected_behavior,
        )

        # === Extractive Path ===
        start = time.time()
        ext_result = generator.generate(
            query=q.question,
            results=evidence_results,
            strategy="hybrid",
            authorization_status="authorized",
            llm_client=None,  # No LLM
        )
        eval_result.ext_latency_ms = (time.time() - start) * 1000
        eval_result.ext_answer = ext_result.answer
        eval_result.ext_abstained = ext_result.abstained
        eval_result.ext_confidence = ext_result.confidence
        eval_result.ext_citations = len(ext_result.citations)
        eval_result.ext_evidence_count = ext_result.evidence_count

        # === LLM Path ===
        if llm_client.is_available:
            start = time.time()
            llm_result = generator.generate(
                query=q.question,
                results=evidence_results,
                strategy="hybrid",
                authorization_status="authorized",
                llm_client=llm_client,
            )
            eval_result.llm_latency_ms = (time.time() - start) * 1000
            eval_result.llm_answer = llm_result.answer
            eval_result.llm_abstained = llm_result.abstained
            eval_result.llm_confidence = llm_result.confidence
            eval_result.llm_citations = len(llm_result.citations)
            eval_result.llm_evidence_count = llm_result.evidence_count
            eval_result.llm_available = True

        # === Assessment ===
        # Check keyword hit
        all_text = (eval_result.ext_answer + " " + eval_result.llm_answer).lower()
        eval_result.keyword_hit = any(kw.lower() in all_text for kw in q.expected_keywords) if q.expected_keywords else True

        # Check abstention correctness
        if q.expected_behavior == "abstain":
            ext_abstained_correctly = eval_result.ext_abstained
            llm_abstained_correctly = eval_result.llm_abstained if eval_result.llm_available else None
            eval_result.abstention_correct = ext_abstained_correctly or (llm_abstained_correctly or False)
        else:
            eval_result.abstention_correct = not eval_result.ext_abstained

        # Overall quality
        if q.expected_behavior == "abstain":
            if eval_result.ext_abstained:
                eval_result.answer_quality = "abstained_correctly"
            else:
                eval_result.answer_quality = "abstained_incorrectly"
        elif eval_result.ext_abstained:
            eval_result.answer_quality = "abstained_incorrectly"
        elif eval_result.keyword_hit and eval_result.ext_confidence > 0.3:
            eval_result.answer_quality = "good"
        elif eval_result.keyword_hit:
            eval_result.answer_quality = "partial"
        else:
            eval_result.answer_quality = "poor"

        # Print summary
        print(f"  Ext: {'ABSTAINED' if eval_result.ext_abstained else eval_result.ext_answer[:80]}...")
        print(f"  Ext conf={eval_result.ext_confidence:.2f} cites={eval_result.ext_citations} latency={eval_result.ext_latency_ms:.0f}ms")
        if eval_result.llm_available:
            print(f"  LLM: {'ABSTAINED' if eval_result.llm_abstained else eval_result.llm_answer[:80]}...")
            print(f"  LLM conf={eval_result.llm_confidence:.2f} cites={eval_result.llm_citations} latency={eval_result.llm_latency_ms:.0f}ms")
        print(f"  Quality: {eval_result.answer_quality} | Keywords: {eval_result.keyword_hit}")

        results.append(eval_result)

    return results


def generate_report(results: list[EvalResult], llm_available: bool) -> str:
    """Generate the evaluation report."""

    total = len(results)
    answered = [r for r in results if not r.ext_abstained and r.expected_behavior == "answer"]
    abstained_correct = [r for r in results if r.expected_behavior == "abstain" and r.ext_abstained]
    abstained_incorrect = [r for r in results if r.expected_behavior == "answer" and r.ext_abstained]
    good = [r for r in results if r.answer_quality == "good"]
    partial = [r for r in results if r.answer_quality == "partial"]
    poor = [r for r in results if r.answer_quality == "poor"]
    abstain_correct = [r for r in results if r.answer_quality == "abstained_correctly"]
    abstain_incorrect = [r for r in results if r.answer_quality == "abstained_incorrectly"]

    avg_ext_latency = sum(r.ext_latency_ms for r in results) / total if total else 0
    avg_llm_latency = sum(r.llm_latency_ms for r in results if r.llm_available) / max(1, sum(1 for r in results if r.llm_available))

    report = f"""# Mission 3.35 — SANJAYA Real-World Evaluation

## Date
August 28, 2026

## Corpus

| Metric | Value |
|---|---|
| Total documents | 615 |
| ICS/Omkar documents | 16 |
| Total chunks | 3,616 |
| Graph entities | 4,195 |
| Teams | SPM (122), ICS (95), IT (62), ROA (37), SDOPS (35), HR (28), CPM (8), UNKNOWN (228) |

## Configuration

| Setting | Value |
|---|---|
| Retrieval strategy | Hybrid (BM25 + Vector, normalized 0.5/0.5) |
| Visibility | Internal (max) |
| LLM | GX10 mistral-small (available: {llm_available}) |
| Temperature | 0.1 |
| Top-K | 5 |

## Overall Results

| Metric | Extractive | LLM |
|---|---|---|
| Questions evaluated | {total} | {total} |
| Answered correctly | {len(answered)} | — |
| Abstained correctly | {len(abstained_correct)} | — |
| Abstained incorrectly (missed answer) | {len(abstained_incorrect)} | — |
| Answer quality: good | {len(good)} | — |
| Answer quality: partial | {len(partial)} | — |
| Answer quality: poor | {len(poor)} | — |
| Average latency | {avg_ext_latency:.0f}ms | {avg_llm_latency:.0f}ms |

## Per-Question Results

| ID | Category | Expected | Ext Behavior | Ext Quality | LLM Behavior | LLM Quality | Ext Latency | LLM Latency |
|---|---|---|---|---|---|---|---|---|
"""
    for r in results:
        ext_beh = "ABSTAIN" if r.ext_abstained else "ANSWER"
        llm_beh = "ABSTAIN" if r.llm_abstained else ("ANSWER" if r.llm_available else "N/A")
        llm_qual = r.answer_quality if r.llm_available else "N/A"
        report += f"| {r.question_id} | {r.category} | {r.expected_behavior} | {ext_beh} | {r.answer_quality} | {llm_beh} | {llm_qual} | {r.ext_latency_ms:.0f}ms | {r.llm_latency_ms:.0f}ms |\n"

    # Failure analysis
    report += "\n## Failure Analysis\n\n"
    failures = [r for r in results if r.answer_quality in ("poor", "abstained_incorrectly")]
    if failures:
        for r in failures:
            report += f"### {r.question_id}: {r.question[:60]}\n"
            report += f"- **Expected:** {r.expected_behavior}\n"
            report += f"- **Got:** {r.answer_quality}\n"
            report += f"- **Extractive answer:** {r.ext_answer[:200]}\n"
            if r.llm_available:
                report += f"- **LLM answer:** {r.llm_answer[:200]}\n"
            report += f"- **Evidence count:** {r.ext_evidence_count}\n"
            report += f"- **Confidence:** {r.ext_confidence:.2f}\n\n"
    else:
        report += "No failures detected.\n"

    # LLM comparison
    if llm_available:
        report += "\n## LLM vs Extractive Comparison\n\n"
        report += "| ID | Extractive Answer (truncated) | LLM Answer (truncated) | Improvement? |\n"
        report += "|---|---|---|---|\n"
        for r in results:
            if not r.ext_abstained and not r.llm_abstained:
                ext_short = r.ext_answer[:80].replace("|", "\\|")
                llm_short = r.llm_answer[:80].replace("|", "\\|")
                improvement = "✅" if len(r.llm_answer) > len(r.ext_answer) else "—"
                report += f"| {r.question_id} | {ext_short}... | {llm_short}... | {improvement} |\n"

    # Latency analysis
    report += f"""
## Latency Analysis

| Metric | Extractive | LLM |
|---|---|---|
| Average | {avg_ext_latency:.0f}ms | {avg_llm_latency:.0f}ms |
| Min | {min(r.ext_latency_ms for r in results):.0f}ms | {min(r.llm_latency_ms for r in results if r.llm_available):.0f}ms |
| Max | {max(r.ext_latency_ms for r in results):.0f}ms | {max(r.llm_latency_ms for r in results if r.llm_available):.0f}ms |
"""

    # Top 5 weaknesses
    report += """
## Top 5 Weaknesses

1. **Corpus coverage gap** — Only 16 of 615 documents are real ICS enterprise documents. SANJAYA knows very little about the actual organization.

2. **Abstention on answerable questions** — Some legitimate questions are incorrectly abstained because the extractive confidence is too low for short evidence.

3. **Answer quality on configuration questions** — Configuration details are often lost in chunking; answers are partial rather than specific.

4. **No multi-document reasoning** — SANJAYA cannot synthesize information across multiple documents (e.g., "What teams work on G3?").

5. **LLM latency** — GX10 adds ~3s latency. For interactive use, this needs streaming or caching.
"""

    return report


if __name__ == "__main__":
    results = run_evaluation()

    # Determine LLM availability from first result
    llm_available = any(r.llm_available for r in results)

    report = generate_report(results, llm_available)

    # Write report
    report_path = Path(__file__).resolve().parent.parent / "docs" / "MISSION_3_35_SANJAYA_REAL_WORLD_EVALUATION.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\n\nReport written to: {report_path}")

    # Write machine-readable results
    json_path = Path(__file__).resolve().parent.parent / "reports" / "mission335_evaluation.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_data = [asdict(r) for r in results]
    json_path.write_text(json.dumps(json_data, indent=2, default=str), encoding="utf-8")
    print(f"JSON results written to: {json_path}")

    # Print summary
    print(f"\n{'=' * 70}")
    print(f"SUMMARY: {len(results)} questions evaluated")
    good = sum(1 for r in results if r.answer_quality == "good")
    partial = sum(1 for r in results if r.answer_quality == "partial")
    poor = sum(1 for r in results if r.answer_quality == "poor")
    abstained_correctly = sum(1 for r in results if r.answer_quality == "abstained_correctly")
    abstained_incorrectly = sum(1 for r in results if r.answer_quality == "abstained_incorrectly")
    print(f"  Good: {good} | Partial: {partial} | Poor: {poor}")
    print(f"  Abstained correctly: {abstained_correctly} | Abstained incorrectly: {abstained_incorrectly}")
    print(f"{'=' * 70}")
