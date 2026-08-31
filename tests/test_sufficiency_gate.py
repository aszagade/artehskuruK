"""Tests for EvidenceSufficiencyGate — Mission 3.55.

Tests that the gate correctly distinguishes evidence that ANSWERS a question
from evidence that merely MENTIONS the question's keywords.
"""

import pytest
from dataclasses import dataclass, field

from kurukshetra.agent.sufficiency_gate import (
    EvidenceSufficiencyGate,
    SufficiencyLevel,
    SufficiencyResult,
    _extract_key_terms,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

@dataclass
class MockEv:
    """Minimal evidence item."""
    chunk_id: str
    document_id: str
    text: str
    score: float = 0.5
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Test: Key-term extraction
# ---------------------------------------------------------------------------

class TestKeyTermExtraction:
    """Test that key terms are extracted from questions."""

    def test_extracts_entities(self):
        terms = _extract_key_terms("What is G3 Data Feed Configuration?")
        assert "G3" in terms

    def test_extracts_content_words(self):
        terms = _extract_key_terms("How does OHIP installation work?")
        assert any("OHIP" in t.upper() for t in terms)

    def test_filters_stop_words(self):
        terms = _extract_key_terms("What is the process for ICS migration?")
        assert "the" not in [t.lower() for t in terms]
        assert "for" not in [t.lower() for t in terms]


# ---------------------------------------------------------------------------
# Test: INSUFFICIENT detection (the critical fix)
# ---------------------------------------------------------------------------

class TestInsufficientDetection:
    """Test that evidence mentioning topic but not answering is INSUFFICIENT."""

    def test_count_question_with_no_count_in_evidence(self):
        """'How many employees does IDeaS have?' — evidence mentions IDeaS but no count."""
        gate = EvidenceSufficiencyGate()
        evidence = [
            MockEv(
                chunk_id="C1", document_id="D1",
                text="IDeaS provides revenue management solutions for the hospitality industry. "
                     "Their team members are dedicated to client success.",
            ),
        ]
        result = gate.check("How many employees does IDeaS have?", evidence)
        assert result.level == SufficiencyLevel.INSUFFICIENT
        assert result.should_abstain is True
        assert result.question_intent == "count"

    def test_specific_value_question_with_no_value(self):
        """'What is the pricing for G3 RMS licensing?' — evidence mentions pricing config but no license cost."""
        gate = EvidenceSufficiencyGate()
        evidence = [
            MockEv(
                chunk_id="C2", document_id="D2",
                text="G3 RMS configuration allows you to set up rate codes and pricing rules "
                     "for the property management system.",
            ),
        ]
        result = gate.check("What is the pricing for G3 RMS licensing?", evidence)
        assert result.level == SufficiencyLevel.INSUFFICIENT
        assert result.should_abstain is True

    def test_sla_question_with_no_sla(self):
        """'What is the SLA for OHIP installation?' — evidence mentions OHIP but no SLA."""
        gate = EvidenceSufficiencyGate()
        evidence = [
            MockEv(
                chunk_id="C3", document_id="D3",
                text="OHIP installation requires configuring the PMS interface and "
                     "setting up the connection between Opera and IDeaS systems.",
            ),
        ]
        result = gate.check("What is the SLA for OHIP installation?", evidence)
        assert result.level == SufficiencyLevel.INSUFFICIENT
        assert result.should_abstain is True

    def test_programming_language_question(self):
        """'What programming language is G3 written in?' — evidence mentions G3 but no language."""
        gate = EvidenceSufficiencyGate()
        evidence = [
            MockEv(
                chunk_id="C4", document_id="D4",
                text="G3 RMS processes rate decisions and sends them to the PMS. "
                     "The system handles data feeds from multiple sources.",
            ),
        ]
        result = gate.check("What programming language is G3 written in?", evidence)
        assert result.level == SufficiencyLevel.INSUFFICIENT
        assert result.should_abstain is True

    def test_company_revenue(self):
        """'What is the company's annual revenue?' — evidence mentions company but no revenue."""
        gate = EvidenceSufficiencyGate()
        evidence = [
            MockEv(
                chunk_id="C5", document_id="D5",
                text="IDeaS is a leading provider of revenue management solutions. "
                     "Their team focuses on client success and technology innovation.",
            ),
        ]
        result = gate.check("What is the company's annual revenue?", evidence)
        assert result.level == SufficiencyLevel.INSUFFICIENT
        assert result.should_abstain is True

    def test_global_property_count(self):
        """'How many properties use G3 RMS globally?' — evidence mentions G3 but no count."""
        gate = EvidenceSufficiencyGate()
        evidence = [
            MockEv(
                chunk_id="C6", document_id="D6",
                text="G3 RMS is installed at various hotel properties worldwide. "
                     "The system supports rate management and pricing optimization.",
            ),
        ]
        result = gate.check("How many properties use G3 RMS globally?", evidence)
        assert result.level == SufficiencyLevel.INSUFFICIENT
        assert result.should_abstain is True


# ---------------------------------------------------------------------------
# Test: SUFFICIENT detection
# ---------------------------------------------------------------------------

class TestSufficientDetection:
    """Test that evidence that actually answers the question is SUFFICIENT."""

    def test_definition_question_with_definition_evidence(self):
        """'What is OHIP?' — evidence defines OHIP."""
        gate = EvidenceSufficiencyGate()
        evidence = [
            MockEv(
                chunk_id="C10", document_id="D10",
                text="OHIP is a hotel PMS interface that connects Opera with IDeaS G3 RMS. "
                     "It allows the system to receive reservation and room data from the PMS.",
            ),
        ]
        result = gate.check("What is OHIP?", evidence)
        assert result.level == SufficiencyLevel.SUFFICIENT
        assert result.should_abstain is False

    def test_procedure_question_with_steps(self):
        """'How does Agent to Agent Migration work?' — evidence describes steps."""
        gate = EvidenceSufficiencyGate()
        evidence = [
            MockEv(
                chunk_id="C11", document_id="D11",
                text="Step 1: Stop all incoming extract pulls. Step 2: Complete the migration "
                     "orchestrator job. Step 3: Verify the property moves to Data Capture Mode.",
            ),
        ]
        result = gate.check("How does Agent to Agent Migration work?", evidence)
        assert result.level in (SufficiencyLevel.SUFFICIENT, SufficiencyLevel.PARTIAL)
        assert result.should_abstain is False

    def test_ownership_question_with_responsibility(self):
        """'Who is responsible for FOLS processing?' — evidence assigns responsibility."""
        gate = EvidenceSufficiencyGate()
        evidence = [
            MockEv(
                chunk_id="C12", document_id="D12",
                text="The SPM team is responsible for FOLS processing. "
                     "They handle the full upload process and monitor daily audits.",
            ),
        ]
        result = gate.check("Who is responsible for FOLS processing?", evidence)
        assert result.level == SufficiencyLevel.SUFFICIENT
        assert result.should_abstain is False

    def test_count_question_with_number(self):
        """'How many HR policy documents exist?' — evidence contains a count."""
        gate = EvidenceSufficiencyGate()
        evidence = [
            MockEv(
                chunk_id="C13", document_id="D13",
                text="There are 28 HR policy documents in the knowledge base, "
                     "covering adoption, benefits, performance review, and more.",
            ),
        ]
        result = gate.check("How many HR policy documents are there?", evidence)
        assert result.level in (SufficiencyLevel.SUFFICIENT, SufficiencyLevel.PARTIAL)
        assert result.should_abstain is False

    def test_configuration_question_with_steps(self):
        """'How do you enable monitoring for a G3 property?' — evidence has config steps."""
        gate = EvidenceSufficiencyGate()
        evidence = [
            MockEv(
                chunk_id="C14", document_id="D14",
                text="To enable monitoring for a G3 property: Go to Support > Configuration > "
                     "Property Tab. Select the property. Click Create. Once created, "
                     "email notifications will be configured automatically.",
            ),
        ]
        result = gate.check("How do you enable monitoring for a G3 property?", evidence)
        assert result.level == SufficiencyLevel.SUFFICIENT
        assert result.should_abstain is False


# ---------------------------------------------------------------------------
# Test: PARTIAL detection
# ---------------------------------------------------------------------------

class TestPartialDetection:
    """Test that evidence that partially answers is PARTIAL."""

    def test_partial_ownership(self):
        """Evidence mentions team but doesn't explicitly assign responsibility."""
        gate = EvidenceSufficiencyGate()
        evidence = [
            MockEv(
                chunk_id="C20", document_id="D20",
                text="The SPM team handles various upload processes for G3 properties. "
                     "They work with data feeds and configuration management.",
            ),
        ]
        result = gate.check("Which team owns the G3 Data Feed Configuration process?", evidence)
        # Should be at least PARTIAL, not INSUFFICIENT
        assert result.level != SufficiencyLevel.INSUFFICIENT
        assert result.should_abstain is False


# ---------------------------------------------------------------------------
# Test: Empty evidence
# ---------------------------------------------------------------------------

class TestEmptyEvidence:
    """Test that empty evidence always returns INSUFFICIENT."""

    def test_no_evidence(self):
        gate = EvidenceSufficiencyGate()
        result = gate.check("What is G3?", [])
        assert result.level == SufficiencyLevel.INSUFFICIENT
        assert result.should_abstain is True


# ---------------------------------------------------------------------------
# Test: Multiple evidence items
# ---------------------------------------------------------------------------

class TestMultipleEvidence:
    """Test behavior with multiple evidence items."""

    def test_mixed_evidence(self):
        """Some evidence answers, some doesn't — should be at least PARTIAL."""
        gate = EvidenceSufficiencyGate()
        evidence = [
            MockEv(
                chunk_id="C30", document_id="D30",
                text="SPM is responsible for managing the FOLS processing workflow. "
                     "The team handles daily uploads and monitoring.",
            ),
            MockEv(
                chunk_id="C31", document_id="D31",
                text="G3 RMS processes rate decisions from multiple data sources.",
            ),
        ]
        result = gate.check("Who is responsible for FOLS processing?", evidence)
        assert result.level != SufficiencyLevel.INSUFFICIENT

    def test_all_irrelevant_evidence(self):
        """All evidence is irrelevant — should be INSUFFICIENT."""
        gate = EvidenceSufficiencyGate()
        evidence = [
            MockEv(
                chunk_id="C32", document_id="D32",
                text="The weather in London is typically overcast in winter.",
            ),
            MockEv(
                chunk_id="C33", document_id="D33",
                text="Python is a popular programming language for data science.",
            ),
        ]
        result = gate.check("What is the SLA for OHIP installation?", evidence)
        assert result.level == SufficiencyLevel.INSUFFICIENT
        assert result.should_abstain is True


# ---------------------------------------------------------------------------
# Test: Result data model
# ---------------------------------------------------------------------------

class TestSufficiencyResult:
    """Test that SufficiencyResult has all required fields."""

    def test_result_fields(self):
        gate = EvidenceSufficiencyGate()
        evidence = [
            MockEv(chunk_id="C40", document_id="D40", text="G3 is a revenue management system."),
        ]
        result = gate.check("What is G3?", evidence)
        assert isinstance(result, SufficiencyResult)
        assert result.level in (SufficiencyLevel.SUFFICIENT, SufficiencyLevel.PARTIAL, SufficiencyLevel.INSUFFICIENT)
        assert 0.0 <= result.score <= 1.0
        assert result.question_intent
        assert 0.0 <= result.answer_pattern_match <= 1.0
        assert 0.0 <= result.topical_relevance <= 1.0
        assert 0.0 <= result.evidence_quality <= 1.0
        assert result.reasoning

    def test_v2_fields_present(self):
        """V2 adds semantic_match and topic_coverage fields."""
        gate = EvidenceSufficiencyGate()
        evidence = [
            MockEv(chunk_id="C50", document_id="D50", text="G3 is a revenue management system."),
        ]
        result = gate.check("What is G3?", evidence)
        assert hasattr(result, 'semantic_match')
        assert hasattr(result, 'topic_coverage')
        assert 0.0 <= result.semantic_match <= 1.0
        assert 0.0 <= result.topic_coverage <= 1.0


class TestAspectMismatchPenalty:
    """Test that aspect-mismatched evidence is penalized."""

    def test_programming_language_aspect_mismatch(self):
        """'What programming language is G3 written in?' — evidence discusses G3 but no programming info."""
        gate = EvidenceSufficiencyGate()
        evidence = [
            MockEv(
                chunk_id="C60", document_id="D60",
                text="G3 RMS processes rate decisions and sends them to the PMS. "
                     "The system handles data feeds from multiple sources.",
            ),
        ]
        result = gate.check("What programming language is G3 written in?", evidence)
        assert result.level == SufficiencyLevel.INSUFFICIENT
        assert result.should_abstain is True

    def test_cost_aspect_mismatch(self):
        """'What is the cost of OHIP installation?' — evidence mentions OHIP but no cost."""
        gate = EvidenceSufficiencyGate()
        evidence = [
            MockEv(
                chunk_id="C61", document_id="D61",
                text="OHIP installation requires configuring the PMS interface and "
                     "setting up the connection between Opera and IDeaS systems.",
            ),
        ]
        result = gate.check("What is the cost of OHIP installation?", evidence)
        assert result.level == SufficiencyLevel.INSUFFICIENT
        assert result.should_abstain is True

    def test_cost_aspect_match(self):
        """'What is the cost of OHIP installation?' — evidence DOES mention cost."""
        gate = EvidenceSufficiencyGate()
        evidence = [
            MockEv(
                chunk_id="C62", document_id="D62",
                text="OHIP installation costs approximately $5,000 per property. "
                     "The setup fee includes interface configuration and testing.",
            ),
        ]
        result = gate.check("What is the cost of OHIP installation?", evidence)
        assert result.level in (SufficiencyLevel.SUFFICIENT, SufficiencyLevel.PARTIAL)
        assert result.should_abstain is False


class TestCountQuestionPenalty:
    """Test that count questions without numbers are penalized."""

    def test_count_without_numbers(self):
        """'How many properties use G3 RMS?' — evidence mentions G3 but no numbers."""
        gate = EvidenceSufficiencyGate()
        evidence = [
            MockEv(
                chunk_id="C70", document_id="D70",
                text="G3 RMS is installed at various hotel properties worldwide. "
                     "The system supports rate management and pricing optimization.",
            ),
        ]
        result = gate.check("How many properties use G3 RMS globally?", evidence)
        assert result.level == SufficiencyLevel.INSUFFICIENT
        assert result.should_abstain is True

    def test_count_with_numbers(self):
        """'How many HR policy documents are there?' — evidence has count."""
        gate = EvidenceSufficiencyGate()
        evidence = [
            MockEv(
                chunk_id="C71", document_id="D71",
                text="There are 28 HR policy documents in the knowledge base, "
                     "covering adoption, benefits, performance review, and more.",
            ),
        ]
        result = gate.check("How many HR policy documents are there?", evidence)
        assert result.level in (SufficiencyLevel.SUFFICIENT, SufficiencyLevel.PARTIAL)
        assert result.should_abstain is False


class TestTopicCoverage:
    """Test that topic coverage across evidence chunks works."""

    def test_cross_document_coverage(self):
        """Evidence from multiple documents covers different aspects."""
        gate = EvidenceSufficiencyGate()
        evidence = [
            MockEv(
                chunk_id="C80", document_id="D80",
                text="G3 Data Feed Configuration: The G3 data feed connects to RMS systems.",
            ),
            MockEv(
                chunk_id="C81", document_id="D81",
                text="The configuration process involves setting up rate codes and "
                     "pricing rules for data synchronization.",
            ),
        ]
        result = gate.check("What is G3 Data Feed Configuration?", evidence)
        assert result.topic_coverage > 0.3
        assert result.level in (SufficiencyLevel.SUFFICIENT, SufficiencyLevel.PARTIAL)

    def test_single_term_coverage(self):
        """Evidence only covers one key term."""
        gate = EvidenceSufficiencyGate()
        evidence = [
            MockEv(
                chunk_id="C82", document_id="D82",
                text="The RMS system processes rate decisions.",
            ),
        ]
        result = gate.check("What is G3 Data Feed Configuration?", evidence)
        assert result.topic_coverage <= 0.5


class TestDefinitionBroadening:
    """Test that V2 definition patterns are broader."""

    def test_definition_with_colon_heading(self):
        """Evidence with term followed by colon (section heading style)."""
        gate = EvidenceSufficiencyGate()
        evidence = [
            MockEv(
                chunk_id="C90", document_id="D90",
                text="G3 Data Feed Configuration: Connects the G3 system to RMS "
                     "for rate synchronization and pricing management.",
            ),
        ]
        result = gate.check("What is G3 Data Feed Configuration?", evidence)
        assert result.level in (SufficiencyLevel.SUFFICIENT, SufficiencyLevel.PARTIAL)
        assert result.should_abstain is False

    def test_definition_with_substantive_discussion(self):
        """Evidence discusses a topic without 'is a' language."""
        gate = EvidenceSufficiencyGate()
        evidence = [
            MockEv(
                chunk_id="C91", document_id="D91",
                text="OHIP provides a bridge between Opera PMS and IDeaS RMS. "
                     "It enables real-time data synchronization for reservations "
                     "and room information.",
            ),
        ]
        result = gate.check("What is OHIP?", evidence)
        assert result.level in (SufficiencyLevel.SUFFICIENT, SufficiencyLevel.PARTIAL)
        assert result.should_abstain is False


class TestAdversarialQuestions:
    """Test adversarial/out-of-scope questions."""

    def test_irrelevant_question_with_frequent_words(self):
        """Question with words that exist in corpus but don't form a real question."""
        gate = EvidenceSufficiencyGate()
        evidence = [
            MockEv(
                chunk_id="C100", document_id="D100",
                text="The process involves configuring rate codes for the property.",
            ),
        ]
        result = gate.check("What is the process for doing the process?", evidence)
        # Should recognize this is not a meaningful question or abstain
        assert result.level != SufficiencyLevel.SUFFICIENT or result.score < 0.7

    def test_empty_evidence(self):
        gate = EvidenceSufficiencyGate()
        result = gate.check("What is G3 Data Feed Configuration?", [])
        assert result.level == SufficiencyLevel.INSUFFICIENT
        assert result.should_abstain is True
        assert result.reasoning == "No evidence provided"
