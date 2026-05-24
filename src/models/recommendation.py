"""LLM recommendation output model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Recommendation:
    """User-facing recommendation (matches context.md output fields)."""

    restaurant_name: str
    cuisine: str
    rating: float
    estimated_cost: float
    explanation: str
    summary: Optional[str] = None
