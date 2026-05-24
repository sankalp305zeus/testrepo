"""CLI to exercise the filter engine against the cached catalog."""

from __future__ import annotations

import argparse
import logging
import time

from src.data.ingest import load_catalog
from src.filter.engine import filter_restaurants
from src.models.preferences import UserPreferences

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Filter restaurant catalog")
    parser.add_argument("--location", default="Bangalore")
    parser.add_argument("--budget", choices=["low", "medium", "high"], default="medium")
    parser.add_argument("--cuisine", default="North Indian")
    parser.add_argument("--min-rating", type=float, default=4.0)
    parser.add_argument("--extras", nargs="*", default=[])
    parser.add_argument("--max-results", type=int, default=10)
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
    result = filter_restaurants(catalog, prefs, max_results=args.max_results)
    elapsed = time.perf_counter() - start

    print(f"\nFilter completed in {elapsed:.3f}s ({len(catalog)} restaurants in catalog)")
    print(f"Code: {result.code}")

    if result.is_empty:
        print(f"Message: {result.message}")
        for hint in result.hints:
            print(f"  • {hint}")
        return

    print(f"Matches: {len(result.restaurants)} (showing up to {args.max_results})\n")
    for i, r in enumerate(result.restaurants, 1):
        print(
            f"{i:2}. {r.name} | {r.location} | {r.cuisine_display()} | "
            f"★ {r.rating} | ₹{r.cost_for_two:.0f}"
        )


if __name__ == "__main__":
    main()
