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
