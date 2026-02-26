"""Telegram Notification Service for IESA Sport.

Primary mode: webhook + reply to the user who wrote to the bot.
No TELEGRAM_CHAT_ID is required for this test flow.

Required env vars (DigitalOcean App Platform):
    TELEGRAM_BOT_TOKEN      - token from @BotFather
    TELEGRAM_WEBHOOK_SECRET - random secret path segment for webhook URL
"""
import logging
import os
from html import escape
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Config helpers
# ------------------------------------------------------------------

def _token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def _webhook_secret() -> str:
    return os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()


def is_configured() -> bool:
    """Return True when TELEGRAM_BOT_TOKEN is present."""
    return bool(_token())


# ------------------------------------------------------------------
# Low-level sender
# ------------------------------------------------------------------

def send_message(text: str, chat_id: str, parse_mode: str = "HTML") -> bool:
    """Send a Telegram message to provided chat_id. Returns True on success."""
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
            return True, "Webhook успешно установлен"
        return False, str(data)
    except Exception as exc:
        return False, str(exc)


def get_webhook_info() -> dict[str, Any]:
    """Read current webhook info from Telegram API."""
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


def process_incoming_update(update: dict[str, Any]) -> bool:
    """Process incoming update and reply to sender chat."""
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id") or "").strip()
    text = (message.get("text") or "").strip()

    if not chat_id:
        logger.info("Telegram update without chat_id ignored")
        return False

    if text.startswith("/start"):
        reply = (
            "🤖 <b>IESA Sport Bot</b>\n\n"
            "Бот активен и готов к работе.\n"
            "Напишите любой текст — я отвечу.\n"
            "Команда <code>/id</code> покажет ваш chat_id."
        )
    elif text.startswith("/id"):
        reply = f"Ваш chat_id: <code>{chat_id}</code>"
    elif text:
        reply = (
            "✅ Бот работает.\n"
            f"Вы написали: <code>{escape(text)}</code>"
        )
    else:
        reply = "✅ Бот на связи."

    return send_message(reply, chat_id=chat_id)


# ------------------------------------------------------------------
# Visit notifications  (replaces email_service functions)
# ------------------------------------------------------------------

def notify_visit_confirmed(visit) -> bool:
    """Notify when a visit is logged (replaces send_visit_confirmed)."""
    member  = visit.member
    partner = visit.partner
    ts      = visit.timestamp.strftime("%d.%m.%Y %H:%M")
    cost    = f"{visit.cost} CHF" if visit.cost else "—"
    service = visit.get_service_type_display()
    name    = member.get_full_name() or member.username

    text = (
        "✅ <b>Визит подтверждён</b>\n\n"
        f"👤 Участник: <b>{name}</b>\n"
        f"🏢 Партнёр: <b>{partner.company_name}</b>\n"
        f"🏃 Услуга: {service}\n"
        f"💰 Стоимость: {cost}\n"
        f"🕐 Время: {ts}"
    )
    if visit.service_description:
        text += f"\n📝 Описание: {visit.service_description}"

    logger.info("Telegram visit_confirmed event prepared (requires per-user chat mapping)")
    return False


def notify_visit_edited(visit, audit) -> bool:
    """Notify when a visit record is edited (replaces send_visit_edited)."""
    member  = visit.member
    partner = visit.partner
    ts      = visit.timestamp.strftime("%d.%m.%Y %H:%M")
    name    = member.get_full_name() or member.username
    old_cost = f"{audit.previous_cost} CHF" if audit.previous_cost else "—"
    new_cost = f"{visit.cost} CHF" if visit.cost else "—"

    text = (
        "📝 <b>Визит изменён</b>\n\n"
        f"👤 Участник: <b>{name}</b>\n"
        f"🏢 Партнёр: <b>{partner.company_name}</b>\n"
        f"🕐 Визит от: {ts}\n\n"
        f"<s>Услуга: {audit.previous_service_type} / {old_cost}</s>\n"
        f"✏️ Новое: {visit.get_service_type_display()} / {new_cost}\n"
        f"📋 Причина: {audit.reason}"
    )
    logger.info("Telegram visit_edited event prepared (requires per-user chat mapping)")
    return False


def notify_visit_cancelled(visit, audit) -> bool:
    """Notify when a visit is cancelled (replaces send_visit_cancelled)."""
    member  = visit.member
    partner = visit.partner
    ts      = visit.timestamp.strftime("%d.%m.%Y %H:%M")
    name    = member.get_full_name() or member.username
    old_cost = f"{audit.previous_cost} CHF" if audit.previous_cost else "—"

    text = (
        "❌ <b>Визит отменён</b>\n\n"
        f"👤 Участник: <b>{name}</b>\n"
        f"🏢 Партнёр: <b>{partner.company_name}</b>\n"
        f"🕐 Визит от: {ts}\n"
        f"🏃 Услуга: {audit.previous_service_type} / {old_cost}\n"
        f"📋 Причина: {audit.reason}"
    )
    logger.info("Telegram visit_cancelled event prepared (requires per-user chat mapping)")
    return False


# ------------------------------------------------------------------
# Test notification
# ------------------------------------------------------------------

def send_test_notification(custom_text: str = "") -> bool:
    """Kept for compatibility; test now goes through webhook replies."""
    return bool(custom_text)
