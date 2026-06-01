"""End-to-end pipeline tests using a fixture catalog and a mocked LLM.

Covers smoke-test scenarios from implementation-plan.md Phase 5:
  #3 — typical prefs → filter → LLM → 3-5 recommendations
  #4 — impossible prefs → friendly empty state
  #5 — LLM down (MOCK_LLM=1) → fallback rankings shown

No network calls are made; GROQ_API_KEY is never required.
"""

from __future__ import annotations

import json

import pytest

from src.filter.engine import filter_restaurants
from src.llm.client import LLMError, MockLLMClient
from src.models.preferences import UserPreferences
from src.models.restaurant import Restaurant
from src.recommendation.engine import recommend


# ---------------------------------------------------------------------------
# Shared fixture catalog (20 restaurants)
# ---------------------------------------------------------------------------

def _make_restaurant(
    idx: int,
    name: str,
    location: str = "Bangalore",
    cuisines=None,
    rating: float = 4.3,
    cost_for_two: float = 600.0,
) -> Restaurant:
    return Restaurant(
        id=f"r{idx:02d}",
        name=name,
        location=location,
        cuisines=cuisines or ["North Indian"],
        rating=rating,
        cost_for_two=cost_for_two,
        metadata={"area": "Indiranagar"},
    )


CATALOG = [
    _make_restaurant(1,  "Spice Hub",        rating=4.6, cost_for_two=550),
    _make_restaurant(2,  "Curry Palace",     rating=4.5, cost_for_two=600),
    _make_restaurant(3,  "Masala Magic",     rating=4.4, cost_for_two=700),
    _make_restaurant(4,  "Punjabi House",    rating=4.3, cost_for_two=650),
    _make_restaurant(5,  "Tandoor Tales",    rating=4.2, cost_for_two=580),
    _make_restaurant(6,  "Biryani Bros",     rating=4.1, cost_for_two=500),
    _make_restaurant(7,  "Dal Makhani Den",  rating=4.0, cost_for_two=450),
    _make_restaurant(8,  "Butter Chicken Co",rating=3.9, cost_for_two=620),
    _make_restaurant(9,  "Roti Republic",    rating=4.5, cost_for_two=480, cuisines=["North Indian", "Mughlai"]),
    _make_restaurant(10, "Naan Stop",        rating=4.4, cost_for_two=530),
    _make_restaurant(11, "Pizza Place",      rating=4.7, cost_for_two=700, cuisines=["Italian"]),
    _make_restaurant(12, "Pasta Point",      rating=4.5, cost_for_two=750, cuisines=["Italian"]),
    _make_restaurant(13, "Wok N Roll",       rating=4.3, cost_for_two=500, cuisines=["Chinese"]),
    _make_restaurant(14, "Dragon Garden",    rating=4.1, cost_for_two=600, cuisines=["Chinese"]),
    _make_restaurant(15, "South Spice",      rating=4.6, cost_for_two=400, cuisines=["South Indian"]),
    _make_restaurant(16, "Dosa Delight",     rating=4.4, cost_for_two=350, cuisines=["South Indian"]),
    _make_restaurant(17, "Expensive Elite",  rating=4.9, cost_for_two=2000, cuisines=["North Indian"]),
    _make_restaurant(18, "Mumbai Snacks",    location="Mumbai", rating=4.5, cost_for_two=500),
    _make_restaurant(19, "Delhi Darbar",     location="Delhi",  rating=4.5, cost_for_two=600),
    _make_restaurant(20, "Budget Bites",     rating=4.0, cost_for_two=300),
]


def _llm_json(names: list[str]) -> str:
    return json.dumps({
        "recommendations": [
            {
                "restaurant_name": n,
                "cuisine": "North Indian",
                "rating": 4.4,
                "estimated_cost": 600,
                "explanation": f"{n} is a great match for your preferences.",
            }
            for n in names
        ],
        "summary": "Top North Indian picks in Bangalore.",
    })


TYPICAL_PREFS = UserPreferences(
    location="Bangalore",
    budget="medium",
    cuisine="North Indian",
    min_rating=4.0,
)


# ---------------------------------------------------------------------------
# Smoke test #3 — typical prefs → filter → mock LLM → 3-5 recommendations
# ---------------------------------------------------------------------------

def test_happy_path_returns_recommendations():
    filter_result = filter_restaurants(CATALOG, TYPICAL_PREFS)
    assert not filter_result.is_empty

    shortlist = filter_result.restaurants
    llm_names = [r.name for r in shortlist[:3]]
    client = MockLLMClient(_llm_json(llm_names))

    result = recommend(shortlist, TYPICAL_PREFS, llm_client=client, max_recommendations=5)

    assert result.code == "OK"
    assert not result.used_fallback
    assert 3 <= len(result.recommendations) <= 5
    for rec in result.recommendations:
        assert rec.restaurant_name
        assert rec.explanation
        assert rec.rating > 0


def test_happy_path_recommendations_only_from_shortlist():
    filter_result = filter_restaurants(CATALOG, TYPICAL_PREFS)
    shortlist = filter_result.restaurants
    shortlist_names = {r.name for r in shortlist}

    llm_names = [r.name for r in shortlist[:3]]
    client = MockLLMClient(_llm_json(llm_names))
    result = recommend(shortlist, TYPICAL_PREFS, llm_client=client, max_recommendations=3)

    for rec in result.recommendations:
        assert rec.restaurant_name in shortlist_names, (
            f"{rec.restaurant_name!r} not in shortlist — hallucination leaked through"
        )


