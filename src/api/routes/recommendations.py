"""POST /recommendations — main recommendation endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from src.api.dependencies import get_orchestrator
from src.api.models import RecommendationItem, RecommendationRequest, RecommendationResponse
from src.models.preferences import UserPreferences
from src.recommendation.contracts import PipelineRequest
from src.recommendation.orchestrator import RecommendationOrchestrator

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/recommendations", response_model=RecommendationResponse, tags=["Recommendations"])
def recommendations(
    body: RecommendationRequest,
    orchestrator: RecommendationOrchestrator = Depends(get_orchestrator),
) -> RecommendationResponse:
    prefs = UserPreferences(
        location=body.location,
        budget=body.budget,
        cuisine=body.cuisine,
        min_rating=body.min_rating,
        extras=body.extras,
    )
    request = PipelineRequest(
        preferences=prefs,
        max_recommendations=body.max_recommendations,
    )

    pipeline_response = orchestrator.run(request)

    logger.info(
        "POST /recommendations filter=%s rec=%s fallback=%s latency=%dms",
        pipeline_response.filter_code,
        pipeline_response.rec_code,
        pipeline_response.used_fallback,
        pipeline_response.latency_ms,
    )

    return RecommendationResponse(
        request_id=pipeline_response.request_id,
        recommendations=[
            RecommendationItem(
                restaurant_name=r.restaurant_name,
                cuisine=r.cuisine,
                rating=r.rating,
                estimated_cost=r.estimated_cost,
                explanation=r.explanation,
            )
            for r in pipeline_response.recommendations
        ],
        summary=pipeline_response.summary,
        filter_code=pipeline_response.filter_code,
        rec_code=pipeline_response.rec_code,
        used_fallback=pipeline_response.used_fallback,
        hints=pipeline_response.hints,
        latency_ms=pipeline_response.latency_ms,
        shortlist_size=pipeline_response.shortlist_size,
    )
