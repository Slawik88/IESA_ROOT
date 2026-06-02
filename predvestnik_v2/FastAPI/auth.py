"""FastAPI/auth.py — Telegram WebApp initData verification.
Docs: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""
import hashlib
import hmac
import json
import os
from urllib.parse import unquote


def verify_webapp_data(init_data: str) -> dict | None:
    """Verify Telegram WebApp initData using HMAC-SHA256.
    Returns parsed user dict or None if signature is invalid or data is missing."""
    bot_token = os.getenv("BOT_TOKEN", "")
    if not init_data or not bot_token:
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

        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(params.items())
        )

        secret_key = hmac.new(
            b"WebAppData", bot_token.encode(), hashlib.sha256
        ).digest()
        computed = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(computed, check_hash):
            return None

        user_str = params.get("user", "")
        if not user_str:
            return None
        return json.loads(user_str)
    except Exception:
        return None
