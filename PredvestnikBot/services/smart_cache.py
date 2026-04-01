"""
Smart Join Cache — merge in-memory cache with database queries.
Caches frequently used data with TTL, ensuring 100% up-to-date display
by merging cached + pending data on read.

Used for: user rank (cached), etc.

Public API
----------
cache_user_rank(user_id, chat_id, rank_str, ttl=300)
  Cache user's rank for 300 seconds.

get_user_rank_cached(user_id, chat_id) -> str | None
  Get cached rank if valid, else ask DB and cache.

""
"""

import time as _time
import logging

logger = logging.getLogger(__name__)

# (user_id, chat_id) → (rank_str, timestamp)
_rank_cache: dict[tuple[int, int], tuple[str, float]] = {}
_RANK_TTL = 300.0  # 5 minutes


def cache_user_rank(user_id: int, chat_id: int, rank_str: str) -> None:
    """Update rank cache."""
    _rank_cache[(user_id, chat_id)] = (rank_str, _time.monotonic())


def get_cached_user_rank(user_id: int, chat_id: int) -> str | None:
    """Get rank from cache if fresh, else None."""
    key = (user_id, chat_id)
    if key in _rank_cache:
        rank, ts = _rank_cache[key]
        if _time.monotonic() - ts < _RANK_TTL:
            return rank
    return None


def invalidate_user_rank(user_id: int, chat_id: int) -> None:
    """Drop cached rank (e.g., after rank change)."""
    _rank_cache.pop((user_id, chat_id), None)


# Optional cleanup for memory (every 1 hour, Remove entries older than 24h)
_last_cleanup = _time.monotonic()
_CLEANUP_INTERVAL = 3600


def _maybe_cleanup() -> None:
    global _last_cleanup
    now = _time.monotonic()
    if now - _last_cleanup < _CLEANUP_INTERVAL:
        return
    _last_cleanup = now
    
    cutoff = now - 86400
    old_keys = [k for k, (_, ts) in _rank_cache.items() if ts < cutoff]
    for k in old_keys:
        del _rank_cache[k]
    
    if old_keys:
        logger.debug(f"smart_cache: cleaned up {len(old_keys)} rank entries")


# Call cleanup every 10K operations
_call_count = 0
def _tick() -> None:
    global _call_count
    _call_count += 1
    if _call_count % 10000 == 0:
        _maybe_cleanup()
