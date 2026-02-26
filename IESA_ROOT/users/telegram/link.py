"""Account linking helpers.

Method A — 6-digit code via /link command.
Method B — Telegram Login Widget HMAC verification.
"""
import hashlib
import hmac
import random
import string
from typing import Any

from .config import LINK_CODE_PREFIX, LINK_CODE_TTL, token


# ── Method A — code ────────────────────────────────────────────────────────

def generate_link_code(chat_id: int) -> str:
    """Generate a 6-digit one-time code stored in Django cache (10 min TTL)."""
    from django.core.cache import cache
    code = "".join(random.choices(string.digits, k=6))
    cache.set(f"{LINK_CODE_PREFIX}{code}", str(chat_id), timeout=LINK_CODE_TTL)
    return code


def consume_link_code(code: str) -> str | None:
    """Return chat_id for a valid code and delete it. None if expired/invalid."""
    from django.core.cache import cache
    key = f"{LINK_CODE_PREFIX}{code.strip()}"
    chat_id = cache.get(key)
    if chat_id:
        cache.delete(key)
    return chat_id


# ── Method B — widget ──────────────────────────────────────────────────────

def verify_telegram_auth(data: dict[str, Any]) -> bool:
    """Verify HMAC-SHA256 signature from Telegram Login Widget."""
    t = token()
    if not t:
        return False
    received_hash = data.get("hash", "")
    check_data = {k: v for k, v in data.items() if k != "hash"}
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(check_data.items()))
    secret_key = hashlib.sha256(t.encode()).digest()
    computed = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, received_hash)
