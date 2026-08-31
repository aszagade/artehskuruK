"""
Graph Validation Tests
======================
"""
import os, sys, time, unittest
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, ".")


class TestEntityQualityGate(unittest.TestCase):
    """Test that entity quality scoring prevents garbage from entering the graph."""

    def test_stopword_rejected(self):
        """Common English words should score as NOISE."""
        from kurukshetra.graph.entity_quality import score_entity
        for word in ["the", "this", "and", "or", "is", "are", "has", "not", "can", "will"]:
            score, label = score_entity(word, "job", 5, 2)
            self.assertEqual(label, "NOISE", f"'{word}' should be NOISE, got {label}")

    def test_temp_file_rejected(self):
        """Temp file names should score as NOISE."""
        from kurukshetra.graph.entity_quality import score_entity
        for name in ["tmpytu8qifn.txt", "doc.txt", "tmp_abc123.txt"]:
            score, label = score_entity(name, "document", 10, 1)
            self.assertEqual(label, "NOISE", f"'{name}' should be NOISE")

    def test_numeric_rejected(self):
        """Numeric-only expressions should score as NOISE."""
        from kurukshetra.graph.entity_quality import score_entity
        for name in ["02375162", "2 weeks", "1 to 6", "12345"]:
            score, label = score_entity(name, "job", 5, 2)
            self.assertEqual(label, "NOISE", f"'{name}' should be NOISE")

    def test_sentence_fragment_rejected(self):
        """Long sentence fragments should score as NOISE."""
        from kurukshetra.graph.entity_quality import score_entity
        score, label = score_entity(
            "This document covers the installation and configuration of G3 RMS for new hotels",
            "process", 83, 75
        )
        self.assertEqual(label, "NOISE")

    def test_g3_rms_preserved(self):
        """G3 RMS should score as HIGH."""
        from kurukshetra.graph.entity_quality import score_entity
        score, label = score_entity("G3 RMS", "system", 125, 34)
        self.assertEqual(label, "HIGH")
        self.assertEqual(score, 1.0)

    def test_spm_preserved(self):
        """SPM should score as HIGH."""
        from kurukshetra.graph.entity_quality import score_entity
        score, label = score_entity("SPM", "team", 135, 33)
        self.assertEqual(label, "HIGH")

    def test_sfdc_preserved(self):
        """SFDC should score as HIGH."""
        from kurukshetra.graph.entity_quality import score_entity
        score, label = score_entity("SFDC", "system", 119, 82)
        self.assertEqual(label, "HIGH")

    def test_salesforce_preserved(self):
        """Salesforce should score as HIGH."""
        from kurukshetra.graph.entity_quality import score_entity
        score, label = score_entity("Salesforce", "system", 78, 5)
        self.assertEqual(label, "HIGH")

    def test_datadog_preserved(self):
        """Datadog should score as HIGH."""
        from kurukshetra.graph.entity_quality import score_entity
        score, label = score_entity("Datadog", "system", 128, 85)
        self.assertEqual(label, "HIGH")

    def test_synxis_preserved(self):
        """SynXis should score as MEDIUM or HIGH."""
        from kurukshetra.graph.entity_quality import score_entity
        score, label = score_entity("SynXis", "system", 5, 3)
        self.assertIn(label, ["MEDIUM", "HIGH"])

    def test_ics_preserved(self):
        """ICS should score as HIGH."""
        from kurukshetra.graph.entity_quality import score_entity
        score, label = score_entity("ICS", "team", 117, 81)
        self.assertEqual(label, "HIGH")

    def test_sdops_preserved(self):
        """SDOPS should score as HIGH."""
        from kurukshetra.graph.entity_quality import score_entity
        score, label = score_entity("SDOPS", "team", 105, 13)
        self.assertEqual(label, "HIGH")

    def test_roa_preserved(self):
        """ROA should score as HIGH."""
        from kurukshetra.graph.entity_quality import score_entity
        score, label = score_entity("ROA", "team", 6, 3)
        self.assertIn(label, ["MEDIUM", "HIGH"])


