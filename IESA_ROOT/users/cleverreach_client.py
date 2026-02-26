"""
CleverReach REST API v3 client — handles OAuth2 token lifecycle and
transactional email delivery for IESA Sport.

Tokens are persisted in Django's cache (Redis in production).
When the cached access token is missing or expired the module transparently
obtains a new one using the refresh token stored in CLEVERREACH_REFRESH_TOKEN.

Usage::

    from users.cleverreach_client import send_cleverreach_email

    send_cleverreach_email(
        to_email='member@example.com',
        to_name='John Doe',
        subject='✅ Visit confirmed',
        html='<html>...</html>',
        text='Visit confirmed',
    )

Required DigitalOcean App Platform env vars
-------------------------------------------
    CLEVERREACH_CLIENT_ID      — OAuth app client ID
    CLEVERREACH_CLIENT_SECRET  — OAuth app client secret
    CLEVERREACH_ACCESS_TOKEN   — Current bearer token (bootstrap value)
    CLEVERREACH_REFRESH_TOKEN  — Refresh token (never expires while used)
    CLEVERREACH_SENDER_EMAIL   — Verified sender address (e.g. noreply@iesasport.ch)
    CLEVERREACH_SENDER_NAME    — Display name (default: IESA Sport)
"""

import logging
import time
from datetime import timedelta

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CR_BASE = "https://rest.cleverreach.com"
TOKEN_URL = f"{CR_BASE}/oauth/token.php"
API_V3 = f"{CR_BASE}/v3"

CACHE_KEY_TOKEN = "cleverreach_access_token"
CACHE_KEY_EXPIRY = "cleverreach_token_expiry"
# Refresh 5 minutes before actual expiry
REFRESH_BUFFER_SECONDS = 300


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------

def _cfg(name: str, default: str = "") -> str:
    """Read a CleverReach setting from Django settings or return default.

    Strips surrounding whitespace and newlines so that env vars copied with
    line-breaks (common in DO App Platform) never produce invalid HTTP headers.
    """
    val = getattr(settings, name, default) or default
    return val.strip() if isinstance(val, str) else val


def get_valid_token() -> str:
    """Return a valid Bearer token, refreshing automatically if needed.

    Priority:
    1. Cache hit and not near-expired → return cached value
    2. Cache miss / near-expired → refresh via refresh_token → store in cache
    3. If refresh fails → return the env-var bootstrap token as last resort
    """
    cached = cache.get(CACHE_KEY_TOKEN)
    expiry = cache.get(CACHE_KEY_EXPIRY, 0)

    if cached and expiry and time.time() < (expiry - REFRESH_BUFFER_SECONDS):
        return cached

    # Attempt token refresh
    client_id = _cfg("CLEVERREACH_CLIENT_ID")
    client_secret = _cfg("CLEVERREACH_CLIENT_SECRET")
    refresh_token = _cfg("CLEVERREACH_REFRESH_TOKEN")

    if not (client_id and client_secret and refresh_token):
        logger.warning("CleverReach credentials incomplete — using bootstrap token")
        return _cfg("CLEVERREACH_ACCESS_TOKEN")

    try:
        resp = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        new_token = data["access_token"]
        expires_in = int(data.get("expires_in", 2592000))
        expire_ts = time.time() + expires_in

        # Cache for expires_in seconds (minus small buffer)
        cache.set(CACHE_KEY_TOKEN, new_token, timeout=expires_in - REFRESH_BUFFER_SECONDS)
        cache.set(CACHE_KEY_EXPIRY, expire_ts, timeout=expires_in)

        # If a new refresh_token was returned, log a reminder to update the env var
        if "refresh_token" in data and data["refresh_token"] != refresh_token:
            logger.warning(
                "CleverReach returned a NEW refresh token — update "
                "CLEVERREACH_REFRESH_TOKEN on DigitalOcean (App Platform → Settings → Env Vars):\n%s",
                data["refresh_token"],
            )

        logger.info("CleverReach token refreshed; expires in %ds", expires_in)
        return new_token

    except Exception as exc:
        logger.error("CleverReach token refresh failed: %s", exc)
        # Fall back to whatever bootstrap token is configured
        fallback = _cfg("CLEVERREACH_ACCESS_TOKEN")
        if fallback:
            return fallback
        raise RuntimeError("No valid CleverReach access token available") from exc


def _auth_headers() -> dict:
    return {
        "Authorization": f"Bearer {get_valid_token()}",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _api_get(path: str, **kwargs) -> dict:
    r = requests.get(f"{API_V3}/{path}", headers=_auth_headers(), timeout=15, **kwargs)
    r.raise_for_status()
    return r.json()


def _api_post(path: str, payload: dict, **kwargs) -> dict:
    r = requests.post(f"{API_V3}/{path}", json=payload, headers=_auth_headers(), timeout=30, **kwargs)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Transactional email sending
# ---------------------------------------------------------------------------

def send_cleverreach_email(
    to_email: str,
    to_name: str,
    subject: str,
    html: str,
    text: str,
) -> bool:
    """Create a CleverReach mailing and deliver it immediately to *to_email*.

    Returns True on success, False on any error (so callers can fall back to SMTP).

    Flow
    ----
    1. POST /v3/mailings.json                → create mailing
    2. POST /v3/mailings/{id}/sendpreview    → send to explicit email address
    """
    sender_email = _cfg("CLEVERREACH_SENDER_EMAIL", "noreply@iesasport.ch")
    sender_name = _cfg("CLEVERREACH_SENDER_NAME", "IESA Sport")

    import datetime
    ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    mailing_name = f"tx_{ts}_{to_email[:20]}"

    try:
        # Step 1: Create mailing
        mailing = _api_post("mailings.json", {
            "name": mailing_name,
            "sender_name": sender_name,
            "sender_email": sender_email,
            "subject": subject,
            "html": html,
            "text": text,
            "type": "trigger",  # single-send / transactional type
        })
        mailing_id = mailing.get("id")
        if not mailing_id:
            logger.error("CleverReach mailing creation returned no id: %s", mailing)
            return False

        logger.debug("CleverReach mailing created: id=%s name=%s", mailing_id, mailing_name)

        # Step 2: Send to direct recipient (v3 endpoint)
        send_result = _api_post(f"mailings/{mailing_id}/sendpreview.json", {
            "receivers": [to_email],
            "previewText": "",
        })
        logger.info(
            "CleverReach sent '%s' → %s (mailing=%s, result=%s)",
            subject, to_email, mailing_id, send_result,
        )
        return True

    except requests.HTTPError as exc:
        body = ""
        try:
            body = exc.response.text
        except Exception:
            pass
        logger.error(
            "CleverReach HTTP error sending to %s: %s — %s", to_email, exc, body
        )
        return False
    except Exception as exc:
        logger.error("CleverReach unexpected error sending to %s: %s", to_email, exc)
        return False


# ---------------------------------------------------------------------------
# Account info helper (for admin/management command)
# ---------------------------------------------------------------------------

def get_account_info() -> dict:
    """Fetch basic account info from CleverReach API."""
    return _api_get("debug/whoami.json")


def is_configured() -> bool:
    """Return True if the minimum CR settings are present in Django settings."""
    return bool(
        _cfg("CLEVERREACH_CLIENT_ID")
        and _cfg("CLEVERREACH_ACCESS_TOKEN")
    )
