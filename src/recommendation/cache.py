"""In-memory LRU result cache for the recommendation pipeline.

Cache key: deterministic hash of the normalised UserPreferences fields.
Cache value: PipelineResponse (the full orchestrator output).

Configuration (via env vars):
  CACHE_TTL_SECONDS  — entry lifetime in seconds (default: 300 / 5 min)
  DISABLE_CACHE      — set to "1" to bypass the cache entirely

The cache is intentionally simple: a time-aware OrderedDict with LRU eviction.
No external dependency required.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from collections import OrderedDict
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_TTL = 300      # seconds
_DEFAULT_MAX = 128      # max entries before LRU eviction


class ResponseCache:
    """Thread-unsafe in-memory LRU cache with per-entry TTL."""

    def __init__(
        self,
        ttl_seconds: int = _DEFAULT_TTL,
        max_size: int = _DEFAULT_MAX,
    ) -> None:
        self._ttl = ttl_seconds
        self._max = max_size
        self._store: OrderedDict[str, tuple] = OrderedDict()  # key → (response, expires_at)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str):
        """Return cached PipelineResponse, or None on miss / expiry."""
        entry = self._store.get(key)
        if entry is None:
            return None
        response, expires_at = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            logger.debug("Cache expired: %s", key[:8])
            return None
        # Move to end (most-recently used)
        self._store.move_to_end(key)
        logger.info("Cache hit: key=%s", key[:8])
        return response

    def set(self, key: str, response) -> None:
        """Store a PipelineResponse; evict LRU entry if at capacity."""
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (response, time.monotonic() + self._ttl)
        if len(self._store) > self._max:
            evicted, _ = self._store.popitem(last=False)
            logger.debug("Cache evicted LRU: %s", evicted[:8])

    def clear(self) -> None:
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:  # pragma: no cover
        return f"ResponseCache(size={self.size}, ttl={self._ttl}s)"


def make_cache_key(preferences) -> str:
    """Deterministic cache key from normalised UserPreferences fields."""
    parts = "|".join([
        preferences.location_normalized.lower(),
        preferences.budget,
        preferences.cuisine_normalized.lower(),
        str(preferences.min_rating),
        ",".join(sorted(e.lower() for e in preferences.extras_normalized)),
    ])
    return hashlib.sha256(parts.encode()).hexdigest()


def build_cache() -> Optional[ResponseCache]:
    """Return a ResponseCache unless DISABLE_CACHE=1 is set."""
    if os.getenv("DISABLE_CACHE", "").lower() in ("1", "true", "yes"):
        logger.info("ResponseCache disabled (DISABLE_CACHE=1)")
        return None
    ttl = int(os.getenv("CACHE_TTL_SECONDS", str(_DEFAULT_TTL)))
    logger.info("ResponseCache enabled (ttl=%ds)", ttl)
    return ResponseCache(ttl_seconds=ttl)
