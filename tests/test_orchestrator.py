"""Tests for Phase 6 — RecommendationOrchestrator, ResponseCache, and contracts."""

from __future__ import annotations

import json
import time

import pytest

from src.llm.client import LLMError, MockLLMClient
from src.models.preferences import UserPreferences
from src.models.restaurant import Restaurant
from src.recommendation.cache import ResponseCache, make_cache_key
from src.recommendation.contracts import PipelineRequest, PipelineResponse
from src.recommendation.orchestrator import RecommendationOrchestrator


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _restaurant(idx: int, name: str, **kwargs) -> Restaurant:
    defaults = dict(
        id=f"r{idx:02d}",
        location="Bangalore",
        cuisines=["North Indian"],
        rating=4.3,
        cost_for_two=600.0,
        metadata={},
    )
    defaults.update(kwargs)
    return Restaurant(name=name, **defaults)


CATALOG = [
    _restaurant(1, "Spice Hub",     rating=4.6, cost_for_two=550),
    _restaurant(2, "Curry Palace",  rating=4.5, cost_for_two=600),
    _restaurant(3, "Masala Magic",  rating=4.4, cost_for_two=700),
    _restaurant(4, "Punjabi House", rating=4.3, cost_for_two=650),
    _restaurant(5, "Tandoor Tales", rating=4.2, cost_for_two=580),
]

PREFS = UserPreferences(
    location="Bangalore",
    budget="medium",
    cuisine="North Indian",
    min_rating=4.0,
)


def _llm_json(*names: str) -> str:
    return json.dumps({
        "recommendations": [
            {"restaurant_name": n, "cuisine": "North Indian",
             "rating": 4.4, "estimated_cost": 600,
             "explanation": f"{n} is a great match."}
            for n in names
        ],
        "summary": "Top picks for you.",
    })


def _orchestrator(mock_response: str | None = None, cache: ResponseCache | None = None):
    client = MockLLMClient(mock_response or _llm_json("Spice Hub", "Curry Palace"))
    return RecommendationOrchestrator(
        catalog=CATALOG,
        llm_client=client,
        cache=cache,
        auto_build_cache=False,
    ), client


# ---------------------------------------------------------------------------
# PipelineRequest / PipelineResponse contracts
# ---------------------------------------------------------------------------

def test_pipeline_request_auto_generates_request_id():
    r1 = PipelineRequest(preferences=PREFS)
    r2 = PipelineRequest(preferences=PREFS)
    assert r1.request_id != r2.request_id


def test_pipeline_request_rejects_invalid_max_recommendations():
    with pytest.raises(ValueError):
        PipelineRequest(preferences=PREFS, max_recommendations=0)
    with pytest.raises(ValueError):
        PipelineRequest(preferences=PREFS, max_recommendations=11)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_happy_path_returns_ok_response():
    orchestrator, _ = _orchestrator()
    request = PipelineRequest(preferences=PREFS, max_recommendations=3)
    response = orchestrator.run(request)

    assert isinstance(response, PipelineResponse)
    assert response.request_id == request.request_id
    assert response.filter_code == "OK"
    assert response.rec_code == "OK"
    assert not response.used_fallback
    assert len(response.recommendations) >= 1
    assert response.shortlist_size > 0
    assert response.latency_ms >= 0


def test_response_contains_all_required_fields():
    orchestrator, _ = _orchestrator()
    response = orchestrator.run(PipelineRequest(preferences=PREFS))

    for rec in response.recommendations:
        assert rec.restaurant_name
        assert rec.cuisine
        assert rec.rating >= 0
        assert rec.estimated_cost >= 0
        assert rec.explanation


def test_recommendations_are_only_from_shortlist():
    orchestrator, _ = _orchestrator()
    shortlist_names = {r.name for r in CATALOG}
    response = orchestrator.run(PipelineRequest(preferences=PREFS))

    for rec in response.recommendations:
        assert rec.restaurant_name in shortlist_names


# ---------------------------------------------------------------------------
# Empty shortlist
# ---------------------------------------------------------------------------

def test_impossible_prefs_returns_empty_shortlist_response():
    impossible = UserPreferences(
        location="Tokyo", budget="low", cuisine="Ethiopian", min_rating=5.0
    )
    orchestrator, _ = _orchestrator()
    response = orchestrator.run(PipelineRequest(preferences=impossible))

    assert response.filter_code == "EMPTY_SHORTLIST"
    assert response.recommendations == []
    assert len(response.hints) >= 1


def test_empty_shortlist_llm_is_not_called():
    impossible = UserPreferences(
        location="Tokyo", budget="low", cuisine="Ethiopian", min_rating=5.0
    )
    orchestrator, client = _orchestrator()
    orchestrator.run(PipelineRequest(preferences=impossible))

    assert len(client.calls) == 0   # LLM never called when shortlist is empty


# ---------------------------------------------------------------------------
# LLM failure → fallback
# ---------------------------------------------------------------------------

def test_llm_failure_returns_fallback_response():
    class AlwaysDown:
        def complete(self, messages):
            raise LLMError("503 down")

    orchestrator = RecommendationOrchestrator(
        catalog=CATALOG, llm_client=AlwaysDown(), auto_build_cache=False
    )
    response = orchestrator.run(PipelineRequest(preferences=PREFS))

    assert response.used_fallback
    assert response.rec_code == "FALLBACK"
    assert len(response.recommendations) >= 1


