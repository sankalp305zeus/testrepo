"""Form validation helpers for the Streamlit presentation layer.

All validation is pure (no Streamlit imports) so it can be unit-tested directly.
"""

from __future__ import annotations

from typing import List, Literal, Optional, Tuple

Budget = Literal["low", "medium", "high"]
VALID_BUDGETS = ("low", "medium", "high")

_MAX_LOCATION_LEN = 100
_MAX_CUISINE_LEN = 100
_MAX_EXTRAS_TEXT_LEN = 500
_MAX_EXTRA_TOKEN_LEN = 80
_MAX_EXTRAS_COUNT = 10


def parse_extras(text: str) -> List[str]:
    """Split a comma-separated extras string into a deduplicated list.

    Each token is trimmed and capped at _MAX_EXTRA_TOKEN_LEN characters.
    Returns at most _MAX_EXTRAS_COUNT entries.
    """
    if not text or not text.strip():
        return []

    seen: set[str] = set()
    result: List[str] = []
    for part in text.split(","):
        token = part.strip()[:_MAX_EXTRA_TOKEN_LEN]
        if not token:
            continue
        key = token.casefold()
        if key not in seen:
            seen.add(key)
            result.append(token)
        if len(result) >= _MAX_EXTRAS_COUNT:
            break
    return result


def validate_form(
    location: str,
    cuisine: str,
    min_rating: float,
    budget: str,
    extras_text: str = "",
) -> Tuple[List[str], Optional[Budget]]:
    """Validate user-supplied form values.

    Returns (error_messages, normalised_budget).
    normalised_budget is None when budget is invalid.
    """
    errors: List[str] = []

    # --- location ---
    loc = (location or "").strip()
    if not loc:
        errors.append("Location is required.")
    elif len(loc) > _MAX_LOCATION_LEN:
        errors.append(f"Location must be at most {_MAX_LOCATION_LEN} characters.")

    # --- cuisine ---
    cuis = (cuisine or "").strip()
    if not cuis:
        errors.append("Cuisine is required.")
    elif len(cuis) > _MAX_CUISINE_LEN:
        errors.append(f"Cuisine must be at most {_MAX_CUISINE_LEN} characters.")

    # --- min_rating ---
    try:
        rating = float(min_rating)
    except (TypeError, ValueError):
        errors.append("Minimum rating must be a number between 0 and 5.")
    else:
        if rating < 0 or rating > 5:
            errors.append("Minimum rating must be between 0 and 5.")

    # --- budget ---
    normalised_budget: Optional[Budget] = None
    if budget not in VALID_BUDGETS:
        errors.append("Please select a valid budget (low, medium, or high).")
    else:
        normalised_budget = budget  # type: ignore[assignment]

    # --- extras length guard (prompt-injection mitigation) ---
    if extras_text and len(extras_text) > _MAX_EXTRAS_TEXT_LEN:
        errors.append(f"Extras field is too long (max {_MAX_EXTRAS_TEXT_LEN} characters).")

    return errors, normalised_budget
