"""CLI: filter catalog then generate LLM recommendations."""

from __future__ import annotations

import argparse
import logging
import os
import time

from dotenv import load_dotenv

from src.data.ingest import load_catalog
from src.filter.engine import filter_restaurants
from src.models.preferences import UserPreferences
from src.recommendation.engine import recommend


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Generate restaurant recommendations")
    parser.add_argument("--location", default="Bangalore")
    parser.add_argument("--budget", choices=["low", "medium", "high"], default="medium")
    parser.add_argument("--cuisine", default="North Indian")
    parser.add_argument("--min-rating", type=float, default=4.0)
    parser.add_argument("--extras", nargs="*", default=[])
    parser.add_argument("--max-results", type=int, default=5)
    args = parser.parse_args()

    prefs = UserPreferences(
        location=args.location,
        budget=args.budget,
        cuisine=args.cuisine,
        min_rating=args.min_rating,
        extras=list(args.extras),
    )

    start = time.perf_counter()
    catalog = load_catalog()
    filter_result = filter_restaurants(catalog, prefs)

    if filter_result.is_empty:
        print(f"\nFilter: {filter_result.code} — {filter_result.message}")
        for hint in filter_result.hints:
            print(f"  • {hint}")
        return

    print(f"\nShortlist: {len(filter_result.restaurants)} restaurants")

    rec_result = recommend(
        filter_result.restaurants,
        prefs,
        max_recommendations=args.max_results,
    )
    elapsed = time.perf_counter() - start

    print(f"Recommendation code: {rec_result.code} (fallback={rec_result.used_fallback})")
    if rec_result.message:
        print(rec_result.message)
    if rec_result.summary:
        print(f"\nSummary: {rec_result.summary}\n")

    if not rec_result.recommendations:
        print("No recommendations generated.")
        return

    print(f"Top {len(rec_result.recommendations)} recommendations ({elapsed:.2f}s total):\n")
    for i, rec in enumerate(rec_result.recommendations, 1):
        print(f"{i}. {rec.restaurant_name}")
        print(f"   Cuisine: {rec.cuisine} | ★ {rec.rating} | ₹{rec.estimated_cost:.0f}")
        print(f"   {rec.explanation}\n")

    if os.getenv("MOCK_LLM"):
        print("(MOCK_LLM=1 — using mock or fallback responses)")


if __name__ == "__main__":
    main()
