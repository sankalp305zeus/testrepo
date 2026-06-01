"""Tests for Streamlit form validation helpers (src/app/forms.py)."""

from __future__ import annotations

import pytest

from src.app.forms import _MAX_EXTRAS_COUNT, _MAX_EXTRA_TOKEN_LEN, parse_extras, validate_form


# ---------------------------------------------------------------------------
# validate_form — happy path
# ---------------------------------------------------------------------------

def test_valid_form_returns_no_errors():
    errors, budget = validate_form("Bangalore", "North Indian", 4.0, "medium")
    assert errors == []
    assert budget == "medium"


def test_all_budget_values_accepted():
    for b in ("low", "medium", "high"):
        errors, budget = validate_form("Delhi", "Chinese", 3.5, b)
        assert errors == []
        assert budget == b


def test_zero_min_rating_accepted():
    errors, _ = validate_form("Bangalore", "Italian", 0.0, "low")
    assert errors == []


def test_max_min_rating_accepted():
    errors, _ = validate_form("Bangalore", "Italian", 5.0, "high")
    assert errors == []


# ---------------------------------------------------------------------------
# validate_form — location errors
# ---------------------------------------------------------------------------

def test_empty_location_raises_error():
    errors, _ = validate_form("", "Italian", 4.0, "low")
    assert any("Location is required" in e for e in errors)


def test_whitespace_only_location_raises_error():
    errors, _ = validate_form("   ", "Italian", 4.0, "low")
    assert any("Location is required" in e for e in errors)


def test_location_too_long_raises_error():
    errors, _ = validate_form("x" * 101, "Italian", 4.0, "low")
    assert any("Location must be at most" in e for e in errors)


# ---------------------------------------------------------------------------
# validate_form — cuisine errors
# ---------------------------------------------------------------------------

def test_empty_cuisine_raises_error():
    errors, _ = validate_form("Bangalore", "", 4.0, "medium")
    assert any("Cuisine is required" in e for e in errors)


def test_cuisine_too_long_raises_error():
    errors, _ = validate_form("Bangalore", "c" * 101, 4.0, "medium")
    assert any("Cuisine must be at most" in e for e in errors)


# ---------------------------------------------------------------------------
# validate_form — rating errors
# ---------------------------------------------------------------------------

def test_rating_above_5_raises_error():
    errors, _ = validate_form("Bangalore", "Italian", 5.1, "low")
    assert any("between 0 and 5" in e for e in errors)


def test_rating_below_0_raises_error():
    errors, _ = validate_form("Bangalore", "Italian", -0.1, "low")
    assert any("between 0 and 5" in e for e in errors)


def test_non_numeric_rating_raises_error():
    errors, _ = validate_form("Bangalore", "Italian", "four", "low")  # type: ignore[arg-type]
    assert any("number" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# validate_form — budget errors
# ---------------------------------------------------------------------------

def test_invalid_budget_returns_none():
    errors, budget = validate_form("Bangalore", "Italian", 4.0, "luxury")
    assert budget is None
    assert any("budget" in e.lower() for e in errors)


def test_invalid_budget_does_not_block_other_error_reporting():
    errors, budget = validate_form("", "Italian", 4.0, "luxury")
    assert budget is None
    assert len(errors) >= 2  # location + budget


# ---------------------------------------------------------------------------
# validate_form — extras text
# ---------------------------------------------------------------------------

def test_extras_too_long_raises_error():
    errors, _ = validate_form("Bangalore", "Italian", 4.0, "low", extras_text="a" * 501)
    assert any("Extras" in e or "extras" in e.lower() for e in errors)


def test_extras_within_limit_is_accepted():
    errors, _ = validate_form("Bangalore", "Italian", 4.0, "low", extras_text="quick, family")
    assert errors == []


# ---------------------------------------------------------------------------
# parse_extras
# ---------------------------------------------------------------------------

def test_parse_extras_basic():
    result = parse_extras("quick service, family-friendly")
    assert result == ["quick service", "family-friendly"]


def test_parse_extras_deduplicates_case_insensitively():
    result = parse_extras("quick, Quick, QUICK")
    assert result == ["quick"]


def test_parse_extras_empty_string_returns_empty():
    assert parse_extras("") == []
    assert parse_extras("   ") == []


def test_parse_extras_strips_whitespace():
    result = parse_extras("  outdoor ,  rooftop  ")
    assert result == ["outdoor", "rooftop"]


def test_parse_extras_skips_empty_tokens():
    result = parse_extras(",,,quick,,,")
    assert result == ["quick"]


def test_parse_extras_respects_max_count():
    many = ", ".join(f"extra{i}" for i in range(_MAX_EXTRAS_COUNT + 5))
    result = parse_extras(many)
    assert len(result) == _MAX_EXTRAS_COUNT


def test_parse_extras_truncates_long_tokens():
    long_token = "x" * (_MAX_EXTRA_TOKEN_LEN + 20)
    result = parse_extras(long_token)
    assert len(result[0]) == _MAX_EXTRA_TOKEN_LEN
