"""FastAPI shared dependencies — catalog and orchestrator singletons."""

from __future__ import annotations

from typing import List

from fastapi import Depends, HTTPException, Request

from src.models.restaurant import Restaurant
from src.recommendation.cache import ResponseCache
from src.recommendation.orchestrator import RecommendationOrchestrator


def get_catalog(request: Request) -> List[Restaurant]:
    catalog = getattr(request.app.state, "catalog", None)
    if not catalog:
        raise HTTPException(status_code=503, detail="Catalog unavailable. Run data ingest first.")
    return catalog


def get_pipeline_cache(request: Request) -> ResponseCache:
    return request.app.state.pipeline_cache


def get_orchestrator(
    catalog: List[Restaurant] = Depends(get_catalog),
    cache: ResponseCache = Depends(get_pipeline_cache),
) -> RecommendationOrchestrator:
    return RecommendationOrchestrator(
        catalog=catalog,
        cache=cache,
        auto_build_cache=False,
    )
