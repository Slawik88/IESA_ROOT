"""Telegram Notification Service for IESA Sport.

Two ways to link a user's Telegram account:

Method A — link code via /link command
  1. User opens the bot and sends /link
  2. Bot replies with a 6-digit code (valid 10 minutes)
  3. User enters the code in their cabinet on the website
  4. Site saves telegram_chat_id to the User record

Method B — Telegram Login Widget
  1. Widget button on the website
  2. Telegram redirects to /auth/telegram/login-callback/ with signed data
  3. Site verifies HMAC hash and saves telegram_chat_id

Required env vars (DigitalOcean App Platform):
    TELEGRAM_BOT_TOKEN      - token from @BotFather
    TELEGRAM_WEBHOOK_SECRET - (optional) random path segment for webhook URL.
                              Auto-derived from token hash if not set.
    TELEGRAM_BOT_NAME       - bot @username without @ (for Login Widget)
"""
import hashlib
import hmac
import logging
import os
import random
import string
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Cache key prefix for link codes
LINK_CODE_PREFIX = "tg_link_code:"
LINK_CODE_TTL    = 600  # 10 minutes

# Telegram Bot API base
_TG_BASE = "https://api.telegram.org/bot{token}/{method}"


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def _token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def _webhook_secret() -> str:
    """Return webhook secret. Falls back to sha256(token)[:20] if env var not set."""
    explicit = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if explicit:
        return explicit
    token = _token()
    if not token:
        return ""
    return hashlib.sha256(token.encode()).hexdigest()[:20]


def is_configured() -> bool:
    return bool(_token())


def _api_url(method: str) -> str:
    return _TG_BASE.format(token=_token(), method=method)


# ---------------------------------------------------------------------------
# Async send  (used inside async Django views / webhook handler)
# ---------------------------------------------------------------------------

