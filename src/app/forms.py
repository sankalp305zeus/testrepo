"""Form validation helpers for the Streamlit UI."""

from __future__ import annotations

from typing import List, Literal, Optional, Tuple

Budget = Literal["low", "medium", "high"]

MAX_LOCATION_LEN = 100
MAX_CUISINE_LEN = 100
MAX_EXTRA_LEN = 80
MAX_EXTRAS_COUNT = 10


def parse_extras(text: str) -> List[str]:
    """Split comma-separated extras into a deduplicated list."""
    if not text or not text.strip():
        return []
    parts = [p.strip() for p in text.split(",") if p.strip()]
    seen: set[str] = set()
    result: List[str] = []
    for part in parts:
        key = part.casefold()
        if key not in seen:
            seen.add(key)
            result.append(part[:MAX_EXTRA_LEN])
        if len(result) >= MAX_EXTRAS_COUNT:
            break
    return result


def validate_form(
    location: str,
    cuisine: str,
    min_rating: float,
    budget: str,
    extras_text: str = "",
) -> Tuple[List[str], Optional[Budget]]:
    """
    Validate sidebar form values.

    Returns (error_messages, normalized_budget). budget is None if invalid.
    """
    errors: List[str] = []

    loc = (location or "").strip()
    if not loc:
        errors.append("Location is required.")
    elif len(loc) > MAX_LOCATION_LEN:
        errors.append(f"Location must be at most {MAX_LOCATION_LEN} characters.")

    cuis = (cuisine or "").strip()
    if not cuis:
        errors.append("Cuisine is required.")
    elif len(cuis) > MAX_CUISINE_LEN:
        errors.append(f"Cuisine must be at most {MAX_CUISINE_LEN} characters.")

    try:
        rating = float(min_rating)
    except (TypeError, ValueError):
        errors.append("Minimum rating must be a number.")
        rating = -1.0
    else:
        if rating < 0 or rating > 5:
            errors.append("Minimum rating must be between 0 and 5.")

    normalized_budget: Optional[Budget] = None
    if budget not in ("low", "medium", "high"):
        errors.append("Please select a valid budget.")
    else:
        normalized_budget = budget  # type: ignore[assignment]

    if extras_text and len(extras_text) > 500:
        errors.append("Extras text is too long (max 500 characters).")

    return errors, normalized_budget
