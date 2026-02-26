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
    TELEGRAM_WEBHOOK_SECRET - random secret path segment for webhook URL
"""
import hashlib
import hmac
import logging
import os
import random
import string
from html import escape
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Cache key prefix for link codes
LINK_CODE_PREFIX = "tg_link_code:"
LINK_CODE_TTL    = 600  # 10 minutes


# ------------------------------------------------------------------
# Config helpers
# ------------------------------------------------------------------

def _token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def _webhook_secret() -> str:
    return os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()


def is_configured() -> bool:
    return bool(_token())


# ------------------------------------------------------------------
# Low-level sender
# ------------------------------------------------------------------

def send_message(text: str, chat_id: str | int, parse_mode: str = "HTML") -> bool:
    """Send a Telegram message to chat_id. Returns True on success."""
    token = _token()
    target = str(chat_id).strip()

    if not token:
        logger.warning("Telegram: TELEGRAM_BOT_TOKEN not set — notification skipped")
        return False
    if not target:
        logger.warning("Telegram: chat_id is empty — notification skipped")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": target,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        data = resp.json()
        if resp.ok and data.get("ok"):
            logger.info("Telegram message sent to chat %s", target)
            return True
        else:
            logger.error("Telegram API error: %s", data)
            return False
    except Exception as exc:
        logger.error("Telegram send failed: %s", exc)
        return False


# ------------------------------------------------------------------
# Webhook management
# ------------------------------------------------------------------

def set_webhook(webhook_url: str) -> tuple[bool, str]:
    """Set Telegram webhook URL."""
    token = _token()
    if not token:
        return False, "TELEGRAM_BOT_TOKEN не задан"
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={"url": webhook_url},
            timeout=10,
        )
        data = resp.json()
        if resp.ok and data.get("ok"):
            return True, data.get("description", "Webhook успешно установлен")
        return False, str(data)
    except Exception as exc:
        return False, str(exc)


def get_webhook_info() -> dict[str, Any]:
    token = _token()
    if not token:
        return {"ok": False, "description": "TELEGRAM_BOT_TOKEN не задан"}
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{token}/getWebhookInfo",
            timeout=10,
        )
        return resp.json()
    except Exception as exc:
        return {"ok": False, "description": str(exc)}


# ------------------------------------------------------------------
# Link code helpers (Method A)
# ------------------------------------------------------------------

def generate_link_code(chat_id: int) -> str:
    """Generate a 6-digit link code and store it in cache."""
    from django.core.cache import cache

    code = "".join(random.choices(string.digits, k=6))
    cache.set(f"{LINK_CODE_PREFIX}{code}", str(chat_id), timeout=LINK_CODE_TTL)
    return code


def consume_link_code(code: str) -> str | None:
    """Return chat_id string for a valid code and delete it. None if invalid/expired."""
    from django.core.cache import cache

    key = f"{LINK_CODE_PREFIX}{code.strip()}"
    chat_id = cache.get(key)
    if chat_id:
        cache.delete(key)
    return chat_id


# ------------------------------------------------------------------
# Telegram Login Widget signature verification (Method B)
# ------------------------------------------------------------------

def verify_telegram_auth(data: dict[str, str]) -> bool:
    """
    Verify data received from Telegram Login Widget.
    https://core.telegram.org/widgets/login#checking-authorization
    """
    token = _token()
    if not token:
        return False

    received_hash = data.get("hash", "")
    check_data = {k: v for k, v in data.items() if k != "hash"}
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(check_data.items()))

    secret_key = hashlib.sha256(token.encode()).digest()
    computed_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()

    return hmac.compare_digest(computed_hash, received_hash)


# ------------------------------------------------------------------
# Webhook update processor
# ------------------------------------------------------------------

def process_incoming_update(update: dict[str, Any]) -> bool:
    """Process incoming Telegram update, reply to sender."""
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
            "• /link — привязать этот Telegram к аккаунту на сайте\n"
            "• /id — показать твой chat_id\n"
            "• /unlink — отвязать аккаунт"
        )

    elif text.startswith("/link"):
        code = generate_link_code(chat_id)
        reply = (
            f"🔗 <b>Код для привязки аккаунта:</b>\n\n"
            f"<code>{code}</code>\n\n"
            f"Введи этот код в своём <b>кабинете на сайте</b> → "
            f"раздел «Telegram».\n\n"
            f"⏳ Код действителен <b>10 минут</b>."
        )

    elif text.startswith("/id"):
        reply = f"Твой chat_id: <code>{chat_id}</code>"

    elif text.startswith("/unlink"):
        from .models import User
        count = User.objects.filter(telegram_chat_id=chat_id).update(
            telegram_chat_id=None, telegram_linked_at=None
        )
        if count:
            reply = "✅ Аккаунт успешно отвязан."
        else:
            reply = "ℹ️ Этот Telegram не привязан ни к одному аккаунту."

    elif text:
        reply = (
            "🤖 Бот IESA Sport.\n"
            "Напишите /link чтобы привязать аккаунт."
        )
    else:
        return False

    return send_message(reply, chat_id=chat_id)


# ------------------------------------------------------------------
# Visit notifications (future: per-user after linking)
# ------------------------------------------------------------------

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
    member  = visit.member
    partner = visit.partner
    ts      = visit.timestamp.strftime("%d.%m.%Y %H:%M")
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
    member  = visit.member
    partner = visit.partner
    ts      = visit.timestamp.strftime("%d.%m.%Y %H:%M")
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

import logging
