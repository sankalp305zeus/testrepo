"""Recommendation engine — LLM ranking, validation, and fallback.

Flow (see architecture.md §5.4):
  1. Build prompt from shortlist + preferences.
  2. Call Groq; parse JSON response.
  3. Cross-check every returned restaurant_name against the shortlist.
  4. On malformed JSON: retry once.
  5. On any LLM failure: return rule-based top-N with template explanations.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.llm.client import LLMClient, LLMError, get_llm_client
from src.llm.prompts import build_messages
from src.models.preferences import UserPreferences
from src.models.recommendation import Recommendation
from src.models.restaurant import Restaurant

logger = logging.getLogger(__name__)

DEFAULT_MAX_RECOMMENDATIONS = 5

FALLBACK_EXPLANATION = (
    "Ranked by rating based on your filters. "
    "Personalised AI explanations are unavailable."
)


# ---------------------------------------------------------------------------
# Result wrapper
# ---------------------------------------------------------------------------

@dataclass
class RecommendationResult:
    """Full output of one recommendation request."""

    recommendations: List[Recommendation]
    summary: Optional[str] = None
    used_fallback: bool = False
    message: str = ""
    code: str = "OK"


# ---------------------------------------------------------------------------
# JSON parsing helpers
# ---------------------------------------------------------------------------

def _strip_markdown_fence(text: str) -> str:
    """Remove ```json ... ``` fences that some models add despite instructions."""
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text.strip())
    return match.group(1).strip() if match else text.strip()


def _parse_payload(raw: str) -> Dict[str, Any]:
    text = _strip_markdown_fence(raw)
    data = json.loads(text)
    if isinstance(data, list):
        return {"recommendations": data}
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object, got {type(data).__name__}")
    return data


def _find_in_shortlist(name: str, shortlist: Sequence[Restaurant]) -> Optional[Restaurant]:
    """Return the shortlist entry whose name matches; None if not found (hallucination)."""
    target = name.strip().casefold()
    if not target:
        return None
    # Exact match first.
    for r in shortlist:
        if r.name.casefold() == target:
            return r
    # Substring fallback (handles minor LLM paraphrasing).
    for r in shortlist:
        n = r.name.casefold()
        if target in n or n in target:
            return r
    return None


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _item_to_recommendation(
    item: Dict[str, Any],
    shortlist: Sequence[Restaurant],
) -> Optional[Recommendation]:
    name = str(item.get("restaurant_name") or item.get("name") or "").strip()
    if not name:
        return None

    matched = _find_in_shortlist(name, shortlist)
    if matched is None:
        logger.debug("LLM hallucination dropped: %r", name)
        return None

    cuisine = str(item.get("cuisine") or matched.cuisine_display()).strip()
    rating = _coerce_float(item.get("rating"), matched.rating)
    cost = _coerce_float(
        item.get("estimated_cost") or item.get("cost_for_two"),
        matched.cost_for_two,
    )
    explanation = str(item.get("explanation") or "").strip()
    if not explanation:
        explanation = (
            f"Matches your preference for {matched.cuisine_display()} "
            f"in {matched.location}."
        )

    return Recommendation(
        restaurant_name=matched.name,
        cuisine=cuisine,
        rating=round(rating, 2),
        estimated_cost=round(cost, 2),
        explanation=explanation,
    )


def parse_llm_recommendations(
    raw: str,
    shortlist: Sequence[Restaurant],
    *,
    max_items: int = DEFAULT_MAX_RECOMMENDATIONS,
) -> Tuple[List[Recommendation], Optional[str]]:
    """Parse and validate the raw LLM JSON string.

    Returns (recommendations, optional_summary).
    Raises json.JSONDecodeError or ValueError on bad input.
    """
    payload = _parse_payload(raw)

    summary: Optional[str] = None
    raw_summary = payload.get("summary")
    if raw_summary:
        summary = str(raw_summary).strip() or None

    items = payload.get("recommendations", [])
    if not isinstance(items, list):
        raise ValueError('"recommendations" must be a JSON array')

    results: List[Recommendation] = []
    seen: set[str] = set()

    for item in items:
        if not isinstance(item, dict):
            continue
        rec = _item_to_recommendation(item, shortlist)
        if rec is None:
            continue
        key = rec.restaurant_name.casefold()
        if key in seen:
            continue
        seen.add(key)
        results.append(rec)
        if len(results) >= max_items:
            break

    return results, summary


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------

def _build_fallback(
    shortlist: Sequence[Restaurant],
    prefs: UserPreferences,
    max_items: int,
) -> RecommendationResult:
    """Rule-based top-N: sorted by rating, with template explanation."""
    picks = list(shortlist)[:max_items]
    recs = [
        Recommendation(
            restaurant_name=r.name,
            cuisine=r.cuisine_display(),
            rating=r.rating,
            estimated_cost=r.cost_for_two,
            explanation=(
                f"{FALLBACK_EXPLANATION} "
                f"{r.rating}★ for {prefs.cuisine_normalized} "
                f"in {prefs.location_normalized} ({prefs.budget} budget)."
            ),
        )
        for r in picks
    ]
    return RecommendationResult(
        recommendations=recs,
        summary="Showing top matches by rating (Groq unavailable).",
        used_fallback=True,
        message="LLM unavailable; showing rule-based ranking.",
        code="FALLBACK",
    )


def _backfill(
    current: List[Recommendation],
    shortlist: Sequence[Restaurant],
    prefs: UserPreferences,
    max_items: int,
) -> List[Recommendation]:
    """Pad LLM results with shortlist entries when Groq returns fewer than max_items."""
    if len(current) >= max_items:
        return current[:max_items]

    used = {r.restaurant_name.casefold() for r in current}
    for r in shortlist:
        if r.name.casefold() in used:
            continue
        current.append(
            Recommendation(
                restaurant_name=r.name,
                cuisine=r.cuisine_display(),
                rating=r.rating,
                estimated_cost=r.cost_for_two,
                explanation=(
                    f"Added from filtered shortlist for {prefs.cuisine_normalized} "
                    f"in {prefs.location_normalized}."
                ),
            )
        )
        used.add(r.name.casefold())
        if len(current) >= max_items:
            break
    return current


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class RecommendationEngine:
    """Orchestrates Groq LLM call, JSON parsing, validation, and fallback."""

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        self._client = llm_client

    def _get_client(self) -> LLMClient:
        if self._client is not None:
            return self._client
        return get_llm_client()

    def recommend(
        self,
        shortlist: Sequence[Restaurant],
        prefs: UserPreferences,
        *,
        max_recommendations: int = DEFAULT_MAX_RECOMMENDATIONS,
    ) -> RecommendationResult:
        if not shortlist:
            return RecommendationResult(
                recommendations=[],
                code="EMPTY_SHORTLIST",
                message="No restaurants to recommend — adjust your filters first.",
            )

        max_recommendations = max(1, min(max_recommendations, 10))

        # Honour MOCK_LLM env flag when no explicit client is injected.
        if self._client is None and os.getenv("MOCK_LLM", "").lower() in ("1", "true", "yes"):
            logger.info("MOCK_LLM=1 — returning rule-based fallback.")
            return _build_fallback(shortlist, prefs, max_recommendations)

        # Resolve client (raises LLMError when key is missing).
        try:
            client = self._get_client()
        except LLMError as exc:
            logger.warning("LLM client unavailable: %s", exc)
            return _build_fallback(shortlist, prefs, max_recommendations)

        messages = build_messages(shortlist, prefs, max_recommendations=max_recommendations)
        last_error: Optional[Exception] = None

        for attempt in range(1, 3):  # up to 2 attempts
            try:
                t0 = time.perf_counter()
                raw = client.complete(messages)
                llm_latency = time.perf_counter() - t0
                logger.info("Groq latency: %.2fs (attempt %d)", llm_latency, attempt)
                recs, summary = parse_llm_recommendations(
                    raw, shortlist, max_items=max_recommendations
                )
                if recs:
                    recs = _backfill(recs, shortlist, prefs, max_recommendations)
                    logger.info(
                        "Recommendation: %d picks returned (fallback=False)",
                        len(recs[:max_recommendations]),
                    )
                    return RecommendationResult(
                        recommendations=recs[:max_recommendations],
                        summary=summary,
                        code="OK",
                    )
                last_error = ValueError("LLM returned no valid recommendations.")
                logger.warning("Attempt %d: no valid recommendations in response.", attempt)
            except (LLMError, json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
                last_error = exc
                logger.warning("Attempt %d failed: %s", attempt, exc)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning("Attempt %d unexpected error: %s", attempt, exc)

        logger.warning("Both LLM attempts failed (%s); using fallback.", last_error)
        return _build_fallback(shortlist, prefs, max_recommendations)


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------

def recommend(
    shortlist: Sequence[Restaurant],
    prefs: UserPreferences,
    *,
    llm_client: Optional[LLMClient] = None,
    max_recommendations: int = DEFAULT_MAX_RECOMMENDATIONS,
) -> RecommendationResult:
    """Shorthand: create a RecommendationEngine and call recommend()."""
    return RecommendationEngine(llm_client=llm_client).recommend(
        shortlist, prefs, max_recommendations=max_recommendations
    )