async def send_message_async(
    text: str,
    chat_id: int | str,
    parse_mode: str = "HTML",
) -> bool:
    """Async: send a Telegram message. Returns True on success."""
    token = _token()
    target = str(chat_id).strip()
    if not token:
        logger.warning("Telegram: TELEGRAM_BOT_TOKEN not set — skipped")
        return False
    if not target:
        logger.warning("Telegram: chat_id empty — skipped")
        return False

    payload = {
        "chat_id": target,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(_api_url("sendMessage"), json=payload)
        data = resp.json()
        if resp.is_success and data.get("ok"):
            logger.info("Telegram async: sent to chat %s", target)
            return True
        logger.error("Telegram API error: %s", data)
        return False
    except Exception as exc:
        logger.error("Telegram async send failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Sync send  (used from Django signals / management commands)
# ---------------------------------------------------------------------------

def send_message(
    text: str,
    chat_id: int | str,
    parse_mode: str = "HTML",
) -> bool:
    """Sync: send a Telegram message. Returns True on success."""
    token = _token()
    target = str(chat_id).strip()
    if not token:
        logger.warning("Telegram: TELEGRAM_BOT_TOKEN not set — skipped")
        return False
    if not target:
        logger.warning("Telegram: chat_id empty — skipped")
        return False

    payload = {
        "chat_id": target,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(_api_url("sendMessage"), json=payload)
        data = resp.json()
        if resp.is_success and data.get("ok"):
            logger.info("Telegram sync: sent to chat %s", target)
            return True
        logger.error("Telegram API error: %s", data)
        return False
    except Exception as exc:
        logger.error("Telegram sync send failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Webhook management  (sync — called from admin views)
# ---------------------------------------------------------------------------

def set_webhook(webhook_url: str) -> tuple[bool, str]:
    token = _token()
    if not token:
        return False, "TELEGRAM_BOT_TOKEN не задан"
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                _api_url("setWebhook"),
                json={"url": webhook_url, "allowed_updates": ["message"]},
            )
        data = resp.json()
        if resp.is_success and data.get("ok"):
            return True, data.get("description", "Webhook успешно установлен")
        return False, str(data)
    except Exception as exc:
        return False, str(exc)


def get_webhook_info() -> dict[str, Any]:
    token = _token()
    if not token:
        return {"ok": False, "description": "TELEGRAM_BOT_TOKEN не задан"}
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(_api_url("getWebhookInfo"))
        return resp.json()
    except Exception as exc:
        return {"ok": False, "description": str(exc)}


# ---------------------------------------------------------------------------
# Link code helpers  (Method A)
# ---------------------------------------------------------------------------

def generate_link_code(chat_id: int) -> str:
    """Generate a 6-digit one-time link code stored in Django cache."""
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


# ---------------------------------------------------------------------------
# Telegram Login Widget signature verification  (Method B)
# ---------------------------------------------------------------------------

def verify_telegram_auth(data: dict[str, str]) -> bool:
    """Verify HMAC signature from Telegram Login Widget."""
    token = _token()
    if not token:
        return False
    received_hash = data.get("hash", "")
    check_data = {k: v for k, v in data.items() if k != "hash"}
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(check_data.items()))
    secret_key = hashlib.sha256(token.encode()).digest()
    computed = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, received_hash)


# ---------------------------------------------------------------------------
# Async update processor  (webhook handler)
# ---------------------------------------------------------------------------

async def process_incoming_update(update: dict[str, Any]) -> bool:
    """
    Process one incoming Telegram update asynchronously.

    Commands:
        /start  — welcome message
        /link   — generate 6-digit link code and reply with it
        /id     — show chat_id
        /unlink — unlink user account

    Everything else → echo the message back (for development / demo).
    """
    from asgiref.sync import sync_to_async

    message = update.get("message") or update.get("edited_message") or {}
    chat    = message.get("chat") or {}
    chat_id = chat.get("id")
    text    = (message.get("text") or "").strip()

    if not chat_id:
        return False

    if text.startswith("/start"):
        reply = (
            "👋 <b>Привет! Это IESA Sport бот.</b>\n\n"
            "Команды:\n"
            "• /link — привязать Telegram к аккаунту на сайте\n"
            "• /id — показать свой chat_id\n"
            "• /unlink — отвязать аккаунт\n\n"
            "Напиши что угодно — я повторю 🙂"
        )

    elif text.startswith("/link"):
        code = generate_link_code(chat_id)
        reply = (
            f"🔗 <b>Код для привязки аккаунта:</b>\n\n"
            f"<code>{code}</code>\n\n"
            f"Введи этот код в своём <b>кабинете на сайте</b> → "
            f"раздел «Telegram».\n\n"
            f"⏳ Действителен <b>10 минут</b>."
        )

    elif text.startswith("/id"):
        reply = f"Твой Telegram chat_id: <code>{chat_id}</code>"

    elif text.startswith("/unlink"):
        from .models import User
        count = await sync_to_async(
            lambda: User.objects.filter(telegram_chat_id=chat_id).update(
                telegram_chat_id=None, telegram_linked_at=None
            )
        )()
        reply = "✅ Аккаунт отвязан." if count else "ℹ️ Этот Telegram не привязан ни к одному аккаунту."

    elif text:
        # Echo mode — reflects everything back (useful for testing the bot is alive)
        reply = f"🔁 {text}"

    else:
        return False

    return await send_message_async(reply, chat_id=chat_id)


# ---------------------------------------------------------------------------
# Visit notifications  (sync — called from views/signals after visit confirmed)
# ---------------------------------------------------------------------------

def notify_visit_confirmed(visit) -> bool:
    chat_id = getattr(visit.member, "telegram_chat_id", None)
    if not chat_id:
        return False
    member  = visit.member
    partner = visit.partner
    ts      = visit.timestamp.strftime("%d.%m.%Y %H:%M")
    cost    = f"{visit.cost} CHF" if visit.cost else "—"
    service = visit.get_service_type_display()
    name    = member.get_full_name() or member.username
    text = (
        "✅ <b>Визит подтверждён</b>\n\n"
        f"👤 {name}\n🏢 {partner.company_name}\n"
        f"🏃 {service} / 💰 {cost}\n🕐 {ts}"
    )
    if visit.service_description:
        text += f"\n📝 {visit.service_description}"
    return send_message(text, chat_id=chat_id)


def notify_visit_edited(visit, audit) -> bool:
    chat_id = getattr(visit.member, "telegram_chat_id", None)
    if not chat_id:
        return False
    member   = visit.member
    partner  = visit.partner
    ts       = visit.timestamp.strftime("%d.%m.%Y %H:%M")
    old_cost = f"{audit.previous_cost} CHF" if audit.previous_cost else "—"
    new_cost = f"{visit.cost} CHF" if visit.cost else "—"
    text = (
        "📝 <b>Визит изменён</b>\n\n"
        f"👤 {member.get_full_name() or member.username}\n"
        f"🏢 {partner.company_name} / 🕐 {ts}\n"
        f"<s>{audit.previous_service_type} / {old_cost}</s>\n"
        f"✏️ {visit.get_service_type_display()} / {new_cost}\n"
        f"📋 {audit.reason}"
    )
    return send_message(text, chat_id=chat_id)


def notify_visit_cancelled(visit, audit) -> bool:
    chat_id = getattr(visit.member, "telegram_chat_id", None)
    if not chat_id:
        return False
    member   = visit.member
    partner  = visit.partner
    ts       = visit.timestamp.strftime("%d.%m.%Y %H:%M")
    old_cost = f"{audit.previous_cost} CHF" if audit.previous_cost else "—"
    text = (
        "❌ <b>Визит отменён</b>\n\n"
        f"👤 {member.get_full_name() or member.username}\n"
        f"🏢 {partner.company_name} / 🕐 {ts}\n"
        f"🏃 {audit.previous_service_type} / {old_cost}\n"
        f"📋 {audit.reason}"
    )
    return send_message(text, chat_id=chat_id)


def send_test_notification(custom_text: str = "") -> bool:
    return bool(custom_text)
