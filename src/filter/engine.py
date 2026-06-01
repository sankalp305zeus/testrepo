"""
Deterministic restaurant filtering (no LLM).

Budget bands (cost_for_two, INR) derived from catalog percentiles:
  low:    <= 400
  medium: 401 – 800
  high:   > 800
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from src.models.preferences import Budget, UserPreferences
from src.models.restaurant import Restaurant

logger = logging.getLogger(__name__)

DEFAULT_SHORTLIST_CAP = 50

# (min_inclusive, max_inclusive); high band uses max_inclusive=None
BUDGET_BANDS: Dict[Budget, Tuple[Optional[float], Optional[float]]] = {
    "low": (None, 400.0),
    "medium": (401.0, 800.0),
    "high": (801.0, None),
}


@dataclass(frozen=True)
class FilterResult:
    """Outcome of filtering the catalog."""

    restaurants: List[Restaurant]
    code: str = "OK"
    message: str = ""
    hints: List[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return len(self.restaurants) == 0


def _cost_in_budget(cost: float, budget: Budget) -> bool:
    min_cost, max_cost = BUDGET_BANDS[budget]
    if min_cost is not None and cost < min_cost:
        return False
    if max_cost is not None and cost > max_cost:
        return False
    return True


def _location_matches(restaurant: Restaurant, location_query: str) -> bool:
    query = location_query.casefold()
    if not query:
        return False

    candidates = [restaurant.location]
    meta = restaurant.metadata or {}
    for key in ("area", "listed_in_city", "address"):
        value = meta.get(key)
        if value:
            candidates.append(str(value))

    for candidate in candidates:
        text = candidate.casefold()
        if query in text or text in query:
            return True
    return False


def _cuisine_matches(restaurant: Restaurant, cuisine_query: str) -> bool:
    query = cuisine_query.casefold()
    if not query:
        return False
    for cuisine in restaurant.cuisines:
        c = cuisine.casefold()
        if query in c or c in query:
            return True
    return False


def _extras_match(restaurant: Restaurant, extras: Sequence[str]) -> bool:
    if not extras:
        return True

    searchable_parts = [
        restaurant.name,
        " ".join(restaurant.cuisines),
        str((restaurant.metadata or {}).get("rest_type", "")),
        str((restaurant.metadata or {}).get("address", "")),
    ]
    haystack = " ".join(searchable_parts).casefold()

    return any(extra.casefold() in haystack for extra in extras)


def _apply_filters(
    catalog: Sequence[Restaurant],
    prefs: UserPreferences,
) -> List[Restaurant]:
    if not catalog:
        return []

    matched: List[Restaurant] = []
    for restaurant in catalog:
        if not _location_matches(restaurant, prefs.location_normalized):
            continue
        if restaurant.rating < prefs.min_rating:
            continue
        if not _cuisine_matches(restaurant, prefs.cuisine_normalized):
            continue
        if not _cost_in_budget(restaurant.cost_for_two, prefs.budget):
            continue
        if not _extras_match(restaurant, prefs.extras_normalized):
            continue
        matched.append(restaurant)

    return matched


def _sort_key(restaurant: Restaurant) -> Tuple[float, float, str]:
    return (-restaurant.rating, restaurant.cost_for_two, restaurant.name.casefold())


def _top_cities(catalog: Sequence[Restaurant], limit: int = 8) -> List[str]:
    counts: Dict[str, int] = {}
    for r in catalog:
        city = r.location.strip()
        if city and city != "Unknown":
            counts[city] = counts.get(city, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [city for city, _ in ranked[:limit]]


def _generate_hints(
    catalog: Sequence[Restaurant],
    prefs: UserPreferences,
) -> List[str]:
    hints: List[str] = []
    location = prefs.location_normalized
    cuisine = prefs.cuisine_normalized

    location_matches = [r for r in catalog if _location_matches(r, location)]
    if not location_matches:
        cities = _top_cities(catalog)
        if cities:
            hints.append(
                f"No restaurants found in “{location}”. Try: {', '.join(cities[:6])}."
            )
        else:
            hints.append(f"No restaurants found in “{location}”.")
    else:
        cuisine_matches = [r for r in location_matches if _cuisine_matches(r, cuisine)]
        if not cuisine_matches:
            hints.append(
                f"No “{cuisine}” restaurants in {location}. Try a broader cuisine (e.g. Indian, Chinese)."
            )

        rating_matches = [
            r for r in location_matches if r.rating >= prefs.min_rating
        ]
        if location_matches and not rating_matches and prefs.min_rating > 0:
            max_rating = max(r.rating for r in location_matches)
            hints.append(
                f"Try lowering minimum rating (max available near {location}: {max_rating:.1f})."
            )

        budget_matches = [
            r
            for r in location_matches
            if _cost_in_budget(r.cost_for_two, prefs.budget)
        ]
        if location_matches and not budget_matches:
            band = BUDGET_BANDS[prefs.budget]
            hints.append(
                f"No restaurants in the “{prefs.budget}” budget band "
                f"({band[0] or 0:.0f}–{band[1] or '∞'} INR for two). Try another budget."
            )

    if not hints:
        hints.append(
            "Try relaxing minimum rating, choosing a broader cuisine, or a different budget."
        )
    return hints


def filter_restaurants(
    catalog: Sequence[Restaurant],
    prefs: UserPreferences,
    *,
    max_results: int = DEFAULT_SHORTLIST_CAP,
) -> FilterResult:
    """
    Filter catalog by preferences and return a rating-sorted shortlist.

    Returns FilterResult with code EMPTY_SHORTLIST when no matches; hints guide the user.
    """
    if not catalog:
        return FilterResult(
            restaurants=[],
            code="NO_CATALOG",
            message="Restaurant catalog is empty. Run data ingestion first.",
            hints=["Run: python -m src.data.ingest"],
        )

    if max_results < 1:
        raise ValueError("max_results must be at least 1")

    matched = _apply_filters(catalog, prefs)
    if not matched:
        hints = _generate_hints(catalog, prefs)
        return FilterResult(
            restaurants=[],
            code="EMPTY_SHORTLIST",
            message="No restaurants match your preferences.",
            hints=hints,
        )

    ranked = sorted(matched, key=_sort_key)
    shortlist = ranked[:max_results]
    logger.info(
        "Filter: %d/%d restaurants matched (location=%r cuisine=%r budget=%s min_rating=%.1f)",
        len(shortlist),
        len(catalog),
        prefs.location_normalized,
        prefs.cuisine_normalized,
        prefs.budget,
        prefs.min_rating,
    )
    return FilterResult(
        restaurants=shortlist,
        code="OK",
        message="",
        hints=[],
    )
