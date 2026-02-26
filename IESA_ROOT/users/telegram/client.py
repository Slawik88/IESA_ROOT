"""Telegram Bot API HTTP client — async and sync variants."""
import logging
from typing import Any

import httpx

from .config import api_url, token

logger = logging.getLogger(__name__)


# ── Async ──────────────────────────────────────────────────────────────────

async def send_message_async(
    text: str,
    chat_id: int | str,
    parse_mode: str = "HTML",
    reply_markup: dict | None = None,
) -> bool:
    """Send a Telegram message asynchronously. Returns True on success."""
    t = token()
    cid = str(chat_id).strip()
    if not t:
        logger.warning("Telegram: TELEGRAM_BOT_TOKEN not set — skipped")
        return False
    if not cid:
        logger.warning("Telegram: chat_id empty — skipped")
        return False

    payload: dict[str, Any] = {
        "chat_id": cid,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(api_url("sendMessage"), json=payload)
        data = resp.json()
        if resp.is_success and data.get("ok"):
            logger.info("Telegram async: sent to chat %s", cid)
            return True
        logger.error("Telegram API error async: %s", data)
        return False
    except Exception as exc:
        logger.error("Telegram async send failed: %s", exc)
        return False


# ── Sync ───────────────────────────────────────────────────────────────────

def send_message(
    text: str,
    chat_id: int | str,
    parse_mode: str = "HTML",
    reply_markup: dict | None = None,
) -> bool:
    """Send a Telegram message synchronously. Returns True on success."""
    t = token()
    cid = str(chat_id).strip()
    if not t:
        logger.warning("Telegram: TELEGRAM_BOT_TOKEN not set — skipped")
        return False
    if not cid:
        logger.warning("Telegram: chat_id empty — skipped")
        return False

    payload: dict[str, Any] = {
        "chat_id": cid,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(api_url("sendMessage"), json=payload)
        data = resp.json()
        if resp.is_success and data.get("ok"):
            logger.info("Telegram sync: sent to chat %s", cid)
            return True
        logger.error("Telegram API error sync: %s", data)
        return False
    except Exception as exc:
        logger.error("Telegram sync send failed: %s", exc)
        return False


# ── Webhook management ─────────────────────────────────────────────────────

def set_webhook(webhook_url: str) -> tuple[bool, str]:
    t = token()
    if not t:
        return False, "TELEGRAM_BOT_TOKEN не задан"
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                api_url("setWebhook"),
                json={"url": webhook_url, "allowed_updates": ["message", "callback_query"]},
            )
        data = resp.json()
        if resp.is_success and data.get("ok"):
            return True, data.get("description", "Webhook установлен")
        return False, str(data)
    except Exception as exc:
        return False, str(exc)


def get_webhook_info() -> dict[str, Any]:
    t = token()
    if not t:
        return {"ok": False, "description": "TELEGRAM_BOT_TOKEN не задан"}
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(api_url("getWebhookInfo"))
        return resp.json()
    except Exception as exc:
        return {"ok": False, "description": str(exc)}
