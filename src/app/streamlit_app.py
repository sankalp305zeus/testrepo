"""
Streamlit UI — Phase 4 presentation layer.

Run: streamlit run src/app/streamlit_app.py
"""

from __future__ import annotations

import os
from typing import List, Optional

import streamlit as st
from dotenv import load_dotenv

from src.app.forms import parse_extras, validate_form
from src.data.ingest import load_catalog
from src.filter.engine import filter_restaurants
from src.models.preferences import UserPreferences
from src.models.restaurant import Restaurant
from src.recommendation.engine import recommend

load_dotenv()

st.set_page_config(
    page_title="Restaurant Recommendations",
    page_icon="🍽️",
    layout="wide",
)


@st.cache_data(show_spinner="Loading restaurant catalog…")
def _cached_catalog() -> List[Restaurant]:
    return load_catalog()


@st.cache_data(show_spinner=False)
def _city_options(catalog: List[Restaurant]) -> List[str]:
    counts: dict[str, int] = {}
    for r in catalog:
        city = r.location.strip()
        if city and city != "Unknown":
            counts[city] = counts.get(city, 0) + 1
    ranked = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    return [city for city, _ in ranked[:25]]


def _render_recommendations(rec_result, used_fallback: bool) -> None:
    if rec_result.summary:
        st.info(rec_result.summary)

    if used_fallback:
        st.warning(
            "Showing rule-based rankings (Groq unavailable or MOCK_LLM=1). "
            + (rec_result.message or "")
        )

    for i, rec in enumerate(rec_result.recommendations, 1):
        with st.container(border=True):
            st.subheader(f"{i}. {rec.restaurant_name}")
            col1, col2, col3 = st.columns(3)
            col1.metric("Rating", f"{rec.rating:.1f} ★")
            col2.metric("Cost for two", f"₹{rec.estimated_cost:.0f}")
            col3.write(f"**Cuisine:** {rec.cuisine}")
            st.write(rec.explanation)


def main() -> None:
    st.title("🍽️ AI Restaurant Recommendations")
    st.caption(
        "Powered by Zomato data + Groq. "
        "Set `GROQ_API_KEY` in `.env`, or `MOCK_LLM=1` for offline mode."
    )

    try:
        catalog = _cached_catalog()
    except Exception:
        st.error(
            "Could not load the restaurant catalog. "
            "Run `python -m src.data.ingest` first, then refresh this page."
        )
        return

    cities = _city_options(catalog)
    default_city = "Bangalore" if "Bangalore" in cities else (cities[0] if cities else "")

    with st.sidebar:
        st.header("Your preferences")
        location = st.selectbox(
            "Location",
            options=cities if cities else [default_city],
            index=cities.index(default_city) if default_city in cities else 0,
        )
        location_custom = st.text_input(
            "Or enter another location",
            placeholder="e.g. Banashankari",
            max_chars=100,
        )
        effective_location = location_custom.strip() or location

        budget = st.selectbox("Budget", options=["low", "medium", "high"], index=1)
        cuisine = st.text_input("Cuisine", value="North Indian", max_chars=100)
        min_rating = st.slider("Minimum rating", min_value=0.0, max_value=5.0, value=4.0, step=0.1)
        extras_text = st.text_input(
            "Extras (comma-separated)",
            placeholder="family-friendly, quick service",
        )
        max_results = st.slider("Max recommendations", min_value=3, max_value=10, value=5)
        submitted = st.button("Get recommendations", type="primary", use_container_width=True)

    if not submitted:
        st.markdown(
            """
            ### How it works
            1. **Filter** — We narrow thousands of restaurants using your preferences.
            2. **Groq** — An LLM ranks the shortlist and explains each pick.
            3. **Results** — Top matches with cuisine, rating, cost, and AI explanation.

            Adjust preferences in the sidebar and click **Get recommendations**.
            """
        )
        st.metric("Restaurants in catalog", f"{len(catalog):,}")
        return

    errors, normalized_budget = validate_form(
        effective_location, cuisine, min_rating, budget, extras_text
    )
    if errors:
        for msg in errors:
            st.error(msg)
        return

    if normalized_budget is None:
        return

    try:
        prefs = UserPreferences(
            location=effective_location,
            budget=normalized_budget,
            cuisine=cuisine.strip(),
            min_rating=float(min_rating),
            extras=parse_extras(extras_text),
        )
    except ValueError as exc:
        st.error(str(exc))
        return

    with st.spinner("Filtering restaurants…"):
        filter_result = filter_restaurants(catalog, prefs)

    if filter_result.is_empty:
        st.warning(filter_result.message or "No restaurants match your filters.")
        for hint in filter_result.hints:
            st.info(hint)
        return

    st.success(f"Found {len(filter_result.restaurants)} candidates in shortlist.")

    groq_configured = bool(
        os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY")
    ) and os.getenv("MOCK_LLM", "").lower() not in ("1", "true", "yes")

    spinner_msg = (
        "Asking Groq for personalized recommendations…"
        if groq_configured
        else "Generating recommendations (offline mode)…"
    )

    try:
        with st.spinner(spinner_msg):
            rec_result = recommend(
                filter_result.restaurants,
                prefs,
                max_recommendations=max_results,
            )
    except Exception:
        st.error(
            "Something went wrong while generating recommendations. "
            "Check your `GROQ_API_KEY` or try `MOCK_LLM=1` in `.env`."
        )
        return

    if not rec_result.recommendations:
        st.warning(rec_result.message or "No recommendations could be generated.")
        return

    st.divider()
    _render_recommendations(rec_result, rec_result.used_fallback)


if __name__ == "__main__":
    main()
