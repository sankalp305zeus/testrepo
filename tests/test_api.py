"""Tests for Phase 7 — FastAPI REST API layer (TestClient, mocked LLM)."""

from __future__ import annotations

import json
from typing import List
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.models.restaurant import Restaurant
from src.recommendation.cache import ResponseCache


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _restaurant(idx: int, name: str, **kwargs) -> Restaurant:
    return Restaurant(
        id=f"r{idx:02d}",
        name=name,
        location=kwargs.get("location", "Bangalore"),
        cuisines=kwargs.get("cuisines", ["North Indian"]),
        rating=kwargs.get("rating", 4.3),
        cost_for_two=kwargs.get("cost_for_two", 600.0),
        metadata={},
    )


CATALOG = [
    _restaurant(1,  "Spice Hub",        rating=4.6, cost_for_two=550),
    _restaurant(2,  "Curry Palace",     rating=4.5, cost_for_two=600),
    _restaurant(3,  "Masala Magic",     rating=4.4, cost_for_two=700),
    _restaurant(4,  "Punjabi House",    rating=4.3, cost_for_two=650),
    _restaurant(5,  "Tandoor Tales",    rating=4.2, cost_for_two=580),
    _restaurant(6,  "Pizza Roma",       rating=4.5, cost_for_two=700, cuisines=["Italian"]),
    _restaurant(7,  "Mumbai Masala",    rating=4.4, cost_for_two=500,
                location="Mumbai", cuisines=["North Indian"]),
]

VALID_BODY = {
    "location": "Bangalore",
    "budget": "medium",
    "cuisine": "North Indian",
    "min_rating": 4.0,
    "extras": [],
    "max_recommendations": 3,
}

def _llm_json(*names: str) -> str:
    return json.dumps({
        "recommendations": [
            {"restaurant_name": n, "cuisine": "North Indian",
             "rating": 4.4, "estimated_cost": 600,
             "explanation": f"{n} is a great match."}
            for n in names
        ],
        "summary": "Great picks for you.",
    })


@pytest.fixture
def client(monkeypatch):
    """TestClient with a fixture catalog (mocked load_catalog) and disabled cache."""
    monkeypatch.setenv("MOCK_LLM", "1")
    monkeypatch.setenv("DISABLE_CACHE", "1")
    # Patch load_catalog so the lifespan uses our small fixture catalog
    with patch("src.api.main.load_catalog", return_value=CATALOG):
        with TestClient(app) as c:
            yield c


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

def test_health_returns_200(client):
    r = client.get("/health")
    assert r.status_code == 200


def test_health_response_shape(client):
    data = client.get("/health").json()
    assert "status" in data
    assert "catalog_size" in data
    assert "groq_configured" in data
    assert "mock_mode" in data


def test_health_reflects_catalog_size(client):
    data = client.get("/health").json()
    assert data["catalog_size"] == len(CATALOG)


def test_health_mock_mode_true(client):
    data = client.get("/health").json()
    assert data["mock_mode"] is True


# ---------------------------------------------------------------------------
# GET /cities
# ---------------------------------------------------------------------------

def test_cities_returns_200(client):
    assert client.get("/cities").status_code == 200


def test_cities_returns_list_of_strings(client):
    data = client.get("/cities").json()
    assert isinstance(data["cities"], list)
    assert all(isinstance(c, str) for c in data["cities"])


def test_cities_contains_bangalore(client):
    cities = client.get("/cities").json()["cities"]
    assert "Bangalore" in cities


# ---------------------------------------------------------------------------
# GET /cuisines
# ---------------------------------------------------------------------------

def test_cuisines_returns_200(client):
    assert client.get("/cuisines").status_code == 200


def test_cuisines_returns_list_of_strings(client):
    data = client.get("/cuisines").json()
    assert isinstance(data["cuisines"], list)
    assert all(isinstance(c, str) for c in data["cuisines"])


def test_cuisines_contains_north_indian(client):
    cuisines = client.get("/cuisines").json()["cuisines"]
    assert "North Indian" in cuisines


# ---------------------------------------------------------------------------
# POST /recommendations — happy path
# ---------------------------------------------------------------------------

