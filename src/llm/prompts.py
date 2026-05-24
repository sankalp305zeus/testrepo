"""Prompt templates for restaurant recommendations."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence

from src.models.preferences import UserPreferences
from src.models.restaurant import Restaurant

SYSTEM_PROMPT = """You are a helpful restaurant advisor for India.
You MUST only recommend restaurants from the SHORTLIST provided by the user.
Do not invent restaurants or facts not supported by the shortlist.
Respond with valid JSON only (no markdown): a single object with keys:
  "recommendations": array of up to {max_items} objects, each with:
    restaurant_name (string, exact name from shortlist),
    cuisine (string),
    rating (number),
    estimated_cost (number, INR for two),
    explanation (string, 1-2 sentences tying to user preferences)
  "summary": optional one-line string overview of the set
Order recommendations from best match to weakest."""

MAX_SHORTLIST_IN_PROMPT = 30


def _serialize_shortlist(restaurants: Sequence[Restaurant]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for restaurant in restaurants[:MAX_SHORTLIST_IN_PROMPT]:
        rows.append(
            {
                "name": restaurant.name[:100],
                "location": restaurant.location[:60],
                "area": str((restaurant.metadata or {}).get("area", ""))[:60],
                "cuisines": ", ".join(restaurant.cuisines[:6])[:120],
                "rating": restaurant.rating,
                "cost_for_two": restaurant.cost_for_two,
            }
        )
    return rows


def build_messages(
    shortlist: Sequence[Restaurant],
    prefs: UserPreferences,
    *,
    max_recommendations: int = 5,
) -> List[Dict[str, str]]:
    """Build chat messages for the LLM."""
    preferences = {
        "location": prefs.location_normalized,
        "budget": prefs.budget,
        "cuisine": prefs.cuisine_normalized,
        "min_rating": prefs.min_rating,
        "extras": prefs.extras_normalized,
    }
    user_payload = {
        "user_preferences": preferences,
        "shortlist": _serialize_shortlist(shortlist),
        "instructions": (
            f"Return up to {max_recommendations} recommendations as JSON. "
            "Use exact restaurant names from the shortlist."
        ),
    }

    system = SYSTEM_PROMPT.format(max_items=max_recommendations)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]
