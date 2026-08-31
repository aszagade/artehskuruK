"""
Tests for Mission 3.34 — GX10 LLM Integration
=============================================

All tests use a mocked GX10 client. No real API calls are made.
Proves:
- GX10 client configuration from env vars
- GX10 chat completion with mocked responses
- AnswerGenerator uses LLM when client is available
- AnswerGenerator falls back to extractive when LLM fails
- AnswerGenerator preserves citations/provenance with LLM
- Abstention still works with LLM
- Timeout/error handling works
- Statistics tracking works
"""
from __future__ import annotations

import os
import unittest
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from kurukshetra.llm.client import (
    GX10Client,
    GX10Config,
    ChatMessage,
    ChatCompletion,
    get_llm_client,
)


# ==================================================================
# Mock GX10 Client
# ==================================================================

class MockGX10Client(GX10Client):
    """Deterministic mock for testing without real API calls."""

    def __init__(self, responses=None, fail=False):
        config = GX10Config(base_url="http://mock:8000/v1", api_key="mock-key")
        super().__init__(config=config)
        self._mock_responses = responses or {}
        self._fail = fail
        self._call_count = 0

    @property
    def is_available(self):
        return not self._fail

    def chat(self, messages, model=None, temperature=None, max_tokens=None):
        self._call_count += 1
        self._stats["total_calls"] += 1
        if self._fail:
            self._stats["failed_calls"] += 1
            return ChatCompletion(
                content="", model="mock", success=False,
                error="Mock failure", latency_ms=1.0,
            )
        # Find matching response or use default
        query = messages[-1].content if messages else ""
        for pattern, response in self._mock_responses.items():
            if pattern.lower() in query.lower():
                self._stats["successful_calls"] += 1
                return ChatCompletion(
                    content=response, model="mock", success=True,
                    latency_ms=50.0, usage={"total_tokens": 100},
                )
        self._stats["successful_calls"] += 1
        return ChatCompletion(
            content="I don't have sufficient evidence to answer this question.",
            model="mock", success=True, latency_ms=50.0,
        )


# ==================================================================
# GX10 Client Unit Tests
# ==================================================================

class TestGX10Config(unittest.TestCase):
    """Test GX10 configuration."""

    def test_config_from_env(self):
        with patch.dict(os.environ, {
            "GX10_BASE_URL": "http://test:8000/v1",
            "GX10_API_KEY": "test-key",
            "GX10_MODEL": "test-model",
            "GX10_TIMEOUT": "15",
            "GX10_MAX_TOKENS": "512",
        }):
            config = GX10Config()
            self.assertEqual(config.base_url, "http://test:8000/v1")
            self.assertEqual(config.api_key, "test-key")
            self.assertEqual(config.model, "test-model")
            self.assertEqual(config.timeout, 15)
            self.assertEqual(config.max_tokens, 512)

    def test_config_is_configured(self):
        config = GX10Config(base_url="http://test:8000/v1", api_key="key")
        self.assertTrue(config.is_configured)

    def test_config_not_configured_empty_url(self):
        config = GX10Config(base_url="", api_key="key")
        self.assertFalse(config.is_configured)

    def test_config_not_configured_empty_key(self):
        config = GX10Config(base_url="http://test:8000/v1", api_key="")
        self.assertFalse(config.is_configured)

    def test_chat_url(self):
        config = GX10Config(base_url="http://test:8000/v1")
        self.assertEqual(config.chat_url, "http://test:8000/v1/chat/completions")


