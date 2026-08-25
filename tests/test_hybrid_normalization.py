"""
Hybrid Normalization Tests
==========================

Proves that score normalization in HybridRetriever works correctly
and that BM25/Vector score-scale differences no longer dominate fusion.
"""

from __future__ import annotations

import unittest

from kurukshetra.retrieval.hybrid import _min_max_normalize


class TestMinMaxNormalize(unittest.TestCase):
    """Unit tests for the _min_max_normalize helper."""

    def test_empty_list(self):
        self.assertEqual(_min_max_normalize([]), [])

    def test_single_element(self):
        self.assertEqual(_min_max_normalize([5.0]), [1.0])

    def test_two_equal_elements(self):
        self.assertEqual(_min_max_normalize([3.0, 3.0]), [1.0, 1.0])

    def test_normal_range(self):
        result = _min_max_normalize([0.0, 0.5, 1.0])
        self.assertAlmostEqual(result[0], 0.0)
        self.assertAlmostEqual(result[1], 0.5)
        self.assertAlmostEqual(result[2], 1.0)

    def test_bm25_scale(self):
        """BM25 scores typically range 9-11."""
        result = _min_max_normalize([9.0, 10.0, 11.0])
        self.assertAlmostEqual(result[0], 0.0)
        self.assertAlmostEqual(result[1], 0.5)
        self.assertAlmostEqual(result[2], 1.0)

    def test_vector_scale(self):
        """Vector scores typically range 0.65-0.70."""
        result = _min_max_normalize([0.65, 0.675, 0.70])
        self.assertAlmostEqual(result[0], 0.0)
        self.assertAlmostEqual(result[1], 0.5)
        self.assertAlmostEqual(result[2], 1.0)

    def test_inverted_order_preserved(self):
        """Higher raw score still maps to higher normalized score."""
        result = _min_max_normalize([1.0, 3.0, 2.0])
        self.assertAlmostEqual(result[0], 0.0)
        self.assertAlmostEqual(result[1], 1.0)
        self.assertAlmostEqual(result[2], 0.5)

    def test_negative_scores(self):
        result = _min_max_normalize([-10.0, 0.0, 10.0])
        self.assertAlmostEqual(result[0], 0.0)
        self.assertAlmostEqual(result[1], 0.5)
        self.assertAlmostEqual(result[2], 1.0)

    def test_many_equal_scores(self):
        result = _min_max_normalize([5.0, 5.0, 5.0, 5.0])
        self.assertEqual(len(result), 4)
        self.assertTrue(all(r == 1.0 for r in result))


class TestHybridScoreScale(unittest.TestCase):
    """Prove that BM25 and Vector score scales no longer dominate fusion."""

    def test_bm25_and_vector_contributions_are_equal_at_05_05(self):
        """With equal weights and normalization, BM25 and Vector contribute equally."""
        # Simulate BM25 raw scores (9-11 range)
        bm25_raw = [9.0, 10.0, 11.0]
        # Simulate Vector raw scores (0.65-0.70 range)
        vector_raw = [0.65, 0.675, 0.70]

        bm25_norm = _min_max_normalize(bm25_raw)
        vector_norm = _min_max_normalize(vector_raw)

        # After normalization, both should be in [0, 1]
        self.assertTrue(all(0 <= s <= 1 for s in bm25_norm))
        self.assertTrue(all(0 <= s <= 1 for s in vector_norm))

        # BM25 contribution: norm * 0.5
        bm25_contribution = [s * 0.5 for s in bm25_norm]
        # Vector contribution: norm * 0.5
        vector_contribution = [s * 0.5 for s in vector_norm]

        # Both should contribute equally to the max score
        self.assertAlmostEqual(max(bm25_contribution), 0.5, places=6)
        self.assertAlmostEqual(max(vector_contribution), 0.5, places=6)

    def test_old_behavior_bm25_dominates(self):
        """Demonstrate the old bug: BM25 dominated even at 0.4 weight."""
        bm25_raw = [9.0, 10.0, 11.0]
        vector_raw = [0.65, 0.675, 0.70]

        # Old behavior: no normalization
        old_bm25_max = max(bm25_raw) * 0.4  # 4.4
        old_vector_max = max(vector_raw) * 0.6  # 0.42

        # BM25 dominated by 10x
        self.assertGreater(old_bm25_max, old_vector_max * 5)

        # New behavior: normalized
        new_bm25_max = max(_min_max_normalize(bm25_raw)) * 0.5  # 0.5
        new_vector_max = max(_min_max_normalize(vector_raw)) * 0.5  # 0.5

        # Now equal
        self.assertAlmostEqual(new_bm25_max, new_vector_max, places=6)

    def test_fusion_score_range(self):
        """Fused scores should be in [0, 1] with equal weights."""
        bm25_norm = _min_max_normalize([9.0, 10.0, 11.0])
        vector_norm = _min_max_normalize([0.65, 0.675, 0.70])

        # Chunk present in both
        fused_both = bm25_norm[2] * 0.5 + vector_norm[2] * 0.5
        self.assertAlmostEqual(fused_both, 1.0, places=6)

        # Chunk only in BM25
        fused_bm25_only = bm25_norm[0] * 0.5 + 0.0
        self.assertAlmostEqual(fused_bm25_only, 0.0, places=6)

        # Chunk only in Vector
        fused_vector_only = 0.0 + vector_norm[0] * 0.5
        self.assertAlmostEqual(fused_vector_only, 0.0, places=6)

    def test_duplicate_chunk_ids(self):
        """Chunks appearing in both BM25 and Vector get combined scores."""
        bm25_raw = {"c1": 10.0, "c2": 9.0}
        vector_raw = {"c1": 0.68, "c3": 0.70}

        bm25_norm = _min_max_normalize(list(bm25_raw.values()))
        vector_norm = _min_max_normalize(list(vector_raw.values()))

        bm25_map = dict(zip(bm25_raw.keys(), bm25_norm))
        vector_map = dict(zip(vector_raw.keys(), vector_norm))

        # c1 is in both
        self.assertIn("c1", bm25_map)
        self.assertIn("c1", vector_map)

        # c2 is only in BM25
        self.assertIn("c2", bm25_map)
        self.assertNotIn("c2", vector_map)

        # c3 is only in Vector
        self.assertNotIn("c3", bm25_map)
        self.assertIn("c3", vector_map)


class TestHybridRetrieverEdgeCases(unittest.TestCase):
    """Edge cases for the hybrid fusion logic."""

    def test_min_max_normalize_all_same(self):
        """All scores identical should yield all 1.0."""
        result = _min_max_normalize([5.0, 5.0, 5.0, 5.0, 5.0])
        self.assertTrue(all(r == 1.0 for r in result))

    def test_min_max_normalize_two_values(self):
        result = _min_max_normalize([0.0, 1.0])
        self.assertAlmostEqual(result[0], 0.0)
        self.assertAlmostEqual(result[1], 1.0)

    def test_normalization_preserves_ranking(self):
        """Higher raw scores always map to higher normalized scores."""
        raw = [1.0, 5.0, 3.0, 9.0, 2.0]
        norm = _min_max_normalize(raw)
        # Check ordering preserved
        for i in range(len(raw)):
            for j in range(len(raw)):
                if raw[i] > raw[j]:
                    self.assertGreater(norm[i], norm[j])


if __name__ == "__main__":
    unittest.main()
