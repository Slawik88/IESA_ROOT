"""Telegram Bot API HTTP client — async and sync variants."""
import asyncio
import logging
import time
from typing import Any

import httpx

from .config import api_url, token

logger = logging.getLogger(__name__)

_RETRY_STATUSES = {429, 500, 502, 503, 504}
_MAX_BACKOFF = 30  # Максимум ожидания между retry (B3-04)


# ── Shared async client pool (B3-09) ───────────────────────────────────────
# Переиспользуем один клиент вместо открытия нового соединения на каждый запрос.
# Клиент создаётся лениво и заменяется если закрыт (shutdown/restart).
_shared_async_client: httpx.AsyncClient | None = None


def _get_async_client() -> httpx.AsyncClient:
    global _shared_async_client
    if _shared_async_client is None or _shared_async_client.is_closed:
        _shared_async_client = httpx.AsyncClient(
            timeout=10,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
    return _shared_async_client


def _safe_json(resp: httpx.Response, context: str = "") -> dict | None:
    """resp.json() с защитой от JSONDecodeError (B3-07)."""
    try:
        return resp.json()
    except Exception as exc:
        logger.error("Telegram JSON decode error%s (status=%d): %s",
                     f" in {context}" if context else "", resp.status_code, exc)
        return None


async def _post_with_retry(method: str, payload: dict, retries: int = 3) -> dict | None:
    """POST к Telegram API с exponential backoff на transient-ошибки."""
    client = _get_async_client()
    for attempt in range(retries):
        try:
            resp = await client.post(api_url(method), json=payload)
            if resp.status_code == 429:
                # Ограничиваем retry_after максимумом (B3-04)
                retry_after = min(int(resp.headers.get("Retry-After", 5)), _MAX_BACKOFF)
                logger.warning("Telegram rate-limited; retry after %ds (attempt %d)", retry_after, attempt + 1)
                if attempt < retries - 1:
                    await asyncio.sleep(retry_after)
                    continue
                return None
            if resp.status_code in _RETRY_STATUSES:
                if attempt < retries - 1:
                    await asyncio.sleep(min(2 ** attempt, _MAX_BACKOFF))
                    continue
                logger.error("Telegram %s: server error %s after %d retries", method, resp.status_code, retries)
                return None
            return _safe_json(resp, method)  # B3-07
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            if attempt < retries - 1:
                await asyncio.sleep(min(2 ** attempt, _MAX_BACKOFF))
                continue
            logger.error("Telegram %s network error after %d retries: %s", method, retries, exc)
            return None
    return None


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

    data = await _post_with_retry("sendMessage", payload)
    if data and data.get("ok"):
        return True
    if data:
        logger.error("Telegram sendMessage error: %s", data)
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
    data = await _post_with_retry("editMessageText", payload)
    if data:
        return bool(data.get("ok"))
    logger.error("Telegram editMessageText failed after retries")
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
    data = await _post_with_retry("editMessageReplyMarkup", payload)
    if data:
        return bool(data.get("ok"))
    logger.error("Telegram editMessageReplyMarkup failed after retries")
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
        client = _get_async_client()
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
        client = _get_async_client()
        resp = await client.post(api_url("setMyCommands"), json={"commands": commands})
        data = _safe_json(resp, "setMyCommands")  # B3-07
        if data is None:
            return False
        ok = bool(resp.is_success and data.get("ok"))
        if ok:
            logger.info("Telegram: setMyCommands OK (%d commands)", len(commands))
        else:
            logger.error("Telegram setMyCommands error: %s", data)
        return ok
    except Exception as exc:
        logger.error("Telegram setMyCommands failed: %s", exc)
        return False


# ── Sync send with retry (B3-05 / B3-10) ──────────────────────────────────

def send_message(
    text: str,
    chat_id: int | str,
    parse_mode: str = "HTML",
    reply_markup: dict | None = None,
) -> bool:
    """Send a Telegram message synchronously with retry. Returns True on success."""
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

    for attempt in range(3):
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(api_url("sendMessage"), json=payload)

            if resp.status_code == 429:
                retry_after = min(int(resp.headers.get("Retry-After", 5)), _MAX_BACKOFF)
                logger.warning("Telegram sync rate-limited; retry after %ds", retry_after)
                if attempt < 2:
                    time.sleep(retry_after)
                    continue
                return False

            if resp.status_code in _RETRY_STATUSES:
                if attempt < 2:
                    time.sleep(min(2 ** attempt, _MAX_BACKOFF))
                    continue
                logger.error("Telegram sync sendMessage: server error %s", resp.status_code)
                return False

            data = _safe_json(resp, "sendMessage sync")  # B3-07
            if data and data.get("ok"):
                return True
            if data:
                logger.error("Telegram sendMessage sync error: %s", data)
            return False

        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            if attempt < 2:
                time.sleep(min(2 ** attempt, _MAX_BACKOFF))
                continue
            logger.error("Telegram sync send failed after retries: %s", exc)
            return False
        except Exception as exc:
            logger.error("Telegram sync send unexpected error: %s", exc)
            return False

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
        data = _safe_json(resp, "setWebhook")
        if data and resp.is_success and data.get("ok"):
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
        return _safe_json(resp, "getWebhookInfo") or {"ok": False, "description": "invalid JSON"}
    except Exception as exc:
        return {"ok": False, "description": str(exc)}
