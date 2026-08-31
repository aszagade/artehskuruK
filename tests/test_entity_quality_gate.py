"""
Tests for Mission 3.56C — Ingestion Quality Gate Hardening

Verifies that:
  - Real organizational entities survive ingestion
  - Garbage entities are rejected at ingestion time
  - Quality scoring works correctly
  - The gate does not over-reject legitimate entities
"""

import pytest
from kurukshetra.graph.entity_quality import score_entity, STOPWORDS, NOISE_PATTERNS


class TestScoreEntity:
    """Test the score_entity function directly."""

    # --- Real entities should be HIGH or MEDIUM ---

    def test_g3_is_high(self):
        score, label = score_entity("G3", "system")
        assert label == "HIGH"
        assert score >= 0.7

    def test_spm_is_high(self):
        score, label = score_entity("SPM", "team")
        assert label == "HIGH"
        assert score >= 0.7

    def test_ics_is_high(self):
        score, label = score_entity("ICS", "team")
        assert label == "HIGH"

    def test_ohip_is_high(self):
        score, label = score_entity("OHIP", "system")
        assert label == "HIGH"

    def test_salesforce_is_high(self):
        score, label = score_entity("Salesforce", "system")
        assert label == "HIGH"

    def test_datadog_is_high(self):
        score, label = score_entity("Datadog", "system")
        assert label == "HIGH"

    def test_rms_is_high(self):
        score, label = score_entity("RMS", "system")
        assert label == "HIGH"

    def test_sdops_is_high(self):
        score, label = score_entity("SDOPS", "team")
        assert label == "HIGH"

    def test_roa_is_high(self):
        score, label = score_entity("ROA", "team")
        assert label == "HIGH"

    def test_synxis_is_high(self):
        score, label = score_entity("SynXis", "system")
        assert label == "HIGH"

    # --- Garbage entities should be NOISE ---

    def test_stopword_the_is_noise(self):
        score, label = score_entity("the", "job")
        assert label == "NOISE"

    def test_stopword_this_is_noise(self):
        score, label = score_entity("this", "process")
        assert label == "NOISE"

    def test_stopword_and_is_noise(self):
        score, label = score_entity("and", "job")
        assert label == "NOISE"

    def test_stopword_has_is_noise(self):
        score, label = score_entity("has", "job")
        assert label == "NOISE"

    def test_stopword_not_is_noise(self):
        score, label = score_entity("not", "job")
        assert label == "NOISE"

    def test_stopword_can_is_noise(self):
        score, label = score_entity("can", "job")
        assert label == "NOISE"

    def test_stopword_are_is_noise(self):
        score, label = score_entity("are", "job")
        assert label == "NOISE"

    def test_stopword_your_is_noise(self):
        score, label = score_entity("your", "job")
        assert label == "NOISE"

    def test_stopword_all_is_noise(self):
        score, label = score_entity("all", "job")
        assert label == "NOISE"

    def test_stopword_then_is_noise(self):
        score, label = score_entity("then", "job")
        assert label == "NOISE"

    def test_numeric_only_is_noise(self):
        score, label = score_entity("02375162", "job")
        assert label == "NOISE"

    def test_single_char_is_noise(self):
        score, label = score_entity("x", "process")
        assert label == "NOISE"

    def test_temp_file_is_noise(self):
        score, label = score_entity("tmpabc123.txt", "document")
        assert label == "NOISE"

    def test_sentence_fragment_is_noise(self):
        score, label = score_entity("This is a very long sentence fragment that should be rejected as noise", "process")
        assert label == "NOISE"

    def test_generic_word_failure_is_noise(self):
        score, label = score_entity("failure", "job")
        assert label in ("LOW", "NOISE")

    def test_generic_word_supports_is_noise(self):
        score, label = score_entity("supports", "job")
        assert label in ("LOW", "NOISE")

    # --- Acronym-style entities should survive ---

    def test_acronym_uppercase_short_survives(self):
        score, label = score_entity("IT", "team")
        # IT is a known entity
        assert label == "HIGH"

    def test_4_char_acronym_medium(self):
        score, label = score_entity("FOLS", "system")
        assert label == "HIGH"

    # --- Multi-word entities ---

    def test_g3_rms_is_high(self):
        score, label = score_entity("G3 RMS", "system")
        assert label == "HIGH"

    def test_property_setup_medium(self):
        score, label = score_entity("Property Setup", "process")
        assert label in ("MEDIUM", "HIGH")

    def test_data_feed_configuration_medium(self):
        score, label = score_entity("Data Feed Configuration", "configuration")
        assert label in ("MEDIUM", "HIGH")

    # --- Edge cases ---

    def test_empty_name_is_noise(self):
        score, label = score_entity("", "system")
        assert label == "NOISE"

    def test_whitespace_only_is_noise(self):
        score, label = score_entity("   ", "system")
        assert label == "NOISE"

    def test_short_lowercase_is_noise(self):
        score, label = score_entity("ab", "process")
        assert label == "NOISE"

    def test_date_like_is_noise(self):
        score, label = score_entity("3 days", "process")
        assert label == "NOISE"

    def test_range_expression_is_noise(self):
        score, label = score_entity("1 to 6", "process")
        assert label == "NOISE"
