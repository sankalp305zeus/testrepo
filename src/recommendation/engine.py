"""
Recommendation engine: LLM ranking + explanations with validation and fallback.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from src.llm.client import LLMClient, LLMError, get_llm_client
from src.llm.prompts import build_messages
from src.models.preferences import UserPreferences
from src.models.recommendation import Recommendation
from src.models.restaurant import Restaurant

logger = logging.getLogger(__name__)

DEFAULT_MAX_RECOMMENDATIONS = 5
FALLBACK_EXPLANATION = (
    "Ranked by rating based on your filters. "
    "Personalized AI explanations are unavailable."
)


@dataclass
class RecommendationResult:
    """Outcome of the recommendation step."""

    recommendations: List[Recommendation]
    summary: Optional[str] = None
    used_fallback: bool = False
    message: str = ""
    code: str = "OK"


def _extract_json_text(raw: str) -> str:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        return fence.group(1).strip()
    return text


def _parse_llm_payload(raw: str) -> Dict[str, Any]:
    text = _extract_json_text(raw)
    data = json.loads(text)
    if isinstance(data, list):
        return {"recommendations": data}
    if not isinstance(data, dict):
        raise ValueError("LLM response must be a JSON object or array")
    return data


def _find_restaurant(name: str, shortlist: Sequence[Restaurant]) -> Optional[Restaurant]:
    target = name.strip().casefold()
    if not target:
        return None
    for restaurant in shortlist:
        if restaurant.name.casefold() == target:
            return restaurant
    for restaurant in shortlist:
        n = restaurant.name.casefold()
        if target in n or n in target:
            return restaurant
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

    matched = _find_restaurant(name, shortlist)
    if matched is None:
        logger.debug("Dropping LLM pick not in shortlist: %s", name)
        return None

    cuisine = str(item.get("cuisine") or matched.cuisine_display()).strip()
    rating = _coerce_float(item.get("rating"), matched.rating)
    cost = _coerce_float(
        item.get("estimated_cost", item.get("cost_for_two")),
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
) -> tuple[List[Recommendation], Optional[str]]:
    payload = _parse_llm_payload(raw)
    summary = payload.get("summary")
    if summary is not None:
        summary = str(summary).strip() or None

    items = payload.get("recommendations", [])
    if not isinstance(items, list):
        raise ValueError("recommendations must be a JSON array")

    results: List[Recommendation] = []
    seen_names: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        rec = _item_to_recommendation(item, shortlist)
        if rec is None:
            continue
        key = rec.restaurant_name.casefold()
        if key in seen_names:
            continue
        seen_names.add(key)
        results.append(rec)
        if len(results) >= max_items:
            break

    return results, summary


def _fallback_recommendations(
    shortlist: Sequence[Restaurant],
    prefs: UserPreferences,
    *,
    max_items: int = DEFAULT_MAX_RECOMMENDATIONS,
) -> RecommendationResult:
    picks = list(shortlist)[:max_items]
    recommendations: List[Recommendation] = []
    for restaurant in picks:
        recommendations.append(
            Recommendation(
                restaurant_name=restaurant.name,
                cuisine=restaurant.cuisine_display(),
                rating=restaurant.rating,
                estimated_cost=restaurant.cost_for_two,
                explanation=(
                    f"{FALLBACK_EXPLANATION} "
                    f"Strong {restaurant.rating}★ match for {prefs.cuisine_normalized} "
                    f"in {prefs.location_normalized} ({prefs.budget} budget)."
                ),
            )
        )
    return RecommendationResult(
        recommendations=recommendations,
        summary="Showing top matches ranked by rating (LLM unavailable).",
        used_fallback=True,
        message="LLM unavailable; using rule-based ranking.",
        code="FALLBACK",
    )


def _backfill_from_shortlist(
    current: List[Recommendation],
    shortlist: Sequence[Restaurant],
    prefs: UserPreferences,
    max_items: int,
) -> List[Recommendation]:
    if len(current) >= max_items:
        return current[:max_items]

    used = {r.restaurant_name.casefold() for r in current}
    for restaurant in shortlist:
        if restaurant.name.casefold() in used:
            continue
        current.append(
            Recommendation(
                restaurant_name=restaurant.name,
                cuisine=restaurant.cuisine_display(),
                rating=restaurant.rating,
                estimated_cost=restaurant.cost_for_two,
                explanation=(
                    f"Added from your filtered shortlist for {prefs.cuisine_normalized} "
                    f"in {prefs.location_normalized}."
                ),
            )
        )
        used.add(restaurant.name.casefold())
        if len(current) >= max_items:
            break
    return current


class RecommendationEngine:
    """Orchestrates LLM calls, parsing, validation, and fallback."""

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        self._llm_client = llm_client

    def _client(self) -> LLMClient:
        if self._llm_client is not None:
            return self._llm_client
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
                message="No restaurants to recommend. Adjust filters first.",
            )

        max_recommendations = max(1, min(max_recommendations, 10))

        if self._llm_client is None and os.getenv("MOCK_LLM", "").lower() in (
            "1",
            "true",
            "yes",
        ):
            logger.info("MOCK_LLM=1 — using rule-based fallback")
            return _fallback_recommendations(shortlist, prefs, max_items=max_recommendations)

        try:
            client = self._llm_client if self._llm_client is not None else self._client()
        except LLMError as exc:
            logger.warning("LLM client unavailable: %s", exc)
            return _fallback_recommendations(shortlist, prefs, max_items=max_recommendations)

        messages = build_messages(shortlist, prefs, max_recommendations=max_recommendations)
        last_error: Optional[Exception] = None

        for attempt in range(2):
            try:
                raw = client.complete(messages)
                recommendations, summary = parse_llm_recommendations(
                    raw,
                    shortlist,
                    max_items=max_recommendations,
                )
                if recommendations:
                    recommendations = _backfill_from_shortlist(
                        recommendations,
                        shortlist,
                        prefs,
                        max_recommendations,
                    )
                    return RecommendationResult(
                        recommendations=recommendations[:max_recommendations],
                        summary=summary,
                        used_fallback=False,
                        code="OK",
                    )
                last_error = ValueError("No valid recommendations in LLM response")
            except (LLMError, json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
                last_error = exc
                logger.warning("LLM attempt %d failed: %s", attempt + 1, exc)
            except Exception as exc:
                last_error = exc
                logger.warning("LLM attempt %d unexpected error: %s", attempt + 1, exc)

        logger.warning("Falling back after LLM failure: %s", last_error)
        return _fallback_recommendations(shortlist, prefs, max_items=max_recommendations)


def recommend(
    shortlist: Sequence[Restaurant],
    prefs: UserPreferences,
    *,
    llm_client: Optional[LLMClient] = None,
    max_recommendations: int = DEFAULT_MAX_RECOMMENDATIONS,
) -> RecommendationResult:
    """Convenience wrapper around RecommendationEngine."""
    engine = RecommendationEngine(llm_client=llm_client)
    return engine.recommend(shortlist, prefs, max_recommendations=max_recommendations)