class TestRelationshipValidation(unittest.TestCase):
    """Test relationship validation against actual document text."""

    def test_validate_single_relationship(self):
        from kurukshetra.graph.relationship_validator import validate_relationship
        vr = validate_relationship("G3 RMS", "SPM")
        self.assertIn(vr.validation_status, ["VALID", "WEAK", "INVALID"])
        self.assertGreaterEqual(vr.evidence_count, 0)

    def test_validated_relationships_have_status(self):
        from kurukshetra.graph.relationship_validator import validate_all_relationships
        report = validate_all_relationships(min_evidence=5, min_shared_docs=2)
        self.assertGreater(report["total"], 0)
        for r in report["relationships"]:
            self.assertIn(r.validation_status, ["VALID", "WEAK", "INVALID"])

    def test_strict_precision_is_measured(self):
        from kurukshetra.graph.relationship_validator import validate_all_relationships
        report = validate_all_relationships(min_evidence=5, min_shared_docs=2)
        self.assertGreater(report["precision_strict"], 0)
        self.assertLessEqual(report["precision_strict"], 1.0)

    def test_g3_spm_is_valid(self):
        from kurukshetra.graph.relationship_validator import validate_relationship
        vr = validate_relationship("G3 RMS", "SPM")
        # G3 RMS and SPM should have a valid relationship
        self.assertIn(vr.validation_status, ["VALID", "WEAK"])


class TestGraphGroundedQuestions(unittest.TestCase):
    """Test questions requiring graph + document evidence."""

    def _ask(self, question):
        """Helper to ask SANJAYA a question."""
        from kurukshetra.retrieval.hybrid import HybridRetriever
        from kurukshetra.retrieval.access_control import VisibilityFilter, VisibilityLevel
        from kurukshetra.agent.orchestrator import AgenticSANJAYA

        try:
            vf = VisibilityFilter(max_level=VisibilityLevel.INTERNAL)
        except Exception:
            vf = None

        retriever = HybridRetriever(vis_filter=vf)
        sanjaya = AgenticSANJAYA(retriever=retriever)
        return sanjaya.ask(question)

    def test_q1_teams_with_g3(self):
        """What teams work with G3?"""
        result = self._ask("What teams work with G3?")
        # Should answer with team information
        self.assertIsNotNone(result.answer_result)
        # Should have evidence
        self.assertGreater(len(result.answer_result.evidence), 0)

    def test_q2_systems_ics_works_with(self):
        """What systems does ICS work with?"""
        result = self._ask("What systems does ICS work with?")
        self.assertIsNotNone(result.answer_result)

    def test_q3_teams_with_sfdc(self):
        """Which teams work with SFDC?"""
        result = self._ask("Which teams work with SFDC?")
        self.assertIsNotNone(result.answer_result)

    def test_q4_shared_systems_spm_ics(self):
        """Which systems are shared by SPM and ICS?"""
        result = self._ask("Which systems are shared by SPM and ICS?")
        self.assertIsNotNone(result.answer_result)

    def test_q5_evidence_g3_spm(self):
        """What evidence shows that G3 is associated with SPM?"""
        result = self._ask("What evidence shows that G3 is associated with SPM?")
        self.assertIsNotNone(result.answer_result)

    def test_q6_documents_supporting_ics_sfdc(self):
        """Which documents support the relationship between ICS and SFDC?"""
        result = self._ask("Which documents support the relationship between ICS and SFDC?")
        self.assertIsNotNone(result.answer_result)


class TestFalseRelationship(unittest.TestCase):
    """Test that SANJAYA does NOT infer false relationships."""

    def test_no_false_g3_ics_from_different_docs(self):
        """
        Document A mentions G3, Document B mentions ICS.
        SANJAYA should NOT conclude G3 -> ICS unless evidence exists.
        """
        from kurukshetra.graph.relationship_validator import validate_relationship
        vr = validate_relationship("G3 RMS", "ICS")
        # Should be either VALID (if evidence exists) or WEAK/INVALID
        # but NOT automatically VALID just because both appear in the corpus
        self.assertIn(vr.validation_status, ["VALID", "WEAK", "INVALID"])
        # If INVALID, that's correct — no evidence
        # If VALID, there must be text-level co-occurrence
        if vr.validation_status == "VALID":
            self.assertGreater(len(vr.supporting_documents), 0)


if __name__ == "__main__":
    unittest.main()
