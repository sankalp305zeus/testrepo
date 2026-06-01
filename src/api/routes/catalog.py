"""GET /cities, GET /cuisines — catalog metadata endpoints."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends

from src.api.dependencies import get_catalog
from src.api.models import CitiesResponse, CuisinesResponse
from src.models.restaurant import Restaurant

router = APIRouter()

_TOP_N = 50


@router.get("/cities", response_model=CitiesResponse, tags=["Catalog"])
def cities(catalog: List[Restaurant] = Depends(get_catalog)) -> CitiesResponse:
    counts: dict[str, int] = {}
    for r in catalog:
        city = r.location.strip()
        if city and city != "Unknown":
            counts[city] = counts.get(city, 0) + 1
    ranked = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    return CitiesResponse(cities=[c for c, _ in ranked[:_TOP_N]])


@router.get("/cuisines", response_model=CuisinesResponse, tags=["Catalog"])
def cuisines(catalog: List[Restaurant] = Depends(get_catalog)) -> CuisinesResponse:
    counts: dict[str, int] = {}
    for r in catalog:
        for cuisine in r.cuisines:
            c = cuisine.strip()
            if c:
                counts[c] = counts.get(c, 0) + 1
    ranked = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    return CuisinesResponse(cuisines=[c for c, _ in ranked[:_TOP_N]])
