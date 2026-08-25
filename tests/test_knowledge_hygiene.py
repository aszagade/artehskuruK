"""
Knowledge Hygiene Tests
=======================

Proves that the graph extractor filters out:
- NaN/None artifacts from spreadsheets
- Empty/whitespace-only entity names
- Newline-containing names
- Names shorter than 3 characters
- Names that are only numbers/special chars
"""

from __future__ import annotations

import unittest

from kurukshetra.graph.extractor import SmartEntityExtractor


class TestEntityNameValidation(unittest.TestCase):
    """Prove _is_valid_entity_name rejects artifacts."""

    def setUp(self):
        self.extractor = SmartEntityExtractor()

    def test_nan_rejected(self):
        """NaN should be rejected."""
        self.assertFalse(self.extractor._is_valid_entity_name("NaN"))

    def test_nan_variants_rejected(self):
        """Various NaN patterns should be rejected."""
        self.assertFalse(self.extractor._is_valid_entity_name("nan"))
        self.assertFalse(self.extractor._is_valid_entity_name("N/A"))
        self.assertFalse(self.extractor._is_valid_entity_name("None"))
        self.assertFalse(self.extractor._is_valid_entity_name("null"))
        self.assertFalse(self.extractor._is_valid_entity_name("--"))
        self.assertFalse(self.extractor._is_valid_entity_name("-"))

    def test_nan_pattern_rejected(self):
        """Multi-word NaN patterns should be rejected."""
        self.assertFalse(self.extractor._is_valid_entity_name("NaN NaN NaN"))
        self.assertFalse(self.extractor._is_valid_entity_name("NaN NaN NaN NaN\n NaN b"))

    def test_newline_rejected(self):
        """Names with newlines should be rejected."""
        self.assertFalse(self.extractor._is_valid_entity_name("Guide\nAccor Client"))
        self.assertFalse(self.extractor._is_valid_entity_name("for SAS\nPost a shift"))

    def test_short_names_rejected(self):
        """Very short names should be rejected."""
        self.assertFalse(self.extractor._is_valid_entity_name("ab"))
        self.assertFalse(self.extractor._is_valid_entity_name("x"))
        self.assertFalse(self.extractor._is_valid_entity_name(""))

    def test_whitespace_only_rejected(self):
        """Whitespace-only names should be rejected."""
        self.assertFalse(self.extractor._is_valid_entity_name("   "))
        self.assertFalse(self.extractor._is_valid_entity_name("\t\n"))

    def test_valid_names_accepted(self):
        """Real entity names should be accepted."""
        self.assertTrue(self.extractor._is_valid_entity_name("G3 RMS"))
        self.assertTrue(self.extractor._is_valid_entity_name("SFDC Workflow"))
        self.assertTrue(self.extractor._is_valid_entity_name("Data Feed Configuration"))
        self.assertTrue(self.extractor._is_valid_entity_name("Ajay Gandhi"))
        self.assertTrue(self.extractor._is_valid_entity_name("Opera Cloud Agent"))
        self.assertTrue(self.extractor._is_valid_entity_name("EDF"))
        self.assertTrue(self.extractor._is_valid_entity_name("SFTP"))

    def test_nan_in_long_name_accepted(self):
        """Names containing nan as part of a real word should be accepted."""
        self.assertTrue(self.extractor._is_valid_entity_name("Nano Technology"))
        self.assertTrue(self.extractor._is_valid_entity_name("Nanjing Process"))


class TestExtractionFiltersArtifacts(unittest.TestCase):
    """Prove the extractor does not create artifact entities."""

    def test_no_nan_entities_from_spreadsheet_text(self):
        """Spreadsheet column headers with NaN should not create entities."""
        extractor = SmartEntityExtractor()
        # Simulate text from a spreadsheet with NaN column values
        text = (
            "Step 1: Login to G3 RMS\n"
            "NaN NaN NaN NaN\n"
            "NaN b\n"
            "Configure SFDC workflow\n"
            "Property configuration complete"
        )
        result = extractor.extract_from_document(
            text=text,
            document_id="TEST-001",
            document_title="Test Document",
        )

        entity_names = [e.name for e in result.entities]
        # Should not contain NaN artifacts
        for name in entity_names:
            self.assertNotIn("NaN", name,
                f"NaN artifact found in entity: {name}")
            self.assertNotIn("\n", name,
                f"Newline found in entity: {name}")

    def test_valid_entities_extracted(self):
        """Real system names should still be extracted."""
        extractor = SmartEntityExtractor()
        text = (
            "This document describes G3 RMS configuration for SFDC integration. "
            "The Data Feed process uses Datadog for monitoring. "
            "Contact Ajay Gandhi for configuration issues."
        )
        result = extractor.extract_from_document(
            text=text,
            document_id="TEST-002",
            document_title="Test Config",
        )

        entity_names = [e.name for e in result.entities]
        # Should find G3 RMS and SFDC
        found_g3 = any("G3" in n for n in entity_names)
        found_sfdc = any("SFDC" in n for n in entity_names)
        self.assertTrue(found_g3, f"G3 not found in: {entity_names}")
        self.assertTrue(found_sfdc, f"SFDC not found in: {entity_names}")




