"""Command handlers.

Each handler returns a tuple: (text: str, reply_markup: dict | None).
reply_markup follows the Telegram InlineKeyboardMarkup schema.
"""
from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async

from .link import generate_link_code

logger = logging.getLogger(__name__)

# ── Keyboard builders ──────────────────────────────────────────────────────

def _kb(*rows: list[dict]) -> dict:
    """Build InlineKeyboardMarkup from rows of button dicts."""
    return {"inline_keyboard": list(rows)}


def _btn(text: str, callback_data: str) -> dict:
    return {"text": text, "callback_data": callback_data}


def _url_btn(text: str, url: str) -> dict:
    return {"text": text, "url": url}


CABINET_URL = "https://iesasport.ch/auth/cabinet/"

# ── Handlers ───────────────────────────────────────────────────────────────

Reply = tuple[str, dict | None]


async def handle_start(chat_id: int, text: str, user_db) -> Reply:
    if user_db:
        name = await sync_to_async(lambda: user_db.get_full_name() or user_db.username)()
        status = await sync_to_async(lambda: user_db.membership_status)()
        emoji = "✅" if status == "active" else "⚠️"
        msg = (
            f"👋 <b>С возвращением, {name}!</b>\n\n"
            f"{emoji} Членство: <b>{'Активно' if status == 'active' else 'Неактивно'}</b>\n\n"
            "Выбери действие:"
        )
        kb = _kb(
            [_btn("📊 Мой статус", "cb:status"), _btn("❓ Помощь", "cb:help")],
            [_url_btn("🏠 Личный кабинет", CABINET_URL)],
            [_btn("🔓 Отвязать Telegram", "cb:unlink_ask")],
        )
    else:
        msg = (
            "👋 <b>Привет! Это бот IESA Sport.</b>\n\n"
            "Здесь ты можешь привязать свой Telegram к аккаунту на сайте "
            "и получать мгновенные уведомления о визитах к партнёрам.\n\n"
            "Нажми кнопку ниже ↓"
        )
        kb = _kb(
            [_btn("🔗 Привязать аккаунт", "cb:link")],
            [_btn("❓ Помощь", "cb:help")],
        )
    return msg, kb


async def handle_help(chat_id: int, text: str, user_db) -> Reply:
    msg = (
        "📖 <b>IESA Sport Bot — справка</b>\n\n"
        "🔗 <b>Привязать аккаунт</b> — получи 6-значный код и введи его в кабинете на сайте.\n\n"
        "📊 <b>Мой статус</b> — проверь состояние членства.\n\n"
        "🏠 <b>Личный кабинет</b> — открыть сайт, получить PIN для партнёров.\n\n"
        "🔓 <b>Отвязать Telegram</b> — отключить уведомления.\n\n"
        "<b>Ты получаешь уведомления о:</b>\n"
        "✅ Подтверждении визита\n"
        "📝 Изменении визита\n"
        "❌ Отмене визита\n"
        "🎉 Активации членства"
    )
    kb = _kb(
        [_btn("🔗 Привязать аккаунт", "cb:link"), _btn("📊 Мой статус", "cb:status")],
        [_url_btn("🏠 Личный кабинет", CABINET_URL)],
    )
    return msg, kb


async def handle_link(chat_id: int, text: str, user_db) -> Reply:
    if user_db:
        name = await sync_to_async(lambda: user_db.get_full_name() or user_db.username)()
        msg = (
            f"✅ Твой Telegram уже привязан к аккаунту <b>{name}</b>.\n\n"
            "Если хочешь отвязать — нажми кнопку ниже."
        )
        kb = _kb(
            [_btn("🔓 Отвязать", "cb:unlink_ask"), _url_btn("🏠 Кабинет", CABINET_URL)],
        )
        return msg, kb

    code = await sync_to_async(generate_link_code)(chat_id)
    msg = (
        f"🔗 <b>Твой код привязки:</b>\n\n"
        f"<code>{code}</code>\n\n"
        f"1. Открой <b>Личный кабинет</b> на сайте\n"
        f"2. Раздел «Telegram» → введи этот код\n\n"
        f"⏳ Код действителен <b>10 минут</b>"
    )
    kb = _kb(
        [_url_btn("🏠 Открыть кабинет", CABINET_URL)],
        [_btn("🔄 Новый код", "cb:new_code")],
    )
    return msg, kb


async def handle_id(chat_id: int, text: str, user_db) -> Reply:
    account_line = ""
    if user_db:
        name = await sync_to_async(lambda: user_db.get_full_name() or user_db.username)()
        account_line = f"\n👤 Привязан к: <b>{name}</b>"
    msg = f"Твой Telegram chat_id:\n<code>{chat_id}</code>" + account_line
    return msg, None


async def handle_status(chat_id: int, text: str, user_db) -> Reply:
    if not user_db:
        msg = "❌ Telegram не привязан к аккаунту IESA Sport."
        kb = _kb([_btn("🔗 Привязать аккаунт", "cb:link")])
        return msg, kb

    name   = await sync_to_async(lambda: user_db.get_full_name() or user_db.username)()
    status = await sync_to_async(lambda: user_db.membership_status)()
    emoji  = "✅" if status == "active" else "⚠️"
    label  = "Активно" if status == "active" else "Неактивно"
    msg = (
        f"👤 <b>{name}</b>\n"
        f"{emoji} Статус членства: <b>{label}</b>"
    )
    kb = _kb(
        [_url_btn("🏠 Личный кабинет", CABINET_URL), _btn("🔄 Обновить", "cb:status")],
        [_btn("🔓 Отвязать Telegram", "cb:unlink_ask")],
    )
    return msg, kb


async def handle_unlink_ask(chat_id: int, text: str, user_db) -> Reply:
    """Show confirmation before unlinking."""
    if not user_db:
        return "ℹ️ Этот Telegram не привязан ни к одному аккаунту.", None
    msg = "⚠️ <b>Отвязать Telegram от аккаунта?</b>\n\nТы перестанешь получать уведомления."
    kb = _kb([_btn("✅ Да, отвязать", "cb:unlink_yes"), _btn("❌ Отмена", "cb:cancel")])
    return msg, kb


async def handle_unlink_yes(chat_id: int, text: str, user_db) -> Reply:
    if not user_db:
        return "ℹ️ Уже отвязан.", None

    def _do_unlink():
        from users.models import User
        return User.objects.filter(telegram_chat_id=chat_id).update(
            telegram_chat_id=None,
            telegram_linked_at=None,
        )

    count = await sync_to_async(_do_unlink)()
    msg = "✅ Telegram отвязан от аккаунта." if count else "ℹ️ Уже отвязан."
    kb = _kb([_btn("🔗 Привязать снова", "cb:link")])
    return msg, kb


async def handle_cancel(chat_id: int, text: str, user_db) -> Reply:
    return "↩️ Отменено.", None


async def handle_echo(chat_id: int, text: str, user_db) -> Reply:
    msg = (
        f"🔁 {text}\n\n"
        "<i>Я повторяю твои сообщения в режиме теста. "
        "Используй кнопки или команды ниже.</i>"
    )
    if user_db:
        kb = _kb(
            [_btn("📊 Мой статус", "cb:status"), _url_btn("🏠 Кабинет", CABINET_URL)],
        )
    else:
        kb = _kb([_btn("🔗 Привязать аккаунт", "cb:link"), _btn("❓ Помощь", "cb:help")])
    return msg, kb
