"""Независимый адрес входа. Файл можно загрузить без импорта модулей бота."""
import hashlib
import hmac
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values


def entry_token() -> str:
    return (os.getenv("DOMOVOY_BOT_TOKEN") or
            dotenv_values(Path(__file__).resolve().parents[1] / ".env").get("DOMOVOY_BOT_TOKEN") or "").strip()


def private_path(token: str) -> str:
    if not token:
        return ""
    digest = hmac.new(token.encode(), b"house-private-entry-v1", hashlib.sha256).hexdigest()[:32]
    return f"/_h/{digest}"


def public_url() -> str | None:
    token = entry_token()
    if not token:
        return None
    base = (os.getenv("DOMOVOY_WEB_BASE_URL") or os.getenv("MINIAPP_URL") or
            "https://iesasport.ch/predvestnik").rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        return None
    return base + private_path(token) + "/"
