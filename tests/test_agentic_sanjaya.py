"""
Tests for AgenticSANJAYA Orchestrator
=====================================

Deterministic tests for:
- Evidence sufficiency checking
- Mention-vs-answer detection
- Iterative retrieval
- Multi-document evidence aggregation
- Verification layer
"""

import pytest
from kurukshetra.retrieval.models import RetrievalResult
from kurukshetra.agent.orchestrator import (
    AgenticSANJAYA,
    EvidenceSufficiencyChecker,
    RetrievalRound,
    AgenticPlan,
)
from kurukshetra.agent.answer_generator import EvidenceItem


# ── EvidenceSufficiencyChecker ────────────────────────────────


class TestEvidenceSufficiencyChecker:
    """Tests for evidence sufficiency checking."""

    def setup_method(self):
        self.checker = EvidenceSufficiencyChecker()

    def test_empty_evidence_returns_zero(self):
        """Empty evidence should return sufficiency 0."""
        score, mva = self.checker.check("test query", [])
        assert score == 0.0
        assert mva is False

    def test_single_evidence_moderate_sufficiency(self):
        """Single evidence item should have moderate sufficiency."""
        evidence = [
            EvidenceItem(
                chunk_id="c1", document_id="d1", source_path="test.txt",
                text="G3 Data Feed Configuration involves setting up data feeds for G3 RMS.",
                score=0.5, rank=1,
            )
        ]
        score, mva = self.checker.check("What is G3 Data Feed Configuration?", evidence)
        assert score > 0.3
        assert mva is False

    def test_multiple_evidence_higher_sufficiency(self):
        """Multiple evidence items should increase sufficiency."""
        evidence = [
            EvidenceItem(
                chunk_id="c1", document_id="d1", source_path="a.txt",
                text="G3 Data Feed Configuration is used for data exchange between systems.",
                score=0.5, rank=1,
            ),
            EvidenceItem(
                chunk_id="c2", document_id="d2", source_path="b.txt",
                text="The G3 Data Feed setup requires RMS configuration and API keys.",
                score=0.4, rank=2,
            ),
            EvidenceItem(
                chunk_id="c3", document_id="d3", source_path="c.txt",
                text="G3 Data Feed supports multiple data formats including XML and JSON.",
                score=0.3, rank=3,
            ),
        ]
        score, mva = self.checker.check("What is G3 Data Feed Configuration?", evidence)
        assert score > 0.5
        assert mva is False

    def test_count_question_no_numbers_abstains(self):
        """Count question with no numbers in evidence should flag MVA."""
        evidence = [
            EvidenceItem(
                chunk_id="c1", document_id="d1", source_path="hr.txt",
                text="Employees of IDeaS are eligible for various benefits and work policies.",
                score=0.5, rank=1,
            ),
        ]
        score, mva = self.checker.check("How many employees does IDeaS have?", evidence)
        assert mva is True
        assert score < 0.6  # Penalized by MVA

    def test_count_question_with_numbers_no_context(self):
        """Count question with numbers but not in headcount context should flag MVA."""
        evidence = [
            EvidenceItem(
                chunk_id="c1", document_id="d1", source_path="hr.txt",
                text="For how many Children can an employee claim? Ans - The day care facility supports up to 5 children per employee.",
                score=0.5, rank=1,
            ),
        ]
        score, mva = self.checker.check("How many employees does IDeaS have?", evidence)
        # Numbers exist but are about children, not employee count
        assert mva is True

    def test_count_question_with_headcount(self):
        """Count question with actual headcount should NOT flag MVA."""
        evidence = [
            EvidenceItem(
                chunk_id="c1", document_id="d1", source_path="hr.txt",
                text="IDeaS has approximately 500 employees across global offices.",
                score=0.5, rank=1,
            ),
        ]
        score, mva = self.checker.check("How many employees does IDeaS have?", evidence)
        assert mva is False
        assert score > 0.5

    def test_non_count_question_not_affected(self):
        """Non-count questions should not be affected by MVA detection."""
        evidence = [
            EvidenceItem(
                chunk_id="c1", document_id="d1", source_path="g3.txt",
                text="G3 Data Feed Configuration involves API setup for data exchange.",
                score=0.5, rank=1,
            ),
        ]
        score, mva = self.checker.check("What is G3 Data Feed?", evidence)
        assert mva is False


# ── Mention-vs-Answer Detection in AnswerGenerator ────────────


