"""LLM provider clients.

Default provider: Groq (llama-3.3-70b-versatile).
Swap by implementing the LLMClient protocol and passing it to RecommendationEngine.

Environment variables:
  GROQ_API_KEY   – Groq API key (required unless MOCK_LLM=1)
  GROQ_MODEL     – Override the default Groq model id
  MOCK_LLM       – Set to "1" to skip Groq and use rule-based fallback
"""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


class LLMError(Exception):
    """Raised when the LLM provider cannot fulfil a request."""


@runtime_checkable
class LLMClient(Protocol):
    """Minimal interface every LLM adapter must implement."""

    def complete(self, messages: List[Dict[str, str]]) -> str:
        """Send messages; return raw response text (JSON expected)."""
        ...


# ---------------------------------------------------------------------------
# Mock client (tests / offline demo)
# ---------------------------------------------------------------------------

class MockLLMClient:
    """Deterministic client that returns a fixed response — for tests."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: List[List[Dict[str, str]]] = []

    def complete(self, messages: List[Dict[str, str]]) -> str:
        self.calls.append(messages)
        return self.response


# ---------------------------------------------------------------------------
# Groq client
# ---------------------------------------------------------------------------

class GroqClient:
    """Groq Chat Completions adapter using the official groq Python SDK."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key or _resolve_api_key()
        self.model = model or os.getenv("GROQ_MODEL") or DEFAULT_GROQ_MODEL
        self.timeout = timeout

        if not self.api_key:
            raise LLMError(
                "GROQ_API_KEY is not set. "
                "Export it or add it to .env, or set MOCK_LLM=1 for offline mode."
            )

    def complete(self, messages: List[Dict[str, str]]) -> str:
        try:
            from groq import Groq
        except ImportError as exc:
            raise LLMError(
                "groq package not found. Install it: pip install groq"
            ) from exc

        client = Groq(api_key=self.api_key, timeout=self.timeout)
        logger.debug("Groq request: model=%s, messages=%d", self.model, len(messages))

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            logger.warning("Groq API error: %s", exc)
            raise LLMError(str(exc)) from exc

        content = response.choices[0].message.content
        if not content:
            raise LLMError("Groq returned an empty response.")

        logger.debug("Groq response received (%d chars)", len(content))
        return content


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_api_key() -> str:
    return (
        os.getenv("GROQ_API_KEY", "").strip()
        or os.getenv("LLM_API_KEY", "").strip()  # legacy alias
    )


def get_llm_client() -> LLMClient:
    """Return a GroqClient.

    Raises LLMError if GROQ_API_KEY is absent or MOCK_LLM=1 is set
    (caller should then use the rule-based fallback).
    """
    if os.getenv("MOCK_LLM", "").lower() in ("1", "true", "yes"):
        raise LLMError("MOCK_LLM=1 — using rule-based fallback (no Groq call).")

    key = _resolve_api_key()
    if not key:
        raise LLMError(
            "GROQ_API_KEY is not set. Set it in .env or use MOCK_LLM=1 for offline mode."
        )

    return GroqClient(api_key=key)
