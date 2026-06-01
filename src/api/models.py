"""Pydantic request/response models for the FastAPI layer.

These are the HTTP-level contracts (Layer 6). They map 1-to-1 with the
internal PipelineRequest / PipelineResponse but are Pydantic models so
FastAPI can validate, serialise, and document them automatically.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


Budget = Literal["low", "medium", "high"]


class RecommendationRequest(BaseModel):
    location: str = Field(..., min_length=1, max_length=100, examples=["Bangalore"])
    budget: Budget = Field(..., examples=["medium"])
    cuisine: str = Field(..., min_length=1, max_length=100, examples=["North Indian"])
    min_rating: float = Field(default=0.0, ge=0.0, le=5.0, examples=[4.0])
    extras: List[str] = Field(default_factory=list, examples=[["family-friendly"]])
    max_recommendations: int = Field(default=5, ge=1, le=10, examples=[5])

    model_config = {
        "json_schema_extra": {
            "example": {
                "location": "Bangalore",
                "budget": "medium",
                "cuisine": "North Indian",
                "min_rating": 4.0,
                "extras": [],
                "max_recommendations": 5,
            }
        }
    }


class RecommendationItem(BaseModel):
    restaurant_name: str
    cuisine: str
    rating: float
    estimated_cost: float
    explanation: str


class RecommendationResponse(BaseModel):
    request_id: str
    recommendations: List[RecommendationItem]
    summary: Optional[str]
    filter_code: str
    rec_code: str
    used_fallback: bool
    hints: List[str]
    latency_ms: int
    shortlist_size: int


class HealthResponse(BaseModel):
    status: str
    catalog_size: int
    groq_configured: bool
    mock_mode: bool


class CitiesResponse(BaseModel):
    cities: List[str]


class CuisinesResponse(BaseModel):
    cuisines: List[str]