class TestUnknownTermNoiseFilter(unittest.TestCase):
    """Prove the GlossaryManager filters noise from unknown terms."""

    def setUp(self):
        from kurukshetra.services.glossary import GlossaryManager
        self.gm = GlossaryManager()

    def test_known_acronyms_filtered(self):
        """Known IDeaS acronyms should not appear as unknown terms."""
        text = "CARE handles ICS cases. CPM and ISM verify EDF SFTP connections."
        unknown = self.gm.detect_unknown_terms(text, "test-known")
        terms = {u.term for u in unknown}
        for known in ["CARE", "ICS", "CPM", "ISM", "EDF", "SFTP", "BDE", "RRA", "OCIM"]:
            self.assertNotIn(known, terms, f"{known} should not be unknown")

    def test_common_english_filtered(self):
        """Common English words should not appear as unknown terms."""
        text = "OPEN the CASE in PHASE 2. VENDOR status is OLDER."
        unknown = self.gm.detect_unknown_terms(text, "test-english")
        terms = {u.term for u in unknown}
        for word in ["OPEN", "CASE", "PHASE", "VENDOR", "OLDER"]:
            self.assertNotIn(word, terms, f"{word} should not be unknown")

    def test_field_names_filtered(self):
        """Spreadsheet column headers should not appear as unknown terms."""
        text = "Case Owner: John. Case Opens: Jan 1. Date Assigned: Feb 2."
        unknown = self.gm.detect_unknown_terms(text, "test-fields")
        terms = {u.term for u in unknown}
        for field in ["Case Owner", "Case Opens", "Date Assigned"]:
            self.assertNotIn(field, terms, f"{field} should not be unknown")

    def test_multi_line_garbage_filtered(self):
        """Terms containing newlines should be rejected."""
        text = "Team\nPricing Troubleshooting Process"
        unknown = self.gm.detect_unknown_terms(text, "test-multiline")
        terms = {u.term for u in unknown}
        for t in terms:
            self.assertNotIn("\n", t, f"Multi-line term leaked: {t!r}")

    def test_date_patterns_filtered(self):
        """Date patterns should not appear as unknown terms."""
        text = "YYYY-MM-DD format. DD-MM-YYYY. HH:MM timestamp."
        unknown = self.gm.detect_unknown_terms(text, "test-dates")
        terms = {u.term for u in unknown}
        for pattern in ["YYYY-MM-DD", "DD-MM-YYYY", "HH:MM"]:
            self.assertNotIn(pattern, terms, f"{pattern} should not be unknown")

    def test_real_terms_detected(self):
        """Real unknown terms should still be detected."""
        text = "Data Feed Configuration Client setup uses QuantumBridge."
        unknown = self.gm.detect_unknown_terms(text, "test-real")
        terms = {u.term for u in unknown}
        self.assertTrue(len(terms) > 0, "Should detect at least one real unknown term")

    def test_noise_term_checker(self):
        """_is_noise_term should reject known noise patterns."""
        from kurukshetra.services.glossary import GlossaryManager
        self.assertTrue(GlossaryManager._is_noise_term("YYYY-MM-DD"))
        self.assertTrue(GlossaryManager._is_noise_term("TRUE"))
        self.assertTrue(GlossaryManager._is_noise_term("NaN"))
        self.assertTrue(GlossaryManager._is_noise_term("--- Sheet1 ---"))
        self.assertTrue(GlossaryManager._is_noise_term("line1\nline2"))
        self.assertFalse(GlossaryManager._is_noise_term("QuantumBridge"))
        self.assertFalse(GlossaryManager._is_noise_term("G3 RMS"))

    def test_is_noise_term_date_variants(self):
        """Various date placeholder patterns should be noise."""
        from kurukshetra.services.glossary import GlossaryManager
        self.assertTrue(GlossaryManager._is_noise_term("YYYY"))
        self.assertTrue(GlossaryManager._is_noise_term("MM-DD"))
        self.assertTrue(GlossaryManager._is_noise_term("HH:MM:SS"))


if __name__ == "__main__":
    unittest.main()
