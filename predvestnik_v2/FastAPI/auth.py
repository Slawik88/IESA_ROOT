"""FastAPI/auth.py — two Telegram auth flows.

1. WebApp initData  (opened inside Telegram via bot button)
   Header: x-init-data = Telegram.WebApp.initData

2. Login Widget     (opened in a regular browser)
   The widget calls /auth/telegram-login; we verify and issue a session token.
   Header: x-session-token = <opaque token stored in localStorage>
"""
import hashlib
import hmac
import json
import os
import time
from urllib.parse import unquote

_SESSION_TTL = 7 * 24 * 3600  # session valid 7 days


def _bot_token() -> str:
    return os.getenv("BOT_TOKEN", "")


# ── WebApp initData ────────────────────────────────────────────────────────────

def verify_webapp_data(init_data: str) -> dict | None:
    """Verify Telegram WebApp initData (HMAC-SHA256, key = 'WebAppData').
    Returns parsed user dict or None."""
    token = _bot_token()
    if not init_data or not token:
        return None
    try:
        params: dict[str, str] = {}
        for part in init_data.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                params[k] = unquote(v)

        check_hash = params.pop("hash", "")
        if not check_hash:
            return None

        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
        secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(computed, check_hash):
            return None

        # M14: отвергаем устаревший initData (replay-защита) — как у Login Widget.
        try:
            if time.time() - int(params.get("auth_date", 0)) > 86400:
                return None
        except (ValueError, TypeError):
            return None

        user_str = params.get("user", "")
        return json.loads(user_str) if user_str else None
    except Exception:
        return None


# ── Login Widget ───────────────────────────────────────────────────────────────

def verify_login_widget(data: dict) -> dict | None:
    """Verify Telegram Login Widget callback data (SHA256 of bot token as key).
    Returns the user dict (id, first_name, username, …) or None."""
    token = _bot_token()
    if not token or "hash" not in data:
        return None
    try:
        check_hash = data["hash"]
        # Only include fields that were actually sent (non-None, non-hash).
        # Empty/missing optional fields must be absent from the check string.
        check_fields = {
            k: v for k, v in data.items()
            if k != "hash" and v is not None and v != ""
        }
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(check_fields.items()))
        secret_key = hashlib.sha256(token.encode()).digest()
        computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(computed, check_hash):
            return None
        # Reject stale data (older than 24 h)
        if time.time() - int(data.get("auth_date", 0)) > 86400:
            return None
        return check_fields
    except Exception:
        return None


# ── Session token (stateless, HMAC-signed) ────────────────────────────────────

def _session_secret() -> bytes:
    return hashlib.sha256((_bot_token() + "session").encode()).digest()


def create_session_token(user_id: int) -> str:
    """Create a signed session token: '{user_id}:{expires}:{hmac}'."""
    expires = int(time.time()) + _SESSION_TTL
    payload = f"{user_id}:{expires}"
    sig = hmac.new(_session_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def verify_session_token(token: str) -> int | None:
    """Verify session token. Returns user_id or None if invalid/expired."""
    try:
        parts = token.split(":")
        if len(parts) != 3:
            return None
        user_id_str, expires_str, sig = parts
        payload = f"{user_id_str}:{expires_str}"
        expected = hmac.new(_session_secret(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        if time.time() > int(expires_str):
            return None
        return int(user_id_str)
    except Exception:
        return None


# ── Signal hashing (твинк-детект в дев-консоли, deps.py) ───────────────────────
# Сырые IP/отпечатки устройств никогда не попадают в БД — только солёный HMAC.
# Кто угодно с доступом к БД видит "этот хэш встречался у X и Y", не сам IP.

def hash_signal(raw: str) -> str:
    if not raw:
        return ""
    secret = hashlib.sha256((_bot_token() + "signal").encode()).digest()
    return hmac.new(secret, raw.encode(), hashlib.sha256).hexdigest()
