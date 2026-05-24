"""Tests for LLM recommendation engine (mocked)."""

import json
import os

import pytest

from src.llm.client import LLMError, MockLLMClient
from src.models.preferences import UserPreferences
from src.models.restaurant import Restaurant
from src.recommendation.engine import (
    FALLBACK_EXPLANATION,
    RecommendationEngine,
    parse_llm_recommendations,
    recommend,
)


def _restaurant(name: str, **kwargs) -> Restaurant:
    defaults = {
        "id": f"id_{name}",
        "location": "Bangalore",
        "cuisines": ["North Indian"],
        "rating": 4.5,
        "cost_for_two": 600.0,
        "metadata": {},
    }
    defaults.update(kwargs)
    return Restaurant(name=name, **defaults)


SHORTLIST = [
    _restaurant("Spice Hub", rating=4.6, cost_for_two=550.0),
    _restaurant("Curry Leaf", rating=4.4, cost_for_two=700.0),
    _restaurant("Budget Bites", rating=4.2, cost_for_two=450.0),
]

PREFS = UserPreferences(
    location="Bangalore",
    budget="medium",
    cuisine="North Indian",
    min_rating=4.0,
)


def _llm_json(recommendations, summary="Great picks."):
    return json.dumps({"recommendations": recommendations, "summary": summary})


def test_parse_valid_llm_response():
    raw = _llm_json(
        [
            {
                "restaurant_name": "Spice Hub",
                "cuisine": "North Indian",
                "rating": 4.6,
                "estimated_cost": 550,
                "explanation": "Top rated match.",
            }
        ]
    )
    recs, summary = parse_llm_recommendations(raw, SHORTLIST)
    assert len(recs) == 1
    assert recs[0].restaurant_name == "Spice Hub"
    assert recs[0].explanation == "Top rated match."
    assert summary == "Great picks."


def test_parse_strips_markdown_fence():
    inner = _llm_json(
        [
            {
                "restaurant_name": "Curry Leaf",
                "cuisine": "North Indian",
                "rating": 4.4,
                "estimated_cost": 700,
                "explanation": "Solid choice.",
            }
        ]
    )
    raw = f"```json\n{inner}\n```"
    recs, _ = parse_llm_recommendations(raw, SHORTLIST)
    assert recs[0].restaurant_name == "Curry Leaf"


def test_parse_drops_hallucinated_restaurant():
    raw = _llm_json(
        [
            {
                "restaurant_name": "Fake Place",
                "cuisine": "Italian",
                "rating": 5,
                "estimated_cost": 100,
                "explanation": "Not real.",
            },
            {
                "restaurant_name": "Spice Hub",
                "cuisine": "North Indian",
                "rating": 4.6,
                "estimated_cost": 550,
                "explanation": "Real.",
            },
        ]
    )
    recs, _ = parse_llm_recommendations(raw, SHORTLIST)
    assert len(recs) == 1
    assert recs[0].restaurant_name == "Spice Hub"


def test_recommend_with_mock_llm():
    payload = _llm_json(
        [
            {
                "restaurant_name": "Spice Hub",
                "cuisine": "North Indian",
                "rating": 4.6,
                "estimated_cost": 550,
                "explanation": "Best fit for your cuisine and budget.",
            },
            {
                "restaurant_name": "Curry Leaf",
                "cuisine": "North Indian",
                "rating": 4.4,
                "estimated_cost": 700,
                "explanation": "Highly rated alternative.",
            },
        ],
        summary="Two strong North Indian options.",
    )
    client = MockLLMClient(payload)
    result = recommend(SHORTLIST, PREFS, llm_client=client, max_recommendations=2)

    assert not result.used_fallback
    assert result.code == "OK"
    assert len(result.recommendations) == 2
    assert result.summary == "Two strong North Indian options."
    assert result.recommendations[0].restaurant_name == "Spice Hub"
    assert len(client.calls) == 1


def test_mock_llm_env_uses_fallback(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "1")
    result = recommend(SHORTLIST, PREFS, max_recommendations=3)
    assert result.used_fallback
    assert result.code == "FALLBACK"
    assert len(result.recommendations) == 3


def test_recommend_retries_then_fallback_on_bad_json():
    client = MockLLMClient("not valid json {{{")
    engine = RecommendationEngine(llm_client=client)
    result = engine.recommend(SHORTLIST, PREFS, max_recommendations=3)

    assert result.used_fallback
    assert result.code == "FALLBACK"
    assert len(result.recommendations) == 3
    assert FALLBACK_EXPLANATION in result.recommendations[0].explanation
    assert len(client.calls) == 2


def test_recommend_fallback_when_llm_raises():
    class FailingClient:
        def complete(self, messages):  # noqa: ARG002
            raise LLMError("API down")

    result = recommend(SHORTLIST, PREFS, llm_client=FailingClient())
    assert result.used_fallback
    assert len(result.recommendations) >= 1


def test_recommend_empty_shortlist():
    result = recommend([], PREFS, llm_client=MockLLMClient("{}"))
    assert result.code == "EMPTY_SHORTLIST"
    assert result.recommendations == []


def test_catalog_values_preferred_on_parse():
    raw = _llm_json(
        [
            {
                "restaurant_name": "Spice Hub",
                "cuisine": "North Indian",
                "rating": 1.0,
                "estimated_cost": 1,
                "explanation": "Test.",
            }
        ]
    )
    recs, _ = parse_llm_recommendations(raw, SHORTLIST)
    assert recs[0].rating == 1.0
    assert recs[0].estimated_cost == 1.0


@pytest.mark.integration
def test_live_llm_integration():
    if os.getenv("RUN_LLM_INTEGRATION") != "1":
        pytest.skip("Set RUN_LLM_INTEGRATION=1 to run live LLM test")
    if not (os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY")):
        pytest.skip("GROQ_API_KEY required")

    from pathlib import Path

    if not Path("data/restaurants.parquet").exists():
        pytest.skip("catalog cache required")

    from src.data.ingest import load_catalog
    from src.filter.engine import filter_restaurants

    catalog = load_catalog()
    prefs = UserPreferences("Bangalore", "medium", "North Indian", 4.0)
    shortlist = filter_restaurants(catalog, prefs).restaurants[:20]
    result = recommend(shortlist, prefs, max_recommendations=3)
    assert len(result.recommendations) >= 1
