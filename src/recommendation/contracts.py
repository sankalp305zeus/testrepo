"""PipelineRequest / PipelineResponse — the single public contract for the orchestration layer.

Every caller (Streamlit UI, CLI, future REST API) speaks only these two types.
Internal details (FilterResult, RecommendationResult) stay hidden inside the orchestrator.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import List, Optional

from src.models.preferences import UserPreferences
from src.models.recommendation import Recommendation


@dataclass
class PipelineRequest:
    """Input contract: what the caller wants."""

    preferences: UserPreferences
    max_recommendations: int = 5
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if self.max_recommendations < 1 or self.max_recommendations > 10:
            raise ValueError("max_recommendations must be between 1 and 10")


@dataclass
class PipelineResponse:
    """Output contract: everything the caller needs to render a result."""

    request_id: str
    recommendations: List[Recommendation]

    # pipeline status
    filter_code: str           # "OK" | "EMPTY_SHORTLIST" | "NO_CATALOG"
    rec_code: str              # "OK" | "FALLBACK" | "EMPTY_SHORTLIST"
    used_fallback: bool

    # user-facing helpers
    hints: List[str]           # non-empty only when filter_code != "OK"
    summary: Optional[str]     # optional one-liner from the LLM

    # observability
    latency_ms: int            # total wall-clock time for the pipeline call
    shortlist_size: int        # number of candidates passed to the LLM