def test_results_display_all_required_fields():
    filter_result = filter_restaurants(CATALOG, TYPICAL_PREFS)
    shortlist = filter_result.restaurants
    llm_names = [r.name for r in shortlist[:3]]
    client = MockLLMClient(_llm_json(llm_names))

    result = recommend(shortlist, TYPICAL_PREFS, llm_client=client)

    for rec in result.recommendations:
        assert rec.restaurant_name
        assert rec.cuisine
        assert rec.rating >= 0
        assert rec.estimated_cost >= 0
        assert rec.explanation


# ---------------------------------------------------------------------------
# Smoke test #4 — impossible prefs → friendly empty state with hints
# ---------------------------------------------------------------------------

def test_impossible_prefs_empty_shortlist_with_hints():
    impossible_prefs = UserPreferences(
        location="Tokyo",
        budget="low",
        cuisine="Ethiopian",
        min_rating=5.0,
    )
    filter_result = filter_restaurants(CATALOG, impossible_prefs)

    assert filter_result.is_empty
    assert filter_result.code == "EMPTY_SHORTLIST"
    assert filter_result.message
    assert len(filter_result.hints) >= 1


def test_location_not_in_catalog_hints_available_cities():
    prefs = UserPreferences(
        location="Tokyo",
        budget="medium",
        cuisine="North Indian",
        min_rating=4.0,
    )
    filter_result = filter_restaurants(CATALOG, prefs)
    assert filter_result.is_empty
    assert any("Bangalore" in h or "Delhi" in h or "Mumbai" in h for h in filter_result.hints)


def test_rating_too_high_hints_max_available():
    prefs = UserPreferences(
        location="Bangalore",
        budget="medium",
        cuisine="North Indian",
        min_rating=5.0,
    )
    filter_result = filter_restaurants(CATALOG, prefs)
    assert filter_result.is_empty
    assert any("rating" in h.lower() for h in filter_result.hints)


# ---------------------------------------------------------------------------
# Smoke test #5 — LLM down → fallback rankings shown (MOCK_LLM=1)
# ---------------------------------------------------------------------------

def test_mock_llm_env_shows_fallback(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "1")
    filter_result = filter_restaurants(CATALOG, TYPICAL_PREFS)
    result = recommend(filter_result.restaurants, TYPICAL_PREFS, max_recommendations=3)

    assert result.used_fallback
    assert result.code == "FALLBACK"
    assert len(result.recommendations) == 3
    assert result.summary


def test_llm_failure_shows_fallback():
    class AlwaysDown:
        def complete(self, messages):
            raise LLMError("503 Service Unavailable")

    filter_result = filter_restaurants(CATALOG, TYPICAL_PREFS)
    result = recommend(
        filter_result.restaurants, TYPICAL_PREFS,
        llm_client=AlwaysDown(), max_recommendations=3,
    )
    assert result.used_fallback
    assert len(result.recommendations) >= 1


def test_llm_hallucination_never_reaches_output():
    filter_result = filter_restaurants(CATALOG, TYPICAL_PREFS)
    shortlist = filter_result.restaurants
    shortlist_names = {r.name for r in shortlist}

    hallucinated = json.dumps({
        "recommendations": [
            {"restaurant_name": "Invented Place XYZ", "cuisine": "North Indian",
             "rating": 5.0, "estimated_cost": 300, "explanation": "Hallucinated."},
            {"restaurant_name": shortlist[0].name, "cuisine": "North Indian",
             "rating": 4.5, "estimated_cost": 500, "explanation": "Real pick."},
        ]
    })
    client = MockLLMClient(hallucinated)
    result = recommend(shortlist, TYPICAL_PREFS, llm_client=client, max_recommendations=5)

    for rec in result.recommendations:
        assert rec.restaurant_name in shortlist_names, (
            f"Hallucinated name {rec.restaurant_name!r} reached output"
        )


# ---------------------------------------------------------------------------
# Budget and location isolation
# ---------------------------------------------------------------------------

def test_filter_respects_budget_low():
    prefs = UserPreferences(
        location="Bangalore", budget="low", cuisine="North Indian", min_rating=3.5
    )
    result = filter_restaurants(CATALOG, prefs)
    for r in result.restaurants:
        assert r.cost_for_two <= 400, f"{r.name} cost {r.cost_for_two} exceeds low band"


def test_filter_respects_budget_high():
    prefs = UserPreferences(
        location="Bangalore", budget="high", cuisine="North Indian", min_rating=3.5
    )
    result = filter_restaurants(CATALOG, prefs)
    for r in result.restaurants:
        assert r.cost_for_two > 800, f"{r.name} cost {r.cost_for_two} not in high band"


def test_filter_isolates_by_city():
    prefs = UserPreferences(
        location="Mumbai", budget="medium", cuisine="North Indian", min_rating=3.5
    )
    result = filter_restaurants(CATALOG, prefs)
    for r in result.restaurants:
        assert "Mumbai" in r.location or "mumbai" in r.location.lower()
