"""Unit tests for data ingestion helpers."""

from src.data.ingest import (
    _extract_city,
    _parse_cost,
    _parse_cuisines,
    _parse_rating,
    _row_to_restaurant,
)


def test_parse_rating_from_fraction():
    assert _parse_rating("4.1/5") == 4.1
    assert _parse_rating("3.8 /5") == 3.8


def test_parse_rating_invalid():
    assert _parse_rating("NEW") is None
    assert _parse_rating("-") is None
    assert _parse_rating(None) is None


def test_parse_cost_simple_and_range():
    assert _parse_cost("800") == 800.0
    assert _parse_cost("1,000") == 1000.0
    assert _parse_cost("300-400") == 350.0


def test_parse_cost_invalid():
    assert _parse_cost("-") is None
    assert _parse_cost("0") is None


def test_parse_cuisines():
    assert _parse_cuisines("North Indian, Chinese") == ["North Indian", "Chinese"]


def test_extract_city_bangalore_aliases():
    addr = "942, 21st Main Road, 2nd Stage, Banashankari, Bangalore"
    assert _extract_city(addr, "Banashankari", "Banashankari") == "Bangalore"
    assert _extract_city("Some road, Bengaluru", None, None) == "Bangalore"


def test_row_to_restaurant_valid():
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
    r = _row_to_restaurant(row, 0)
    assert r is not None
    assert r.name == "Test Diner"
    assert r.location == "Bangalore"
    assert r.rating == 4.5
    assert r.cost_for_two == 600.0
    assert "Italian" in r.cuisines


def test_row_to_restaurant_drops_invalid():
    row = {
        "name": "",
        "address": "X, Bangalore",
        "cuisines": "Italian",
        "rate": "4.0/5",
        "approx_cost(for two people)": "500",
    }
    assert _row_to_restaurant(row, 0) is None