def test_recommendations_returns_200(client):
    r = client.post("/recommendations", json=VALID_BODY)
    assert r.status_code == 200


def test_recommendations_response_shape(client):
    data = client.post("/recommendations", json=VALID_BODY).json()
    assert "request_id" in data
    assert "recommendations" in data
    assert "filter_code" in data
    assert "rec_code" in data
    assert "used_fallback" in data
    assert "hints" in data
    assert "latency_ms" in data
    assert "shortlist_size" in data


def test_recommendations_returns_results(client):
    data = client.post("/recommendations", json=VALID_BODY).json()
    assert data["filter_code"] == "OK"
    assert len(data["recommendations"]) >= 1


def test_recommendation_items_have_required_fields(client):
    items = client.post("/recommendations", json=VALID_BODY).json()["recommendations"]
    for item in items:
        assert item["restaurant_name"]
        assert item["cuisine"]
        assert item["rating"] >= 0
        assert item["estimated_cost"] >= 0
        assert item["explanation"]


def test_mock_llm_uses_fallback(client):
    data = client.post("/recommendations", json=VALID_BODY).json()
    assert data["used_fallback"] is True   # MOCK_LLM=1 fixture always falls back


# ---------------------------------------------------------------------------
# POST /recommendations — empty shortlist
# ---------------------------------------------------------------------------

def test_impossible_prefs_returns_200_not_500(client):
    body = {**VALID_BODY, "location": "Tokyo", "cuisine": "Ethiopian", "min_rating": 5.0}
    r = client.post("/recommendations", json=body)
    assert r.status_code == 200


def test_impossible_prefs_returns_empty_shortlist_code(client):
    body = {**VALID_BODY, "location": "Tokyo", "cuisine": "Ethiopian", "min_rating": 5.0}
    data = client.post("/recommendations", json=body).json()
    assert data["filter_code"] == "EMPTY_SHORTLIST"
    assert data["recommendations"] == []
    assert len(data["hints"]) >= 1


# ---------------------------------------------------------------------------
# POST /recommendations — validation errors (422)
# ---------------------------------------------------------------------------

def test_missing_location_returns_422(client):
    body = {k: v for k, v in VALID_BODY.items() if k != "location"}
    assert client.post("/recommendations", json=body).status_code == 422


def test_missing_cuisine_returns_422(client):
    body = {k: v for k, v in VALID_BODY.items() if k != "cuisine"}
    assert client.post("/recommendations", json=body).status_code == 422


def test_invalid_budget_returns_422(client):
    assert client.post("/recommendations", json={**VALID_BODY, "budget": "luxury"}).status_code == 422


def test_rating_above_5_returns_422(client):
    assert client.post("/recommendations", json={**VALID_BODY, "min_rating": 6.0}).status_code == 422


def test_rating_below_0_returns_422(client):
    assert client.post("/recommendations", json={**VALID_BODY, "min_rating": -1.0}).status_code == 422


def test_max_recommendations_above_10_returns_422(client):
    assert client.post("/recommendations", json={**VALID_BODY, "max_recommendations": 11}).status_code == 422


# ---------------------------------------------------------------------------
# POST /recommendations — LLM down → fallback (not 500)
# ---------------------------------------------------------------------------

def test_llm_down_returns_200_with_fallback(monkeypatch):
    monkeypatch.delenv("MOCK_LLM", raising=False)
    monkeypatch.setenv("DISABLE_CACHE", "1")

    app.state.catalog = CATALOG
    app.state.pipeline_cache = None

    from src.llm.client import LLMError
    with patch("src.recommendation.engine.get_llm_client",
               side_effect=LLMError("API down")):
        with TestClient(app) as c:
            r = c.post("/recommendations", json=VALID_BODY)
    assert r.status_code == 200
    assert r.json()["used_fallback"] is True


# ---------------------------------------------------------------------------
# GET /health — catalog not loaded → 503
# ---------------------------------------------------------------------------

def test_health_with_empty_catalog(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "1")
    monkeypatch.setenv("DISABLE_CACHE", "1")
    with patch("src.api.main.load_catalog", return_value=[]):
        with TestClient(app) as c:
            data = c.get("/health").json()
    assert data["catalog_size"] == 0