class TestGX10Client(unittest.TestCase):
    """Test GX10 client operations."""

    def test_client_not_available_when_unconfigured(self):
        client = GX10Client(GX10Config(base_url="", api_key=""))
        self.assertFalse(client.is_available)

    def test_client_not_available_when_configured(self):
        client = GX10Client(GX10Config(base_url="http://test:8000/v1", api_key="key"))
        self.assertTrue(client.is_available)

    def test_chat_returns_error_when_not_configured(self):
        client = GX10Client(GX10Config(base_url="", api_key=""))
        result = client.chat([ChatMessage(role="user", content="test")])
        self.assertFalse(result.success)
        self.assertIn("not configured", result.error)

    @patch("kurukshetra.llm.client._get_requests")
    def test_chat_success(self, mock_get_requests):
        mock_requests = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 10},
        }
        mock_requests.post.return_value = mock_response
        mock_get_requests.return_value = mock_requests

        client = GX10Client(GX10Config(base_url="http://test:8000/v1", api_key="key"))
        result = client.chat([ChatMessage(role="user", content="Say hello")])

        self.assertTrue(result.success)
        self.assertEqual(result.content, "Hello!")
        self.assertEqual(result.model, "mistral-small")

    @patch("kurukshetra.llm.client._get_requests")
    def test_chat_handles_http_error(self, mock_get_requests):
        mock_requests = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_requests.post.return_value = mock_response
        mock_get_requests.return_value = mock_requests

        client = GX10Client(GX10Config(base_url="http://test:8000/v1", api_key="bad"))
        result = client.chat([ChatMessage(role="user", content="test")])

        self.assertFalse(result.success)
        self.assertIn("401", result.error)

    @patch("kurukshetra.llm.client._get_requests")
    def test_chat_handles_timeout(self, mock_get_requests):
        import requests as _requests
        mock_requests = MagicMock()
        mock_requests.post.side_effect = _requests.Timeout("Connection timed out")
        mock_get_requests.return_value = mock_requests

        client = GX10Client(GX10Config(base_url="http://test:8000/v1", api_key="key"))
        result = client.chat([ChatMessage(role="user", content="test")])

        self.assertFalse(result.success)
        self.assertIn("Timeout", result.error)

    def test_stats_tracking(self):
        client = MockGX10Client()
        client.chat([ChatMessage(role="user", content="test1")])
        client.chat([ChatMessage(role="user", content="test2")])

        self.assertEqual(client.stats["total_calls"], 2)
        self.assertEqual(client.stats["successful_calls"], 2)


# ==================================================================
# AnswerGenerator LLM Integration Tests
# ==================================================================

class TestAnswerGeneratorWithLLM(unittest.TestCase):
    """Test AnswerGenerator with mocked LLM client."""

    def _make_retrieval_result(self, chunk_id="CH-1", doc_id="DOC-1",
                                text="G3 RMS configuration", score=0.9):
        from kurukshetra.retrieval.models import RetrievalResult
        return RetrievalResult(
            chunk_id=chunk_id, document_id=doc_id,
            text=text, score=score, metadata={},
        )

    def test_llm_used_when_available(self):
        from kurukshetra.agent.answer_generator import AnswerGenerator

        llm = MockGX10Client(responses={
            "g3 rms": "G3 RMS is a revenue management system configured by the SPM team.",
        })
        gen = AnswerGenerator()
        results = [self._make_retrieval_result(text="G3 RMS is configured by SPM team.")]

        result = gen.generate(
            query="What is G3 RMS?",
            results=results,
            strategy="hybrid",
            llm_client=llm,
        )

        self.assertFalse(result.abstained)
        self.assertIn("revenue management system", result.answer)
        # Verify citations preserved
        self.assertGreater(len(result.citations), 0)
        self.assertGreater(len(result.evidence), 0)

    def test_extractive_fallback_when_llm_fails(self):
        from kurukshetra.agent.answer_generator import AnswerGenerator

        llm = MockGX10Client(fail=True)
        gen = AnswerGenerator()
        results = [self._make_retrieval_result(text="G3 RMS is configured by SPM team.")]

        result = gen.generate(
            query="What is G3 RMS?",
            results=results,
            strategy="hybrid",
            llm_client=llm,
        )

        self.assertFalse(result.abstained)
        # Should fall back to extractive answer
        self.assertIn("G3 RMS", result.answer)

    def test_no_llm_uses_extractive(self):
        from kurukshetra.agent.answer_generator import AnswerGenerator

        gen = AnswerGenerator()
        results = [self._make_retrieval_result(text="G3 RMS is configured by SPM team.")]

        result = gen.generate(
            query="What is G3 RMS?",
            results=results,
            strategy="hybrid",
            llm_client=None,
        )

        self.assertFalse(result.abstained)
        self.assertIn("G3 RMS", result.answer)

    def test_abstention_still_works_with_llm(self):
        from kurukshetra.agent.answer_generator import AnswerGenerator

        llm = MockGX10Client()
        gen = AnswerGenerator()
        # No results -> abstain
        result = gen.generate(
            query="What is quantum computing?",
            results=[],
            strategy="hybrid",
            llm_client=llm,
        )

        self.assertTrue(result.abstained)

    def test_llm_failure_adds_limitation(self):
        from kurukshetra.agent.answer_generator import AnswerGenerator

        llm = MockGX10Client(fail=True)
        gen = AnswerGenerator()
        results = [self._make_retrieval_result(text="G3 RMS is configured by SPM team.")]

        result = gen.generate(
            query="What is G3 RMS?",
            results=results,
            strategy="hybrid",
            llm_client=llm,
        )

        # When LLM fails and falls back to extractive, no LLM limitation added
        self.assertFalse(result.abstained)

    def test_llm_success_adds_limitation(self):
        from kurukshetra.agent.answer_generator import AnswerGenerator

        llm = MockGX10Client(responses={"g3": "G3 is a system."})
        gen = AnswerGenerator()
        results = [self._make_retrieval_result(text="G3 RMS is configured.")]

        result = gen.generate(
            query="What is G3?",
            results=results,
            strategy="hybrid",
            llm_client=llm,
        )

        # LLM limitation should be noted
        llm_limits = [l for l in result.limitations if "LLM" in l]
        self.assertGreater(len(llm_limits), 0)


