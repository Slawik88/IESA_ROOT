"""Telegram bot — configuration helpers."""
import hashlib
import os

# Telegram Bot API base URL template
TG_BASE = "https://api.telegram.org/bot{token}/{method}"

# Cache settings for link codes (Method A)
LINK_CODE_PREFIX = "tg_link_code:"
LINK_CODE_TTL    = 600   # 10 minutes

# Rate-limit: max commands per user per window
RATE_LIMIT_COUNT  = 10
RATE_LIMIT_WINDOW = 60   # seconds


def token() -> str:
    """Return bot token from env."""
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def webhook_secret() -> str:
    """Return webhook secret path segment.

    Falls back to sha256(token)[:20] if TELEGRAM_WEBHOOK_SECRET is not set.
    """
    explicit = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if explicit:
        return explicit
    t = token()
    if not t:
        return ""
    return hashlib.sha256(t.encode()).hexdigest()[:20]


def bot_name() -> str:
    return os.environ.get("TELEGRAM_BOT_NAME", "").strip()


# ── Master kill-switch ──────────────────────────────────────────────────────
# Set to True when bot should handle incoming updates.
# False = webhook accepted but silently ignored (safe disable).
BOT_ACTIVE = False


def is_configured() -> bool:
    return bool(token())


def is_active() -> bool:
    """Return True only if bot is configured AND BOT_ACTIVE is True."""
    return BOT_ACTIVE and is_configured()


def api_url(method: str) -> str:
    return TG_BASE.format(token=token(), method=method)
