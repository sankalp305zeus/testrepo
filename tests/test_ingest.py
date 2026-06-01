"""Unit tests for data ingestion helpers.

Covers edge cases from edge-cases.md §1 (DATA-*).
"""

from __future__ import annotations

import pytest

from src.data.ingest import (
    CACHE_VERSION,
    _dataframe_to_restaurants,
    _extract_city,
    _normalize_dataset,
    _parse_cost,
    _parse_cuisines,
    _parse_rating,
    _restaurants_to_dataframe,
    _row_to_restaurant,
    _validate_schema,
)


# ---------------------------------------------------------------------------
# _parse_rating  (DATA-05)
# ---------------------------------------------------------------------------

def test_parse_rating_from_fraction():
    assert _parse_rating("4.1/5") == 4.1
    assert _parse_rating("3.8 /5") == 3.8


def test_parse_rating_integer_string():
    assert _parse_rating("4") == 4.0


def test_parse_rating_invalid_sentinels():
    assert _parse_rating("NEW") is None
    assert _parse_rating("-") is None
    assert _parse_rating(None) is None
    assert _parse_rating("") is None
    assert _parse_rating("nan") is None


def test_parse_rating_out_of_range_dropped():
    assert _parse_rating("6.0") is None   # DATA-16: > 5 → drop
    assert _parse_rating("-1") is None


# ---------------------------------------------------------------------------
# _parse_cost  (DATA-06)
# ---------------------------------------------------------------------------

def test_parse_cost_simple_and_range():
    assert _parse_cost("800") == 800.0
    assert _parse_cost("1,000") == 1000.0
    assert _parse_cost("300-400") == 350.0


def test_parse_cost_rupee_symbol():
    assert _parse_cost("₹500") == 500.0


def test_parse_cost_invalid():
    assert _parse_cost("-") is None
    assert _parse_cost(None) is None
    assert _parse_cost("nan") is None


def test_parse_cost_zero_dropped():
    assert _parse_cost("0") is None          # DATA-06: zero cost → drop


# ---------------------------------------------------------------------------
# _parse_cuisines  (DATA-08)
# ---------------------------------------------------------------------------

def test_parse_cuisines_comma_string():
    assert _parse_cuisines("North Indian, Chinese") == ["North Indian", "Chinese"]


def test_parse_cuisines_list_input():
    assert _parse_cuisines(["Italian", "Continental"]) == ["Italian", "Continental"]


def test_parse_cuisines_single_entry():
    assert _parse_cuisines("Italian") == ["Italian"]


def test_parse_cuisines_empty():
    assert _parse_cuisines("") == []
    assert _parse_cuisines(None) == []


# ---------------------------------------------------------------------------
# _extract_city  (DATA-15)
# ---------------------------------------------------------------------------

def test_extract_city_bangalore_aliases():
    assert _extract_city("942, MG Road, Bangalore", "MG Road", "MG Road") == "Bangalore"
    assert _extract_city("Some road, Bengaluru", None, None) == "Bangalore"
    assert _extract_city("Some road, Banglore", None, None) == "Bangalore"


def test_extract_city_falls_back_to_listed_in():
    assert _extract_city(None, None, "Pune") == "Pune"


def test_extract_city_unknown_when_no_info():
    assert _extract_city(None, None, None) == "Unknown"


# ---------------------------------------------------------------------------
# _row_to_restaurant  (DATA-04, DATA-05, DATA-06)
# ---------------------------------------------------------------------------

def _base_row(**overrides):
    row = {
        "url": "https://zomato.com/test",
        "name": "Test Diner",
        "address": "1 MG Road, Bangalore",
        "location": "MG Road",
        "listed_in(city)": "MG Road",
        "cuisines": "Italian, Continental",
        "rate": "4.5/5",
        "approx_cost(for two people)": "600",
    }
    row.update(overrides)
    return row


