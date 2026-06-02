"""FastAPI application — Layer 6 REST API.

Startup:
    uvicorn src.api.main:app --reload --port 8000
    # or:
    make api

Docs:
    http://localhost:8000/docs   (Swagger UI)
    http://localhost:8000/redoc  (ReDoc)

Environment:
    GROQ_API_KEY / LLM_API_KEY  — Groq credentials
    MOCK_LLM=1                  — skip Groq, return fallback rankings
    ALLOWED_ORIGINS             — comma-separated CORS origins (default: *)
    CACHE_TTL_SECONDS           — LRU cache TTL (default: 300)
    DISABLE_CACHE=1             — bypass result cache
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import catalog, health, recommendations
from src.data.ingest import load_catalog
from src.recommendation.cache import build_cache

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — load catalog and build cache once at startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — loading restaurant catalog...")
    preloaded_catalog = getattr(app.state, "catalog", None)
    try:
        app.state.catalog = load_catalog()
        logger.info("Catalog loaded: %d restaurants", len(app.state.catalog))
    except Exception as exc:
        logger.error("Catalog load failed: %s", exc)
        if preloaded_catalog is not None:
            app.state.catalog = preloaded_catalog
            logger.info("Using preloaded catalog: %d restaurants", len(app.state.catalog))
        else:
            app.state.catalog = []

    app.state.pipeline_cache = build_cache()
    logger.info("Pipeline cache: %s", app.state.pipeline_cache)

    yield

    logger.info("Shutting down.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AI Restaurant Recommendations API",
    description=(
        "Powered by the Zomato dataset and Groq. "
        "Filter restaurants by location, budget, cuisine, and rating — "
        "then get AI-ranked picks with personalised explanations."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow frontend origin(s)
_origins_env = os.getenv("ALLOWED_ORIGINS", "*")
origins = [o.strip() for o in _origins_env.split(",")] if _origins_env != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(health.router)
app.include_router(catalog.router)
app.include_router(recommendations.router)
