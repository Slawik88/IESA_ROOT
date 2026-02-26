"""
Telegram Notification Service — IESA Sport
===========================================
Replaces email notifications with Telegram Bot API messages.

How it works
------------
Bot sends messages to a Telegram chat (admin group, channel, or personal chat).
Uses only outbound HTTP — no webhook, no background process required.
Works perfectly on DigitalOcean App Platform.

Required environment variables (set in DO App Platform → Settings → Env Vars):
    TELEGRAM_BOT_TOKEN   — token from @BotFather (e.g. 7123456789:AAF...)
    TELEGRAM_CHAT_ID     — chat ID to receive notifications
                           (admin group / channel / personal chat)
                           Get it by messaging @userinfobot

Optional:
    TELEGRAM_ADMIN_CHAT_ID — separate chat for admin alerts (defaults to TELEGRAM_CHAT_ID)
"""
import logging
import os

import requests

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Config helpers
# ------------------------------------------------------------------

def _token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def _chat_id() -> str:
    return os.environ.get("TELEGRAM_CHAT_ID", "").strip()


def _admin_chat_id() -> str:
    return os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "").strip() or _chat_id()


def is_configured() -> bool:
    """Return True when both BOT_TOKEN and CHAT_ID are present."""
    return bool(_token() and _chat_id())


# ------------------------------------------------------------------
# Low-level sender
# ------------------------------------------------------------------

def send_message(text: str, chat_id: str = "", parse_mode: str = "HTML") -> bool:
    """
    Send a Telegram message.  Returns True on success.
    If chat_id is not provided, uses TELEGRAM_CHAT_ID env var.
    """
    token = _token()
    target = chat_id or _chat_id()

    if not token:
        logger.warning("Telegram: TELEGRAM_BOT_TOKEN not set — notification skipped")
        return False
    if not target:
        logger.warning("Telegram: TELEGRAM_CHAT_ID not set — notification skipped")
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

    return send_message(text)


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
    return send_message(text)


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
    return send_message(text)


# ------------------------------------------------------------------
# Test notification
# ------------------------------------------------------------------

def send_test_notification(custom_text: str = "") -> bool:
    """Send a test message to verify the bot is working."""
    text = custom_text or (
        "🤖 <b>IESA Sport — Тест бота</b>\n\n"
        "✅ Telegram-уведомления работают корректно!\n\n"
        "Этот бот будет отправлять уведомления о визитах участников."
    )
    return send_message(text)
