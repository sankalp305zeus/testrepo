"""LLM provider clients (Groq default)."""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


@runtime_checkable
class LLMClient(Protocol):
    """Minimal interface for chat completion."""

    def complete(self, messages: List[Dict[str, str]]) -> str:
        ...


class LLMError(Exception):
    """Raised when the LLM provider fails."""


class MockLLMClient:
    """Deterministic client for tests."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: List[List[Dict[str, str]]] = []

    def complete(self, messages: List[Dict[str, str]]) -> str:
        self.calls.append(messages)
        return self.response


class GroqClient:
    """Groq Chat Completions API adapter."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key or _resolve_groq_api_key()
        self.model = (
            model
            or os.getenv("GROQ_MODEL")
            or os.getenv("LLM_MODEL")
            or DEFAULT_GROQ_MODEL
        )
        self.timeout = timeout
        if not self.api_key:
            raise LLMError("GROQ_API_KEY is not set")

    def complete(self, messages: List[Dict[str, str]]) -> str:
        try:
            from groq import Groq
        except ImportError as exc:
            raise LLMError(
                "groq package is required. Install with: pip install groq"
            ) from exc

        client = Groq(api_key=self.api_key, timeout=self.timeout)
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            logger.warning("Groq API call failed: %s", exc)
            raise LLMError(str(exc)) from exc

        content = response.choices[0].message.content
        if not content:
            raise LLMError("Empty response from Groq")
        return content


def _resolve_groq_api_key() -> str:
    """Prefer GROQ_API_KEY; accept legacy LLM_API_KEY for migration."""
    return (
        os.getenv("GROQ_API_KEY", "").strip()
        or os.getenv("LLM_API_KEY", "").strip()
    )


def get_llm_client() -> LLMClient:
    """Return GroqClient; raises LLMError if API key is missing."""
    if os.getenv("MOCK_LLM", "").lower() in ("1", "true", "yes"):
        raise LLMError("MOCK_LLM=1 enables offline fallback without calling the API.")

    if not _resolve_groq_api_key():
        raise LLMError(
            "GROQ_API_KEY is not set. Set it in .env or use MOCK_LLM=1 for offline mode."
        )
    return GroqClient()
