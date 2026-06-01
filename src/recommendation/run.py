"""CLI entry point — runs the full pipeline via RecommendationOrchestrator.

Usage:
    python -m src.recommendation.run --location Bangalore --budget medium \\
        --cuisine "North Indian" --min-rating 4.0

Offline demo (no Groq call):
    MOCK_LLM=1 python -m src.recommendation.run
"""

from __future__ import annotations

import argparse
import logging

from dotenv import load_dotenv

from src.models.preferences import UserPreferences
from src.recommendation.contracts import PipelineRequest
from src.recommendation.orchestrator import RecommendationOrchestrator


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate Groq-powered restaurant recommendations")
    p.add_argument("--location", default="Bangalore")
    p.add_argument("--budget", choices=["low", "medium", "high"], default="medium")
    p.add_argument("--cuisine", default="North Indian")
    p.add_argument("--min-rating", type=float, default=4.0, dest="min_rating")
    p.add_argument("--extras", nargs="*", default=[])
    p.add_argument("--max-results", type=int, default=5, dest="max_results")
    p.add_argument("--no-cache", action="store_true", help="Disable result cache for this run")
    return p.parse_args()


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    args = _parse_args()
    prefs = UserPreferences(
        location=args.location,
        budget=args.budget,
        cuisine=args.cuisine,
        min_rating=args.min_rating,
        extras=list(args.extras),
    )

    orchestrator = RecommendationOrchestrator(auto_build_cache=not args.no_cache)
    request = PipelineRequest(preferences=prefs, max_recommendations=args.max_results)
    response = orchestrator.run(request)

    print(f"\nrequest_id : {response.request_id}")
    print(f"filter     : {response.filter_code}  shortlist={response.shortlist_size}")
    print(f"rec        : {response.rec_code}  fallback={response.used_fallback}")
    print(f"latency    : {response.latency_ms} ms")

    if response.filter_code != "OK":
        print(f"\n{response.rec_code}: no restaurants matched.")
        for hint in response.hints:
            print(f"  Hint: {hint}")
        return

    if response.summary:
        print(f"\nSummary: {response.summary}")

    if not response.recommendations:
        print("No recommendations generated.")
        return

    print(f"\nTop {len(response.recommendations)} picks:\n")
    for i, rec in enumerate(response.recommendations, 1):
        print(f"{i}. {rec.restaurant_name}")
        print(f"   {rec.cuisine} | ★ {rec.rating} | ₹{rec.estimated_cost:.0f}")
        print(f"   {rec.explanation}\n")


if __name__ == "__main__":
    main()