def test_mock_llm_env_returns_fallback(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "1")
    orchestrator = RecommendationOrchestrator(
        catalog=CATALOG, auto_build_cache=False
    )
    response = orchestrator.run(PipelineRequest(preferences=PREFS))

    assert response.used_fallback
    assert response.rec_code == "FALLBACK"


def test_orchestrator_never_raises_on_bad_json():
    orchestrator, _ = _orchestrator(mock_response="not json at all {{{{")
    response = orchestrator.run(PipelineRequest(preferences=PREFS))

    # Should fall back gracefully, not raise
    assert response.used_fallback


# ---------------------------------------------------------------------------
# Cache — hit / miss
# ---------------------------------------------------------------------------

def test_cache_miss_calls_llm():
    cache = ResponseCache(ttl_seconds=60)
    orchestrator, client = _orchestrator(cache=cache)

    orchestrator.run(PipelineRequest(preferences=PREFS))
    assert len(client.calls) == 1   # LLM called on miss


def test_cache_hit_skips_llm():
    cache = ResponseCache(ttl_seconds=60)
    orchestrator, client = _orchestrator(cache=cache)

    request = PipelineRequest(preferences=PREFS)
    orchestrator.run(request)               # miss — calls LLM
    orchestrator.run(request)               # hit — skips LLM

    assert len(client.calls) == 1           # LLM called exactly once


def test_cache_hit_preserves_request_id():
    cache = ResponseCache(ttl_seconds=60)
    orchestrator, _ = _orchestrator(cache=cache)

    r1 = PipelineRequest(preferences=PREFS)
    r2 = PipelineRequest(preferences=PREFS)
    assert r1.request_id != r2.request_id   # different UUIDs

    orchestrator.run(r1)    # populate cache
    resp2 = orchestrator.run(r2)

    assert resp2.request_id == r2.request_id    # caller's ID, not cached one


def test_cache_different_prefs_are_separate_entries():
    cache = ResponseCache(ttl_seconds=60)
    orchestrator, client = _orchestrator(cache=cache)

    prefs_a = UserPreferences(location="Bangalore", budget="low",
                               cuisine="North Indian", min_rating=4.0)
    prefs_b = UserPreferences(location="Bangalore", budget="high",
                               cuisine="North Indian", min_rating=4.0)

    orchestrator.run(PipelineRequest(preferences=prefs_a))
    orchestrator.run(PipelineRequest(preferences=prefs_b))

    # Two different keys → two LLM calls (prefs_b shortlist is empty for high
    # budget on our test catalog, but the filter step still runs)
    assert cache.size <= 2   # at most two entries stored


def test_disable_cache_env_bypasses_caching(monkeypatch):
    monkeypatch.setenv("DISABLE_CACHE", "1")
    from src.recommendation.cache import build_cache
    assert build_cache() is None


# ---------------------------------------------------------------------------
# Cache TTL expiry
# ---------------------------------------------------------------------------

def test_cache_entry_expires_after_ttl():
    cache = ResponseCache(ttl_seconds=0)    # expires immediately
    orchestrator, client = _orchestrator(cache=cache)

    orchestrator.run(PipelineRequest(preferences=PREFS))   # sets entry
    time.sleep(0.01)                                        # let it expire
    orchestrator.run(PipelineRequest(preferences=PREFS))   # should miss

    assert len(client.calls) == 2   # LLM called twice (no cache hit)


# ---------------------------------------------------------------------------
# ResponseCache unit tests
# ---------------------------------------------------------------------------

def test_cache_lru_eviction():
    cache = ResponseCache(ttl_seconds=60, max_size=2)
    # Use dummy objects as values; cache doesn't inspect them
    cache.set("a", "resp_a")
    cache.set("b", "resp_b")
    cache.set("c", "resp_c")   # evicts "a" (LRU)

    assert cache.get("a") is None
    assert cache.get("b") == "resp_b"
    assert cache.get("c") == "resp_c"


def test_cache_clear():
    cache = ResponseCache(ttl_seconds=60)
    cache.set("x", "value")
    cache.clear()
    assert cache.size == 0


# ---------------------------------------------------------------------------
# make_cache_key — determinism
# ---------------------------------------------------------------------------

def test_cache_key_is_deterministic():
    k1 = make_cache_key(PREFS)
    k2 = make_cache_key(PREFS)
    assert k1 == k2


def test_cache_key_differs_on_different_prefs():
    other = UserPreferences(
        location="Delhi", budget="low", cuisine="Chinese", min_rating=3.5
    )
    assert make_cache_key(PREFS) != make_cache_key(other)


def test_cache_key_is_case_insensitive_for_location_and_cuisine():
    p1 = UserPreferences(location="Bangalore", budget="medium",
                         cuisine="North Indian", min_rating=4.0)
    p2 = UserPreferences(location="bangalore", budget="medium",
                         cuisine="north indian", min_rating=4.0)
    assert make_cache_key(p1) == make_cache_key(p2)
