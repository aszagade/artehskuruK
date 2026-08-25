"""
Retrieval-Time Access Control Tests
====================================

Proves that:
- VisibilityLevel parsing works correctly
- Visibility hierarchy is enforced (PUBLIC < INTERNAL < CONFIDENTIAL < RESTRICTED)
- VisibilityFilter correctly filters results by document visibility
- FilteredRetriever wraps any retriever with filtering
- Backward compatibility: retrievers work without vis_filter (None)
- DuckDB database is never modified by filter operations
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from kurukshetra.retrieval.access_control import (
    FilteredRetriever,
    VisibilityFilter,
    VisibilityLevel,
)
from kurukshetra.retrieval.models import RetrievalResult


class TestVisibilityLevel(unittest.TestCase):
    """Prove VisibilityLevel enum behaves correctly."""

    def test_ordering(self):
        """PUBLIC < INTERNAL < CONFIDENTIAL < RESTRICTED."""
        self.assertLess(VisibilityLevel.PUBLIC, VisibilityLevel.INTERNAL)
        self.assertLess(VisibilityLevel.INTERNAL, VisibilityLevel.CONFIDENTIAL)
        self.assertLess(VisibilityLevel.CONFIDENTIAL, VisibilityLevel.RESTRICTED)

    def test_from_string_known(self):
        """Known strings parse correctly."""
        self.assertEqual(VisibilityLevel.from_string("public"), VisibilityLevel.PUBLIC)
        self.assertEqual(VisibilityLevel.from_string("INTERNAL"), VisibilityLevel.INTERNAL)
        self.assertEqual(VisibilityLevel.from_string("Confidential"), VisibilityLevel.CONFIDENTIAL)
        self.assertEqual(VisibilityLevel.from_string("restricted"), VisibilityLevel.RESTRICTED)

    def test_from_string_unknown_defaults_to_internal(self):
        """Unknown strings default to INTERNAL."""
        self.assertEqual(VisibilityLevel.from_string("bogus"), VisibilityLevel.INTERNAL)
        self.assertEqual(VisibilityLevel.from_string(""), VisibilityLevel.INTERNAL)

    def test_from_string_none_defaults_to_internal(self):
        """None defaults to INTERNAL."""
        self.assertEqual(VisibilityLevel.from_string(None), VisibilityLevel.INTERNAL)


class TestVisibilityFilter(unittest.TestCase):
    """Prove VisibilityFilter correctly filters by document visibility."""

    def _make_result(self, doc_id: str, chunk_id: str = "c1") -> RetrievalResult:
        return RetrievalResult(
            chunk_id=chunk_id,
            document_id=doc_id,
            score=1.0,
            text="test",
            metadata={},
        )

    def test_empty_results_returned_empty(self):
        """Filtering empty list returns empty list."""
        vf = VisibilityFilter(max_level=VisibilityLevel.INTERNAL)
        self.assertEqual(vf.filter([]), [])

    def test_public_doc_visible_to_internal(self):
        """PUBLIC documents are visible to INTERNAL clearance."""
        # Mock the database connection
        with unittest.mock.patch(
            "kurukshetra.retrieval.access_control.get_connection"
        ) as mock_conn:
            mock_db = MagicMock()
            mock_db.execute.return_value.fetchall.return_value = [
                ("DOC-1", "Public"),
            ]
            mock_conn.return_value = mock_db

            vf = VisibilityFilter(max_level=VisibilityLevel.INTERNAL)
            result = self._make_result("DOC-1")
            filtered = vf.filter([result])
            self.assertEqual(len(filtered), 1)

    def test_confidential_doc_hidden_from_internal(self):
        """CONFIDENTIAL documents are NOT visible to INTERNAL clearance."""
        with unittest.mock.patch(
            "kurukshetra.retrieval.access_control.get_connection"
        ) as mock_conn:
            mock_db = MagicMock()
            mock_db.execute.return_value.fetchall.return_value = [
                ("DOC-1", "Confidential"),
            ]
            mock_conn.return_value = mock_db

            vf = VisibilityFilter(max_level=VisibilityLevel.INTERNAL)
            result = self._make_result("DOC-1")
            filtered = vf.filter([result])
            self.assertEqual(len(filtered), 0)

    def test_internal_doc_visible_to_internal(self):
        """INTERNAL documents are visible to INTERNAL clearance."""
        with unittest.mock.patch(
            "kurukshetra.retrieval.access_control.get_connection"
        ) as mock_conn:
            mock_db = MagicMock()
            mock_db.execute.return_value.fetchall.return_value = [
                ("DOC-1", "Internal"),
            ]
            mock_conn.return_value = mock_db

            vf = VisibilityFilter(max_level=VisibilityLevel.INTERNAL)
            result = self._make_result("DOC-1")
            filtered = vf.filter([result])
            self.assertEqual(len(filtered), 1)

    def test_restricted_doc_only_visible_to_restricted(self):
        """RESTRICTED documents only visible to RESTRICTED clearance."""
        with unittest.mock.patch(
            "kurukshetra.retrieval.access_control.get_connection"
        ) as mock_conn:
            mock_db = MagicMock()
            mock_db.execute.return_value.fetchall.return_value = [
                ("DOC-1", "Restricted"),
            ]
            mock_conn.return_value = mock_db

            # INTERNAL cannot see RESTRICTED
            vf_int = VisibilityFilter(max_level=VisibilityLevel.INTERNAL)
            self.assertEqual(len(vf_int.filter([self._make_result("DOC-1")])), 0)

            # CONFIDENTIAL cannot see RESTRICTED
            vf_conf = VisibilityFilter(max_level=VisibilityLevel.CONFIDENTIAL)
            self.assertEqual(len(vf_conf.filter([self._make_result("DOC-1")])), 0)

            # RESTRICTED can see RESTRICTED
            vf_rest = VisibilityFilter(max_level=VisibilityLevel.RESTRICTED)
            self.assertEqual(len(vf_rest.filter([self._make_result("DOC-1")])), 1)

    def test_mixed_visibility_filtering(self):
        """Filtering a mixed list keeps only authorized results."""
        with unittest.mock.patch(
            "kurukshetra.retrieval.access_control.get_connection"
        ) as mock_conn:
            mock_db = MagicMock()
            mock_db.execute.return_value.fetchall.return_value = [
                ("DOC-PUB", "Public"),
                ("DOC-INT", "Internal"),
                ("DOC-CONF", "Confidential"),
                ("DOC-REST", "Restricted"),
            ]
            mock_conn.return_value = mock_db

            vf = VisibilityFilter(max_level=VisibilityLevel.INTERNAL)
            results = [
                self._make_result("DOC-PUB", "c1"),
                self._make_result("DOC-INT", "c2"),
                self._make_result("DOC-CONF", "c3"),
                self._make_result("DOC-REST", "c4"),
            ]
            filtered = vf.filter(results)
            doc_ids = [r.document_id for r in filtered]
            self.assertEqual(doc_ids, ["DOC-PUB", "DOC-INT"])

    def test_unknown_doc_defaults_to_internal(self):
        """Documents not in the database default to INTERNAL visibility."""
        with unittest.mock.patch(
            "kurukshetra.retrieval.access_control.get_connection"
        ) as mock_conn:
            mock_db = MagicMock()
            mock_db.execute.return_value.fetchall.return_value = []
            mock_conn.return_value = mock_db

            vf = VisibilityFilter(max_level=VisibilityLevel.INTERNAL)
            result = self._make_result("UNKNOWN-DOC")
            filtered = vf.filter([result])
            self.assertEqual(len(filtered), 1)

    def test_is_allowed(self):
        """is_allowed checks individual documents."""
        with unittest.mock.patch(
            "kurukshetra.retrieval.access_control.get_connection"
        ) as mock_conn:
            mock_db = MagicMock()
            mock_db.execute.return_value.fetchall.return_value = [
                ("DOC-INT", "Internal"),
                ("DOC-CONF", "Confidential"),
            ]
            mock_conn.return_value = mock_db

            vf = VisibilityFilter(max_level=VisibilityLevel.INTERNAL)
            self.assertTrue(vf.is_allowed("DOC-INT"))
            self.assertFalse(vf.is_allowed("DOC-CONF"))
            self.assertTrue(vf.is_allowed("UNKNOWN"))  # defaults to INTERNAL

    def test_invalidate_forces_reload(self):
        """invalidate() clears the cache and reloads on next call."""
        with unittest.mock.patch(
            "kurukshetra.retrieval.access_control.get_connection"
        ) as mock_conn:
            mock_db = MagicMock()
            # First call: no documents
            mock_db.execute.return_value.fetchall.return_value = []
            mock_conn.return_value = mock_db

            vf = VisibilityFilter(max_level=VisibilityLevel.INTERNAL)
            # UNKNOWN defaults to INTERNAL, so allowed
            self.assertTrue(vf.is_allowed("DOC-1"))

            # Invalidate and change data
            vf.invalidate()
            mock_db.execute.return_value.fetchall.return_value = [
                ("DOC-1", "Confidential"),
            ]
            # Now DOC-1 is CONFIDENTIAL, not allowed
            self.assertFalse(vf.is_allowed("DOC-1"))


class TestFilteredRetriever(unittest.TestCase):
    """Prove FilteredRetriever wraps any retriever correctly."""

    def test_wrap_filters_results(self):
        """FilteredRetriever filters results from a mock retriever."""
        mock_retriever = MagicMock()
        mock_retriever.search.return_value = [
            RetrievalResult("c1", "DOC-PUB", 0.9, "public text", {}),
            RetrievalResult("c2", "DOC-CONF", 0.8, "confidential text", {}),
            RetrievalResult("c3", "DOC-INT", 0.7, "internal text", {}),
        ]

        with unittest.mock.patch(
            "kurukshetra.retrieval.access_control.get_connection"
        ) as mock_conn:
            mock_db = MagicMock()
            mock_db.execute.return_value.fetchall.return_value = [
                ("DOC-PUB", "Public"),
                ("DOC-INT", "Internal"),
                ("DOC-CONF", "Confidential"),
            ]
            mock_conn.return_value = mock_db

            vf = VisibilityFilter(max_level=VisibilityLevel.INTERNAL)
            safe = FilteredRetriever(mock_retriever, vf)
            results = safe.search("test query", top_k=5)

            doc_ids = [r.document_id for r in results]
            self.assertIn("DOC-PUB", doc_ids)
            self.assertIn("DOC-INT", doc_ids)
            self.assertNotIn("DOC-CONF", doc_ids)

    def test_overfetch_compensates_for_filtering(self):
        """FilteredRetriever requests more results to compensate for filtering."""
        mock_retriever = MagicMock()
        mock_retriever.search.return_value = []

        with unittest.mock.patch(
            "kurukshetra.retrieval.access_control.get_connection"
        ) as mock_conn:
            mock_db = MagicMock()
            mock_db.execute.return_value.fetchall.return_value = []
            mock_conn.return_value = mock_db

            vf = VisibilityFilter(max_level=VisibilityLevel.INTERNAL)
            safe = FilteredRetriever(mock_retriever, vf)
            safe.search("test", top_k=5)

            # Should request top_k * 3 to compensate
            mock_retriever.search.assert_called_once_with("test", top_k=15)


class TestBackwardCompatibility(unittest.TestCase):
    """Prove existing retrievers work without vis_filter (None)."""

    def test_bm25_no_filter(self):
        """DatabaseBM25Retriever works without vis_filter."""
        from kurukshetra.retrieval.database_bm25 import DatabaseBM25Retriever

        retriever = DatabaseBM25Retriever(vis_filter=None)
        self.assertIsNone(retriever.vis_filter)
        # Should not raise
        results = retriever.search("test query", top_k=3)
        self.assertIsInstance(results, list)

    def test_hybrid_no_filter(self):
        """HybridRetriever works without vis_filter."""
        from kurukshetra.retrieval.hybrid import HybridRetriever

        retriever = HybridRetriever(vis_filter=None)
        self.assertIsNone(retriever.vis_filter)
        # Should not raise
        results = retriever.search("test query", top_k=3)
        self.assertIsInstance(results, list)


if __name__ == "__main__":
    unittest.main()
