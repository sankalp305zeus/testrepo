"""GET /health — system status."""

from __future__ import annotations

import os

from fastapi import APIRouter, Request

from src.api.models import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["System"])
def health(request: Request) -> HealthResponse:
    catalog = getattr(request.app.state, "catalog", None)
    groq_key = bool(os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY"))
    mock_mode = os.getenv("MOCK_LLM", "").lower() in ("1", "true", "yes")

    return HealthResponse(
        status="ok",
        catalog_size=len(catalog) if catalog else 0,
        groq_configured=groq_key,
        mock_mode=mock_mode,
    )
