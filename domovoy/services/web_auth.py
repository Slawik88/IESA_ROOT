"""Проверка Telegram Mini App именно от домашнего бота, без игровых сессий."""
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from services.households import DomainError

MAX_AUTH_AGE_SECONDS = 3600
MAX_AUTH_BYTES = 8192


def verify_init_data(raw: str, bot_token: str, *, now: int | None = None) -> int:
    if not bot_token or not raw or len(raw) > MAX_AUTH_BYTES:
        raise DomainError("Откройте приложение заново из лички у бота")
    try:
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True, max_num_fields=30)
        data = dict(pairs)
        if len(data) != len(pairs):
            raise ValueError("duplicate field")
        received = data.pop("hash")
        check = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
        secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(received, expected):
            raise ValueError("signature")
        age = (int(time.time()) if now is None else now) - int(data["auth_date"])
        if age < -30 or age > MAX_AUTH_AGE_SECONDS:
            raise ValueError("expired")
        user = json.loads(data["user"])
        actor = user["id"]
        if type(actor) is not int or actor <= 0 or actor > 2**52 or user.get("is_bot"):
            raise ValueError("user")
        return actor
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise DomainError("Откройте приложение заново из лички у бота") from exc
