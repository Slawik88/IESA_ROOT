"""Telegram Bot API HTTP client — async and sync variants."""
import logging
from typing import Any

import httpx

from .config import api_url, token

logger = logging.getLogger(__name__)


# ── Async send ─────────────────────────────────────────────────────────────

async def send_message_async(
    text: str,
    chat_id: int | str,
    parse_mode: str = "HTML",
    reply_markup: dict | None = None,
    disable_notification: bool = False,
) -> bool:
    """Send a Telegram message asynchronously. Returns True on success."""
    t = token()
    cid = str(chat_id).strip()
    if not t or not cid:
        logger.warning("Telegram async: token or chat_id missing")
        return False

    payload: dict[str, Any] = {
        "chat_id": cid,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if disable_notification:
        payload["disable_notification"] = True

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(api_url("sendMessage"), json=payload)
        data = resp.json()
        if resp.is_success and data.get("ok"):
            return True
        logger.error("Telegram sendMessage error: %s", data)
        return False
    except Exception as exc:
        logger.error("Telegram async send failed: %s", exc)
        return False


# ── Edit message in-place ──────────────────────────────────────────────────

async def edit_message_text(
    chat_id: int | str,
    message_id: int,
    text: str,
    parse_mode: str = "HTML",
    reply_markup: dict | None = None,
) -> bool:
    """Edit an existing message text. Returns True on success."""
    t = token()
    if not t:
        return False
    payload: dict[str, Any] = {
        "chat_id": str(chat_id),
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(api_url("editMessageText"), json=payload)
        data = resp.json()
        return bool(resp.is_success and data.get("ok"))
    except Exception as exc:
        logger.error("Telegram editMessageText failed: %s", exc)
        return False


async def edit_message_reply_markup(
    chat_id: int | str,
    message_id: int,
    reply_markup: dict | None = None,
) -> bool:
    """Edit only the inline keyboard of an existing message."""
    t = token()
    if not t:
        return False
    payload: dict[str, Any] = {
        "chat_id": str(chat_id),
        "message_id": message_id,
        "reply_markup": reply_markup or {},
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(api_url("editMessageReplyMarkup"), json=payload)
        data = resp.json()
        return bool(resp.is_success and data.get("ok"))
    except Exception as exc:
        logger.error("Telegram editMessageReplyMarkup failed: %s", exc)
        return False


# ── Answer callback query ──────────────────────────────────────────────────

async def answer_callback_query(
    callback_query_id: str,
    text: str = "",
    show_alert: bool = False,
) -> bool:
    """Acknowledge a button press (removes loading spinner). Always call this."""
    t = token()
    if not t:
        return False
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            resp = await client.post(
                api_url("answerCallbackQuery"),
                json={"callback_query_id": callback_query_id, "text": text, "show_alert": show_alert},
            )
        return bool(resp.is_success)
    except Exception as exc:
        logger.error("Telegram answerCallbackQuery failed: %s", exc)
        return False


# ── Set bot commands menu ──────────────────────────────────────────────────

async def set_bot_commands(commands: list[dict]) -> bool:
    """Register commands in Telegram so the / button shows a menu."""
    t = token()
    if not t:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(api_url("setMyCommands"), json={"commands": commands})
        data = resp.json()
        ok = bool(resp.is_success and data.get("ok"))
        if ok:
            logger.info("Telegram: setMyCommands OK (%d commands)", len(commands))
        else:
            logger.error("Telegram setMyCommands error: %s", data)
        return ok
    except Exception as exc:
        logger.error("Telegram setMyCommands failed: %s", exc)
        return False


# ── Sync send (signals/management commands) ────────────────────────────────

def send_message(
    text: str,
    chat_id: int | str,
    parse_mode: str = "HTML",
    reply_markup: dict | None = None,
) -> bool:
    """Send a Telegram message synchronously. Returns True on success."""
    t = token()
    cid = str(chat_id).strip()
    if not t or not cid:
        logger.warning("Telegram sync: token or chat_id missing")
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
            return True
        logger.error("Telegram sendMessage sync error: %s", data)
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
                json={
                    "url": webhook_url,
                    "allowed_updates": ["message", "edited_message", "callback_query", "chat_member"],
                },
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


# ── Async ──────────────────────────────────────────────────────────────────

async def send_message_async(
    text: str,
    chat_id: int | str,
    parse_mode: str = "HTML",
    reply_markup: dict | None = None,
    disable_notification: bool = False,
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
    if disable_notification:
        payload["disable_notification"] = True

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
                json={
                    "url": webhook_url,
                    "allowed_updates": ["message", "callback_query", "chat_member"],
                },
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
