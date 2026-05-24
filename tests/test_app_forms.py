"""Tests for Streamlit form validation."""

import pytest

from src.app.forms import parse_extras, validate_form


def test_validate_form_ok():
    errors, budget = validate_form("Bangalore", "North Indian", 4.0, "medium")
    assert errors == []
    assert budget == "medium"


def test_validate_form_missing_location():
    errors, budget = validate_form("", "Italian", 4.0, "low")
    assert "Location is required" in errors[0]
    assert budget == "low"


def test_validate_form_rating_out_of_range():
    errors, _ = validate_form("Bangalore", "Italian", 6.0, "low")
    assert any("between 0 and 5" in e for e in errors)


def test_validate_form_invalid_budget():
    errors, budget = validate_form("Bangalore", "Italian", 4.0, "luxury")
    assert budget is None
    assert any("budget" in e.lower() for e in errors)


def test_parse_extras_dedupes():
    assert parse_extras("quick, family, quick") == ["quick", "family"]
