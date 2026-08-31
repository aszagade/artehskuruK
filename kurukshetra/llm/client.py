"""
GX10 LLM Client
================

OpenAI-compatible chat completion client for the GX10 endpoint.

Configuration via environment variables:
- GX10_BASE_URL: Base URL (e.g., http://172.26.120.11:4000/v1)
- GX10_API_KEY: API key for authentication
- GX10_MODEL: Model name (default: mistral-small)
- GX10_TIMEOUT: Request timeout in seconds (default: 30)
- GX10_MAX_TOKENS: Max tokens for completions (default: 1024)

Falls back to extractive answers when GX10 is unavailable.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Load .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Lazy import requests to avoid import-time failures
_requests = None


def _get_requests():
    global _requests
    if _requests is None:
        import requests as _r
        _requests = _r
    return _requests


# ==================================================================
# Configuration
# ==================================================================

@dataclass
class GX10Config:
    """GX10 client configuration, read from environment variables."""
    base_url: str = field(default_factory=lambda: os.environ.get("GX10_BASE_URL", ""))
    api_key: str = field(default_factory=lambda: os.environ.get("GX10_API_KEY", ""))
    model: str = field(default_factory=lambda: os.environ.get("GX10_MODEL", "mistral-small"))
    timeout: int = field(default_factory=lambda: int(os.environ.get("GX10_TIMEOUT", "30")))
    max_tokens: int = field(default_factory=lambda: int(os.environ.get("GX10_MAX_TOKENS", "1024")))
    temperature: float = field(default_factory=lambda: float(os.environ.get("GX10_TEMPERATURE", "0.1")))

    @property
    def is_configured(self) -> bool:
        """Whether GX10 is configured with a valid URL and API key."""
        return bool(self.base_url and self.api_key)

    @property
    def chat_url(self) -> str:
        """Full chat completions URL."""
        return f"{self.base_url.rstrip('/')}/chat/completions"


# ==================================================================
# Response Types
# ==================================================================

@dataclass
class ChatMessage:
    """A single chat message."""
    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class ChatCompletion:
    """Result of a chat completion request."""
    content: str
    model: str
    usage: dict = field(default_factory=dict)
    finish_reason: str = ""
    latency_ms: float = 0.0
    success: bool = True
    error: str = ""


# ==================================================================
# System Prompts
# ==================================================================

SYSTEM_PROMPT_GROUNDED = """You are SANJAYA, an enterprise knowledge assistant for IDeaS Revenue Management Solutions.

Your role is to answer questions using the provided evidence from the organization's knowledge base.

Rules:
1. Answer based on the provided evidence. Do not invent or assume facts not in the evidence.
2. You MAY synthesize information across multiple evidence sources when they collectively support an answer. For example, if Source 1 mentions G3 is used by the SPM team and Source 2 mentions G3 is used by the ICS team, you can conclude G3 spans both teams.
3. If the evidence genuinely does not contain information to answer, say "I don't have sufficient evidence to answer this question."
4. If evidence conflicts, present both perspectives and note the conflict.
5. Always cite your sources when referencing specific documents or facts.
6. Be concise and professional.
7. Use the exact terminology from the evidence (system names, process names, team names).
8. If a question is outside the scope of the evidence, say so clearly.
9. Do not provide general knowledge that is not in the evidence.
10. When evidence is distributed across multiple documents, synthesize it rather than saying insufficient evidence."""


# ==================================================================
# Client
# ==================================================================

class GX10Client:
    """
    OpenAI-compatible chat completion client for GX10.

    Usage:
        client = GX10Client()
        if client.is_available:
            result = client.chat(messages=[...])
    """

    def __init__(self, config: Optional[GX10Config] = None):
        self.config = config or GX10Config()
        self._stats = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_latency_ms": 0.0,
        }

    @property
    def is_available(self) -> bool:
        """Whether GX10 is configured and reachable."""
        return self.config.is_configured

    def chat(
        self,
        messages: list[ChatMessage],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> ChatCompletion:
        """
        Send a chat completion request to GX10.

        Args:
            messages: List of chat messages
            model: Override model (default from config)
            temperature: Override temperature
            max_tokens: Override max tokens

        Returns:
            ChatCompletion with the response or error
        """
        if not self.is_available:
            return ChatCompletion(
                content="",
                model="",
                success=False,
                error="GX10 not configured (missing GX10_BASE_URL or GX10_API_KEY)",
            )

        _requests = _get_requests()
        model = model or self.config.model
        temperature = temperature if temperature is not None else self.config.temperature
        max_tokens = max_tokens or self.config.max_tokens

        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        start = time.time()
        self._stats["total_calls"] += 1

        try:
            response = _requests.post(
                self.config.chat_url,
                json=payload,
                headers=headers,
                timeout=self.config.timeout,
            )
            latency_ms = (time.time() - start) * 1000
            self._stats["total_latency_ms"] += latency_ms

            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                usage = data.get("usage", {})
                finish = data.get("choices", [{}])[0].get("finish_reason", "")

                self._stats["successful_calls"] += 1
                return ChatCompletion(
                    content=content,
                    model=model,
                    usage=usage,
                    finish_reason=finish,
                    latency_ms=round(latency_ms, 1),
                    success=True,
                )
            else:
                error_msg = f"GX10 returned {response.status_code}: {response.text[:200]}"
                logger.warning(error_msg)
                self._stats["failed_calls"] += 1
                return ChatCompletion(
                    content="",
                    model=model,
                    latency_ms=round(latency_ms, 1),
                    success=False,
                    error=error_msg,
                )

        except Exception as e:
            latency_ms = (time.time() - start) * 1000
            self._stats["total_latency_ms"] += latency_ms
            self._stats["failed_calls"] += 1
            error_msg = f"GX10 request failed: {type(e).__name__}: {e}"
            logger.warning(error_msg)
            return ChatCompletion(
                content="",
                model=model,
                latency_ms=round(latency_ms, 1),
                success=False,
                error=error_msg,
            )

    def health_check(self) -> bool:
        """Check if GX10 is reachable and responding."""
        if not self.is_available:
            return False
        _requests = _get_requests()
        try:
            r = _requests.get(
                f"{self.config.base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {self.config.api_key}"},
                timeout=5,
            )
            return r.status_code == 200
        except Exception:
            return False

    @property
    def stats(self) -> dict:
        """Return client statistics."""
        return dict(self._stats)


# ==================================================================
# Singleton
# ==================================================================

_default_client: Optional[GX10Client] = None


def get_llm_client() -> GX10Client:
    """Get or create the default GX10 client singleton."""
    global _default_client
    if _default_client is None:
        _default_client = GX10Client()
    return _default_client
