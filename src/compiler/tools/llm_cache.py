"""
llm_cache.py
────────────
In-process LRU cache for LLM responses, keyed on (model, prompt_hash).

Why this exists:
  - The validator and repair agents may call the same model with nearly
    identical prompts across repair loop iterations.
  - CrewAI's built-in cache: true only caches tool call results, not raw
    LLM completions.
  - This cache sits one level higher and avoids redundant API calls when
    the same (model, prompt) pair is seen within a session.

Usage:
  from compiler.tools.llm_cache import llm_cache

  cached = llm_cache.get(model="deepseek/...", prompt="...")
  if cached is None:
      response = await call_llm(...)
      llm_cache.set(model="deepseek/...", prompt="...", response=response)

The cache is session-scoped (in-memory, not persisted). It is cleared
automatically when the session store cleans up after 1 hour.

Logs are intentionally verbose — remove logger.debug calls once stable.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections import OrderedDict
from typing import Optional

logger = logging.getLogger("protoflow.llm_cache")


class LLMResponseCache:
    """
    Thread-safe LRU cache for LLM responses.

    Parameters
    ----------
    max_size : int
        Maximum number of entries to keep in memory.
    ttl_seconds : int
        Time-to-live for each entry in seconds. Expired entries are evicted
        on the next get() call.
    """

    def __init__(self, max_size: int = 256, ttl_seconds: int = 3600) -> None:
        self._cache: OrderedDict[str, tuple[str, float]] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._hits = 0
        self._misses = 0
        logger.info(
            "[llm_cache] Initialised. max_size=%d, ttl=%ds.", max_size, ttl_seconds
        )

    # ── Key construction ──────────────────────────────────────────────────────

    @staticmethod
    def _make_key(model: str, prompt: str) -> str:
        """SHA-256 hash of (model, prompt) to keep keys compact."""
        raw = f"{model}::{prompt}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    # ── Public API ────────────────────────────────────────────────────────────

    def get(self, model: str, prompt: str) -> Optional[str]:
        """
        Return cached response or None.
        Moves the entry to the end (most-recently-used) on hit.
        """
        key = self._make_key(model, prompt)
        entry = self._cache.get(key)

        if entry is None:
            self._misses += 1
            logger.debug(
                "[llm_cache] MISS. model=%s. Total misses=%d.", model, self._misses
            )
            return None

        response, timestamp = entry
        age = time.monotonic() - timestamp

        if age > self._ttl:
            logger.debug(
                "[llm_cache] EXPIRED entry (age=%.1fs). model=%s.", age, model
            )
            del self._cache[key]
            self._misses += 1
            return None

        # Move to end (LRU update)
        self._cache.move_to_end(key)
        self._hits += 1
        logger.debug(
            "[llm_cache] HIT. model=%s. age=%.1fs. Total hits=%d.",
            model, age, self._hits,
        )
        return response

    def set(self, model: str, prompt: str, response: str) -> None:
        """Store a response. Evicts the oldest entry if at capacity."""
        key = self._make_key(model, prompt)

        if key in self._cache:
            # Update existing entry
            self._cache.move_to_end(key)
            self._cache[key] = (response, time.monotonic())
            logger.debug("[llm_cache] Updated existing entry. model=%s.", model)
            return

        if len(self._cache) >= self._max_size:
            evicted_key, _ = self._cache.popitem(last=False)
            logger.debug(
                "[llm_cache] Evicted oldest entry (cache full). key=%s.", evicted_key[:16]
            )

        self._cache[key] = (response, time.monotonic())
        logger.debug(
            "[llm_cache] Stored new entry. model=%s. Cache size=%d/%d.",
            model, len(self._cache), self._max_size,
        )

    def invalidate(self, model: str, prompt: str) -> bool:
        """Remove a specific entry. Returns True if it existed."""
        key = self._make_key(model, prompt)
        if key in self._cache:
            del self._cache[key]
            logger.debug("[llm_cache] Invalidated entry. model=%s.", model)
            return True
        return False

    def clear(self) -> None:
        """Clear all entries (called on session cleanup)."""
        count = len(self._cache)
        self._cache.clear()
        self._hits = 0
        self._misses = 0
        logger.info("[llm_cache] Cleared %d entries.", count)

    def stats(self) -> dict:
        """Return cache statistics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": round(hit_rate, 1),
            "ttl_seconds": self._ttl,
        }


# ── Module-level singleton ────────────────────────────────────────────────────
# Import this instance everywhere instead of creating new ones.

llm_cache = LLMResponseCache(max_size=256, ttl_seconds=3600)
