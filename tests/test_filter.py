"""Unit tests for the filtering engine."""

import pytest

from src.filter.engine import BUDGET_BANDS, filter_restaurants
from src.models.preferences import UserPreferences
from src.models.restaurant import Restaurant


def _restaurant(
    *,
    id: str = "r1",
    name: str = "Test Place",
    location: str = "Bangalore",
    cuisines=None,
    rating: float = 4.2,
    cost_for_two: float = 600.0,
    metadata=None,
) -> Restaurant:
    return Restaurant(
        id=id,
        name=name,
        location=location,
        cuisines=cuisines or ["North Indian"],
        rating=rating,
        cost_for_two=cost_for_two,
        metadata=metadata or {"area": "Indiranagar"},
    )


FIXTURES = [
    _restaurant(id="r1", name="Spice Hub", rating=4.5, cost_for_two=350.0),
    _restaurant(id="r2", name="Curry Leaf", rating=4.3, cost_for_two=600.0),
    _restaurant(
        id="r3",
        name="Budget Bites",
        rating=4.0,
        cost_for_two=300.0,
        cuisines=["North Indian", "Chinese"],
    ),
    _restaurant(
        id="r4",
        name="Fine Dine",
        rating=4.8,
        cost_for_two=1500.0,
        cuisines=["North Indian"],
    ),
    _restaurant(
        id="r5",
        name="Italian Corner",
        rating=4.6,
        cost_for_two=700.0,
        cuisines=["Italian"],
    ),
    _restaurant(
        id="r6",
        name="Family Feast",
        rating=4.1,
        cost_for_two=500.0,
        metadata={"area": "Koramangala", "rest_type": "Casual Dining"},
    ),
    _restaurant(
        id="r7",
        name="Low Rated Spot",
        rating=3.2,
        cost_for_two=450.0,
    ),
    _restaurant(
        id="r8",
        name="Banashankari Local",
        location="Bangalore",
        rating=4.4,
        cost_for_two=550.0,
        metadata={"area": "Banashankari"},
    ),
    _restaurant(
        id="r9",
        name="Tie Rating A",
        rating=4.5,
        cost_for_two=500.0,
        cuisines=["North Indian"],
    ),
    _restaurant(
        id="r10",
        name="Tie Rating B",
        rating=4.5,
        cost_for_two=400.0,
        cuisines=["North Indian"],
    ),
]


def test_typical_prefs_non_empty():
    prefs = UserPreferences(
        location="Bangalore",
        budget="medium",
        cuisine="North Indian",
        min_rating=4.0,
    )
    result = filter_restaurants(FIXTURES, prefs, max_results=50)
    assert not result.is_empty
    assert result.code == "OK"
    assert all(r.rating >= 4.0 for r in result.restaurants)
    assert all(401 <= r.cost_for_two <= 800 for r in result.restaurants)


def test_impossible_prefs_empty_with_hints():
    prefs = UserPreferences(
        location="Tokyo",
        budget="low",
        cuisine="North Indian",
        min_rating=5.0,
    )
    result = filter_restaurants(FIXTURES, prefs)
    assert result.is_empty
    assert result.code == "EMPTY_SHORTLIST"
    assert result.message
    assert len(result.hints) >= 1


def test_single_match():
    prefs = UserPreferences(
        location="Bangalore",
        budget="medium",
        cuisine="Italian",
        min_rating=4.0,
    )
    result = filter_restaurants(FIXTURES, prefs)
    assert len(result.restaurants) == 1
    assert result.restaurants[0].name == "Italian Corner"


def test_budget_boundary_medium():
    prefs = UserPreferences(
        location="Bangalore",
        budget="medium",
        cuisine="North Indian",
        min_rating=3.5,
    )
    result = filter_restaurants(FIXTURES, prefs, max_results=50)
    names = {r.name for r in result.restaurants}
    assert "Budget Bites" not in names  # 300 = low band
    assert "Curry Leaf" in names  # 600 = medium
    assert "Fine Dine" not in names  # 1500 = high


def test_rating_tie_breaker_uses_lower_cost():
    prefs = UserPreferences(
        location="Bangalore",
        budget="medium",
        cuisine="North Indian",
        min_rating=4.0,
    )
    result = filter_restaurants(
        [_restaurant(id="a", name="Tie Rating A", rating=4.5, cost_for_two=550.0),
         _restaurant(id="b", name="Tie Rating B", rating=4.5, cost_for_two=450.0)],
        prefs,
    )
    assert result.restaurants[0].name == "Tie Rating B"


def test_location_case_insensitive():
    prefs = UserPreferences(
        location="bangalore",
        budget="medium",
        cuisine="north indian",
        min_rating=4.0,
    )
    result = filter_restaurants(FIXTURES, prefs, max_results=50)
    assert not result.is_empty


def test_location_matches_area_metadata():
    prefs = UserPreferences(
        location="Banashankari",
        budget="medium",
        cuisine="North Indian",
        min_rating=4.0,
    )
    result = filter_restaurants(FIXTURES, prefs)
    assert any(r.name == "Banashankari Local" for r in result.restaurants)


def test_extras_keyword_family():
    prefs = UserPreferences(
        location="Bangalore",
        budget="medium",
        cuisine="North Indian",
        min_rating=4.0,
        extras=["family"],
    )
    result = filter_restaurants(FIXTURES, prefs)
    assert len(result.restaurants) == 1
    assert result.restaurants[0].name == "Family Feast"


def test_shortlist_cap():
    prefs = UserPreferences(
        location="Bangalore",
        budget="medium",
        cuisine="North Indian",
        min_rating=3.0,
    )
    result = filter_restaurants(FIXTURES, prefs, max_results=2)
    assert len(result.restaurants) == 2


def test_empty_catalog():
    prefs = UserPreferences(
        location="Bangalore",
        budget="medium",
        cuisine="North Indian",
        min_rating=4.0,
    )
    result = filter_restaurants([], prefs)
    assert result.code == "NO_CATALOG"


def test_user_preferences_validation():
    with pytest.raises(ValueError):
        UserPreferences(location="", budget="low", cuisine="Italian")
    with pytest.raises(ValueError):
        UserPreferences(location="X", budget="low", cuisine="", min_rating=4.0)
    with pytest.raises(ValueError):
        UserPreferences(location="X", budget="low", cuisine="Italian", min_rating=6.0)


def test_budget_bands_documented():
    assert BUDGET_BANDS["low"][1] == 400.0
    assert BUDGET_BANDS["medium"] == (401.0, 800.0)
    assert BUDGET_BANDS["high"][0] == 801.0


@pytest.mark.integration
def test_filter_real_catalog_under_one_second():
    """Uses cached parquet when present."""
    from pathlib import Path

    if not Path("data/restaurants.parquet").exists():
        pytest.skip("catalog cache not built")

    import time

    from src.data.ingest import load_catalog

    catalog = load_catalog()
    prefs = UserPreferences(
        location="Bangalore",
        budget="medium",
        cuisine="North Indian",
        min_rating=4.0,
    )
    start = time.perf_counter()
    result = filter_restaurants(catalog, prefs, max_results=50)
    elapsed = time.perf_counter() - start

    assert elapsed < 1.0
    assert not result.is_empty
    assert len(result.restaurants) <= 50