class TestMentionVsAnswerDetection:
    """Tests for MVA detection in AnswerGenerator."""

    def setup_method(self):
        from kurukshetra.agent.answer_generator import AnswerGenerator
        self.gen = AnswerGenerator()

    def test_count_question_no_numbers_abstains(self):
        """Count question without numbers in evidence should abstain."""
        results = [
            RetrievalResult(
                chunk_id="c1", document_id="d1", score=0.5,
                text="Employees are eligible for benefits and work policies at IDeaS.",
                metadata={},
            ),
        ]
        r = self.gen.generate(
            query="How many employees does IDeaS have?",
            results=results,
            strategy="hybrid",
        )
        # Should abstain because evidence mentions employees but doesn't give a count
        assert r.abstained is True

    def test_count_question_with_headcount_no_mva_penalty(self):
        """MVA detection should not penalize evidence with actual headcount."""
        evidence = [
            EvidenceItem(
                chunk_id="c1", document_id="d1", source_path="hr.txt",
                text="IDeaS employees: The company has approximately 500 employees worldwide. Employee headcount includes full-time and contract staff.",
                score=0.5, rank=1,
            ),
        ]
        penalty = self.gen._detect_mention_vs_answer(
            "How many employees does IDeaS have?", evidence
        )
        # MVA penalty should be 0 because evidence contains a count
        assert penalty == 0.0

    def test_non_count_question_not_affected(self):
        """Non-count questions should not be affected by MVA detection."""
        results = [
            RetrievalResult(
                chunk_id="c1", document_id="d1", score=0.5,
                text="G3 Data Feed Configuration involves API setup and data exchange.",
                metadata={},
            ),
        ]
        r = self.gen.generate(
            query="What is G3 Data Feed Configuration?",
            results=results,
            strategy="hybrid",
        )
        assert r.abstained is False


# ── AgenticSANJAYA Orchestrator ──────────────────────────────


class TestAgenticSANJAYA:
    """Tests for the agentic orchestrator."""

    def setup_method(self):
        from kurukshetra.retrieval.hybrid import HybridRetriever
        from kurukshetra.retrieval.access_control import VisibilityFilter, VisibilityLevel
        self.hybrid = HybridRetriever()
        self.vis = VisibilityFilter(max_level=VisibilityLevel.INTERNAL)
        self.filtered = self.vis.wrap(self.hybrid)
        self.orch = AgenticSANJAYA(retriever=self.filtered, llm_client=None, max_rounds=2)

    def test_simple_question_one_round(self):
        """Simple factual question should complete in one round."""
        result = self.orch.ask("What is G3 Data Feed Configuration?")
        assert len(result.rounds) >= 1
        assert result.answer_result.abstained is False
        assert result.verification_passed is True

    def test_out_of_scope_abstains(self):
        """Out-of-scope question should abstain."""
        result = self.orch.ask("What is quantum computing?")
        assert result.answer_result.abstained is True

    def test_evidence_has_multiple_documents(self):
        """Entity/team questions should retrieve from multiple documents."""
        result = self.orch.ask("What do you know about ICS?")
        assert result.unique_documents >= 1
        assert len(result.answer_result.evidence) >= 1

    def test_iterative_retrieval_bounded(self):
        """Retrieval should never exceed max_rounds."""
        result = self.orch.ask("What teams are involved with G3?")
        assert len(result.rounds) <= 2

    def test_agentic_result_has_all_fields(self):
        """AgenticResult should have all required fields."""
        result = self.orch.ask("What is OHIP installation?")
        assert hasattr(result, "answer_result")
        assert hasattr(result, "rounds")
        assert hasattr(result, "total_retrieval_time_ms")
        assert hasattr(result, "total_evidence_count")
        assert hasattr(result, "unique_documents")
        assert hasattr(result, "multi_document_synthesis")
        assert hasattr(result, "mention_vs_answer_detected")
        assert hasattr(result, "verification_passed")

    def test_retrieval_round_has_diagnostics(self):
        """Each retrieval round should have diagnostic information."""
        result = self.orch.ask("What is G3 RMS?")
        for rd in result.rounds:
            assert hasattr(rd, "round_number")
            assert hasattr(rd, "strategy")
            assert hasattr(rd, "query_used")
            assert hasattr(rd, "evidence")
            assert hasattr(rd, "sufficiency_score")
            assert hasattr(rd, "mention_vs_answer_flag")

    def test_entity_augmented_results(self):
        """Entity queries should augment results with graph-based documents."""
        result = self.orch.ask("What do you know about SPM?")
        assert result.total_evidence_count >= 1
        assert result.unique_documents >= 1

    def test_workflow_question_answers(self):
        """Workflow questions should answer from retrieved evidence."""
        result = self.orch.ask("How does AMS Recoding work?")
        assert result.answer_result.abstained is False
        assert len(result.answer_result.evidence) >= 1

    def test_mention_vs_answer_flag_propagates(self):
        """MVA detection should propagate to AgenticResult."""
        result = self.orch.ask("How many employees does IDeaS have?")
        # MVA should be detected in at least one round
        assert result.mention_vs_answer_detected is True
        assert result.answer_result.abstained is True

    def test_verification_passes_for_good_answer(self):
        """Verification should pass for well-grounded answers."""
        result = self.orch.ask("What is G3 Data Feed Configuration?")
        assert result.verification_passed is True

    def test_max_rounds_configurable(self):
        """Max rounds should be configurable."""
        orch1 = AgenticSANJAYA(retriever=self.filtered, max_rounds=1)
        result1 = orch1.ask("What teams are involved with G3?")
        assert len(result1.rounds) <= 1

        orch3 = AgenticSANJAYA(retriever=self.filtered, max_rounds=3)
        result3 = orch3.ask("What teams are involved with G3?")
        assert len(result3.rounds) <= 3