def test_row_to_restaurant_valid():
    r = _row_to_restaurant(_base_row(), 0)
    assert r is not None
    assert r.name == "Test Diner"
    assert r.location == "Bangalore"
    assert r.rating == 4.5
    assert r.cost_for_two == 600.0
    assert "Italian" in r.cuisines


def test_row_drops_empty_name():              # DATA-04
    assert _row_to_restaurant(_base_row(name=""), 0) is None
    assert _row_to_restaurant(_base_row(name="   "), 0) is None


def test_row_drops_invalid_rating():          # DATA-05
    assert _row_to_restaurant(_base_row(rate="NEW"), 0) is None
    assert _row_to_restaurant(_base_row(rate="-"), 0) is None
    assert _row_to_restaurant(_base_row(rate=None), 0) is None


def test_row_drops_zero_cost():               # DATA-06
    assert _row_to_restaurant(_base_row(**{"approx_cost(for two people)": "0"}), 0) is None


def test_row_drops_empty_cuisines():
    assert _row_to_restaurant(_base_row(cuisines=""), 0) is None


def test_row_drops_unknown_city():
    assert _row_to_restaurant(_base_row(address=None, location=None, **{"listed_in(city)": None}), 0) is None


# ---------------------------------------------------------------------------
# _validate_schema  (DATA-02)
# ---------------------------------------------------------------------------

def test_validate_schema_passes_with_all_required_columns():
    _validate_schema(["name", "address", "cuisines", "rate", "approx_cost(for two people)"])


def test_validate_schema_raises_on_missing_column():
    with pytest.raises(ValueError, match="missing required columns"):
        _validate_schema(["name", "cuisines", "rate"])   # address + cost missing


# ---------------------------------------------------------------------------
# Cache round-trip  (DATA-12: cache version)
# ---------------------------------------------------------------------------

def test_cache_round_trip_preserves_data():
    from src.models.restaurant import Restaurant
    original = [
        Restaurant(
            id="r1",
            name="Round Trip Café",
            location="Bangalore",
            cuisines=["Italian", "Continental"],
            rating=4.2,
            cost_for_two=650.0,
            metadata={"area": "Indiranagar"},
        )
    ]
    df = _restaurants_to_dataframe(original)
    restored = _dataframe_to_restaurants(df)
    assert len(restored) == 1
    r = restored[0]
    assert r.name == "Round Trip Café"
    assert r.rating == 4.2
    assert "Italian" in r.cuisines
    assert r.metadata.get("area") == "Indiranagar"


def test_cache_version_mismatch_raises():
    import pandas as pd
    from src.models.restaurant import Restaurant

    original = [
        Restaurant(
            id="r1", name="Old Café", location="Bangalore",
            cuisines=["Italian"], rating=4.0, cost_for_two=500.0,
        )
    ]
    df = _restaurants_to_dataframe(original)
    df["cache_version"] = CACHE_VERSION + 99   # simulate stale cache
    with pytest.raises(ValueError, match="Cache version mismatch"):
        _dataframe_to_restaurants(df)


# ---------------------------------------------------------------------------
# _normalize_dataset  (DATA-14: all rows invalid → RuntimeError)
# ---------------------------------------------------------------------------

def test_normalize_dataset_raises_when_all_rows_invalid():
    class FakeSplit:
        column_names = ["name", "address", "cuisines", "rate", "approx_cost(for two people)"]

        def __iter__(self):
            # Every row has an empty name → all dropped
            yield {
                "name": "",
                "address": "X, Bangalore",
                "location": "X",
                "listed_in(city)": "Bangalore",
                "cuisines": "Italian",
                "rate": "4.0/5",
                "approx_cost(for two people)": "500",
                "url": None,
                "rest_type": None,
                "votes": None,
            }

        def __len__(self):
            return 1

    with pytest.raises(RuntimeError, match="No valid restaurants"):
        _normalize_dataset(FakeSplit())
