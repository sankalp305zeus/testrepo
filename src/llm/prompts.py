"""Prompt templates for Groq-based restaurant recommendations.

Design principles (from architecture.md §5.3):
  1. Grounding   — model must only recommend restaurants from the shortlist.
  2. Structured  — response must be a JSON object with a "recommendations" array.
  3. Reasoning   — each pick includes a 1-2 sentence explanation tied to prefs.
  4. Ranking     — best match first; capped at max_recommendations.
  5. Summary     — optional one-line overview of the result set.
  6. Token cap   — only essential fields serialised; long strings truncated.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence

from src.models.preferences import UserPreferences
from src.models.restaurant import Restaurant

# Maximum shortlist rows sent to the LLM (keeps prompt size manageable).
MAX_SHORTLIST_ROWS = 30

SYSTEM_PROMPT = (
    "You are a knowledgeable restaurant advisor for India.\n"
    "You MUST recommend only restaurants that appear in the SHORTLIST provided by the user.\n"
    "Do NOT invent restaurant names or details.\n\n"
    "Respond with valid JSON only (no markdown, no prose outside JSON).\n"
    "The JSON object must have:\n"
    "  \"recommendations\": array of up to {max_items} objects, each containing:\n"
    "    restaurant_name  – exact name from the shortlist\n"
    "    cuisine          – cuisine type (string)\n"
    "    rating           – numeric rating\n"
    "    estimated_cost   – cost for two in INR (number)\n"
    "    explanation      – 1-2 sentences explaining why this fits the user's preferences\n"
    "  \"summary\": (optional) one-line overview of the recommendations\n\n"
    "Order recommendations from best match to weakest match."
)


def _serialize_shortlist(restaurants: Sequence[Restaurant]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for r in restaurants[:MAX_SHORTLIST_ROWS]:
        rows.append(
            {
                "name": r.name[:100],
                "location": r.location[:60],
                "area": str((r.metadata or {}).get("area", ""))[:60] or None,
                "cuisines": ", ".join(r.cuisines[:6])[:120],
                "rating": r.rating,
                "cost_for_two": r.cost_for_two,
            }
        )
    return rows


def build_messages(
    shortlist: Sequence[Restaurant],
    prefs: UserPreferences,
    *,
    max_recommendations: int = 5,
) -> List[Dict[str, str]]:
    """Build the system + user message pair for the Groq chat completion call."""
    user_payload = {
        "user_preferences": {
            "location": prefs.location_normalized,
            "budget": prefs.budget,
            "cuisine": prefs.cuisine_normalized,
            "min_rating": prefs.min_rating,
            "extras": prefs.extras_normalized,
        },
        "shortlist": _serialize_shortlist(shortlist),
        "task": (
            f"Return up to {max_recommendations} ranked recommendations as JSON. "
            "Use exact restaurant names from the shortlist only."
        ),
    }

    system = SYSTEM_PROMPT.format(max_items=max_recommendations)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]
