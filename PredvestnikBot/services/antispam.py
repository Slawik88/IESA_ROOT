"""
Advanced antispam — Token Bucket algorithm in-memory.
Blocks spammers BEFORE database queries, with per-user and per-chat limits.

Public API
----------
check_spam(user_id, chat_id, event_type='message') -> bool
  Returns True if the user should be blocked (spam detected).

reset_user_limits(user_id, chat_id) -> None
  Clear buckets after successful action (e.g., after user banned).
"""

import time as _time
import logging

logger = logging.getLogger(__name__)

# Token Bucket: (user_id, chat_id, event_type) → (tokens, last_refill_time)
_buckets: dict[tuple[int, int, str], tuple[float, float]] = {}

# Configuration (tunable)
_CONFIG = {
    # Refill rate: tokens returned per second
    'message': {
        'capacity': 20,      # max tokens (can hold 20 messages worth)
        'refill_rate': 1.0,  # 1 token per second (~60 per minute)
    },
    'command': {
        'capacity': 10,
        'refill_rate': 0.2,  # 0.2 tokens per second (~12 per minute)
    },
    'action': {
        'capacity': 5,
        'refill_rate': 0.1,  # 0.1 tokens per second (~6 per minute)
    },
}


def check_spam(user_id: int, chat_id: int, event_type: str = 'message') -> bool:
    """
    Check if user should be blocked. Uses Token Bucket algorithm.
    
    Args:
        user_id: Telegram user ID
        chat_id: Telegram chat ID
        event_type: 'message', 'command', or 'action'
    
    Returns:
        True if spam (block user), False if OK (allow).
    """
    if event_type not in _CONFIG:
        event_type = 'message'
    
    config = _CONFIG[event_type]
    capacity = config['capacity']
    refill_rate = config['refill_rate']
    
    now = _time.time()
    key = (user_id, chat_id, event_type)
    
    # Initialize or refill bucket
    if key not in _buckets:
        _buckets[key] = (capacity, now)
        tokens, _ = _buckets[key]
    else:
        tokens, last_refill = _buckets[key]
        elapsed = now - last_refill
        tokens = min(capacity, tokens + elapsed * refill_rate)
    
    # Try to consume 1 token
    if tokens >= 1.0:
        _buckets[key] = (tokens - 1.0, now)
        return False  # OK
    else:
        _buckets[key] = (tokens, now)
        return True  # SPAM


def reset_user_limits(user_id: int, chat_id: int) -> None:
    """Clear all buckets for a user in a chat (e.g., after banning)."""
    keys_to_delete = [k for k in _buckets if k[0] == user_id and k[1] == chat_id]
    for k in keys_to_delete:
        del _buckets[k]
    logger.debug(f"antispam: reset {len(keys_to_delete)} buckets for user {user_id} in chat {chat_id}")


# Optional: Clean up expired buckets every ~1 hour to prevent memory leak
_last_cleanup = _time.time()
_CLEANUP_INTERVAL = 3600  # seconds


def _maybe_cleanup() -> None:
    """Periodically remove buckets older than 24 hours (memory leak prevention)."""
    global _last_cleanup
    now = _time.time()
    if now - _last_cleanup < _CLEANUP_INTERVAL:
        return
    _last_cleanup = now
    
    cutoff = now - 86400  # 24 hours
    old_keys = [k for k, (_, last_refill) in _buckets.items() if last_refill < cutoff]
    for k in old_keys:
        del _buckets[k]
    if old_keys:
        logger.debug(f"antispam: cleaned up {len(old_keys)} old buckets")


# Trigger cleanup on every call (O(1) amortized)
_call_count = 0
def _tick_cleanup() -> None:
    global _call_count
    _call_count += 1
    if _call_count % 10000 == 0:
        _maybe_cleanup()

check_spam.__wrapped__ = check_spam
_orig_check_spam = check_spam
def check_spam(user_id: int, chat_id: int, event_type: str = 'message') -> bool:
    _tick_cleanup()
    return _orig_check_spam(user_id, chat_id, event_type)