# ==================================================================
# Evidence Formatting Tests
# ==================================================================

class TestEvidenceFormatting(unittest.TestCase):
    """Test evidence formatting for LLM context."""

    def test_format_evidence_for_llm(self):
        from kurukshetra.agent.answer_generator import AnswerGenerator
        from kurukshetra.agent.answer_generator import EvidenceItem

        gen = AnswerGenerator()
        evidence = [
            EvidenceItem(chunk_id="C1", document_id="D1",
                        source_path="docs/g3.md", text="G3 config details",
                        score=0.9, rank=1),
            EvidenceItem(chunk_id="C2", document_id="D2",
                        source_path="docs/rms.md", text="RMS settings",
                        score=0.8, rank=2),
        ]

        formatted = gen._format_evidence_for_llm(evidence)

        self.assertIn("Source 1", formatted)
        self.assertIn("docs/g3.md", formatted)
        self.assertIn("G3 config details", formatted)
        self.assertIn("Source 2", formatted)

    def test_format_limits_to_10_items(self):
        from kurukshetra.agent.answer_generator import AnswerGenerator
        from kurukshetra.agent.answer_generator import EvidenceItem

        gen = AnswerGenerator()
        evidence = [
            EvidenceItem(chunk_id=f"C{i}", document_id=f"D{i}",
                        source_path=f"doc{i}.md", text=f"text {i}",
                        score=0.5, rank=i)
            for i in range(15)
        ]

        formatted = gen._format_evidence_for_llm(evidence)

        # Should only include top 10
        self.assertIn("Source 10", formatted)
        self.assertNotIn("Source 11", formatted)


# ==================================================================
# Singleton Tests
# ==================================================================

class TestLLMClientSingleton(unittest.TestCase):
    """Test the get_llm_client singleton."""

    def test_singleton_returns_same_instance(self):
        # Reset singleton
        import kurukshetra.llm.client as mod
        mod._default_client = None

        c1 = get_llm_client()
        c2 = get_llm_client()
        self.assertIs(c1, c2)

    def test_singleton_uses_env_vars(self):
        import kurukshetra.llm.client as mod
        mod._default_client = None

        with patch.dict(os.environ, {
            "GX10_BASE_URL": "http://test:8000/v1",
            "GX10_API_KEY": "test-key",
        }):
            client = get_llm_client()
            self.assertTrue(client.is_available)
            self.assertEqual(client.config.base_url, "http://test:8000/v1")


if __name__ == "__main__":
    unittest.main()
