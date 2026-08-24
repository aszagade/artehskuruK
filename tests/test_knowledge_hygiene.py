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


if __name__ == "__main__":
    unittest.main()
