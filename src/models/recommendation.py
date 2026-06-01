"""LLM recommendation output model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Recommendation:
    """Single restaurant recommendation returned by the LLM engine.

    Fields match the output table in context.md.
    """

    restaurant_name: str
    cuisine: str
    rating: float
    estimated_cost: float
    explanation: str
    summary: Optional[str] = None
