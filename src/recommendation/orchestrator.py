"""RecommendationOrchestrator — single entry point for the full pipeline.

Flow:
  1. Check cache (skip steps 2-3 on hit)
  2. Filter catalog by preferences → shortlist
  3. Call LLM recommendation engine → ranked results
  4. Build PipelineResponse; store in cache; return

Every caller — Streamlit UI, CLI, future REST API — calls orchestrator.run()
and receives a PipelineResponse. Internal types (FilterResult, RecommendationResult)
never leave this module.

Logging convention (one INFO line per step):
  {"step": "cache",   "hit": true,  "key": "ab12...", "latency_ms": 0}
  {"step": "filter",  "code": "OK", "shortlist": 12,  "latency_ms": 4}
  {"step": "llm",     "code": "OK", "fallback": false, "latency_ms": 6821}
  {"step": "total",   "latency_ms": 6825}
"""

from __future__ import annotations

import json
import logging
import time
from typing import List, Optional

from src.data.ingest import load_catalog
from src.filter.engine import filter_restaurants
from src.llm.client import LLMClient
from src.models.restaurant import Restaurant
from src.recommendation.cache import ResponseCache, build_cache, make_cache_key
from src.recommendation.contracts import PipelineRequest, PipelineResponse
from src.recommendation.engine import recommend

logger = logging.getLogger(__name__)


class RecommendationOrchestrator:
    """Runs the full filter → LLM → cache pipeline for a single request."""

    def __init__(
        self,
        catalog: Optional[List[Restaurant]] = None,
        llm_client: Optional[LLMClient] = None,
        cache: Optional[ResponseCache] = None,
        *,
        auto_build_cache: bool = True,
    ) -> None:
        """
        Args:
            catalog:          Pre-loaded restaurant list. If None, load_catalog() is called
                              on the first run (result is cached on the instance).
            llm_client:       Override the Groq client (useful in tests).
            cache:            ResponseCache instance. If None and auto_build_cache is True,
                              build_cache() is called (honours DISABLE_CACHE env var).
            auto_build_cache: Set False to disable cache entirely without env var.
        """
        self._catalog = catalog
        self._llm_client = llm_client
        self._cache: Optional[ResponseCache] = (
            cache if cache is not None
            else (build_cache() if auto_build_cache else None)
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, request: PipelineRequest) -> PipelineResponse:
        """Execute the recommendation pipeline and return a PipelineResponse.

        Never raises — all errors are captured and reflected in the response.
        """
        t_total = time.perf_counter()

        # 1. Cache lookup
        cache_key = make_cache_key(request.preferences)
        if self._cache is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                # Preserve original request_id but keep everything else
                response = PipelineResponse(
                    request_id=request.request_id,
                    recommendations=cached.recommendations,
                    filter_code=cached.filter_code,
                    rec_code=cached.rec_code,
                    used_fallback=cached.used_fallback,
                    hints=cached.hints,
                    summary=cached.summary,
                    latency_ms=0,
                    shortlist_size=cached.shortlist_size,
                )
                _log_step("cache", hit=True, key=cache_key[:8], latency_ms=0)
                return response
            _log_step("cache", hit=False, key=cache_key[:8], latency_ms=0)

        # 2. Load catalog (lazy, cached on instance after first call)
        catalog = self._get_catalog()

        # 3. Filter
        t_filter = time.perf_counter()
        filter_result = filter_restaurants(catalog, request.preferences)
        filter_ms = _ms(t_filter)
        _log_step("filter", code=filter_result.code,
                  shortlist=len(filter_result.restaurants), latency_ms=filter_ms)

        if filter_result.is_empty:
            response = PipelineResponse(
                request_id=request.request_id,
                recommendations=[],
                filter_code=filter_result.code,
                rec_code="EMPTY_SHORTLIST",
                used_fallback=False,
                hints=filter_result.hints,
                summary=None,
                latency_ms=_ms(t_total),
                shortlist_size=0,
            )
            _log_step("total", latency_ms=_ms(t_total))
            return response

        # 4. LLM recommendation
        t_llm = time.perf_counter()
        rec_result = recommend(
            filter_result.restaurants,
            request.preferences,
            llm_client=self._llm_client,
            max_recommendations=request.max_recommendations,
        )
        llm_ms = _ms(t_llm)
        _log_step("llm", code=rec_result.code,
                  fallback=rec_result.used_fallback, latency_ms=llm_ms)

        total_ms = _ms(t_total)
        _log_step("total", latency_ms=total_ms)

        response = PipelineResponse(
            request_id=request.request_id,
            recommendations=rec_result.recommendations,
            filter_code=filter_result.code,
            rec_code=rec_result.code,
            used_fallback=rec_result.used_fallback,
            hints=[],
            summary=rec_result.summary,
            latency_ms=total_ms,
            shortlist_size=len(filter_result.restaurants),
        )

        # 5. Store in cache (only successful LLM or fallback results)
        if self._cache is not None:
            self._cache.set(cache_key, response)

        return response

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_catalog(self) -> List[Restaurant]:
        if self._catalog is None:
            self._catalog = load_catalog()
        return self._catalog


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _log_step(step: str, **kwargs) -> None:
    payload = json.dumps({"step": step, **kwargs}, ensure_ascii=False)
    logger.info("pipeline %s", payload)
