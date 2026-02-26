"""Command handlers — each returns a reply string (or None to skip).

Every handler is async and receives: (chat_id, text, user_db)
where user_db is the linked Django User or None.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async

from .client import send_message_async
from .link import generate_link_code

if TYPE_CHECKING:
    from users.models import User  # noqa: F401

logger = logging.getLogger(__name__)


async def handle_start(chat_id: int, text: str, user_db) -> str:
    linked_hint = (
        "\n✅ Твой Telegram <b>уже привязан</b> к аккаунту на сайте."
        if user_db else
        "\n🔗 Используй /link чтобы привязать аккаунт."
    )
    return (
        "👋 <b>Привет! Это бот IESA Sport.</b>\n\n"
        "Команды:\n"
        "• /link — привязать Telegram к аккаунту на сайте\n"
        "• /status — показать статус аккаунта\n"
        "• /id — показать твой Telegram chat_id\n"
        "• /unlink — отвязать аккаунт\n"
        "• /help — подробная справка\n"
        + linked_hint
    )


async def handle_help(chat_id: int, text: str, user_db) -> str:
    return (
        "📖 <b>Справка IESA Sport Bot</b>\n\n"
        "<b>/link</b> — Получить 6-значный код для привязки Telegram к кабинету на сайте.\n\n"
        "<b>/status</b> — Показать статус твоего членства.\n\n"
        "<b>/id</b> — Показать твой Telegram chat_id (нужно для поддержки).\n\n"
        "<b>/unlink</b> — Отвязать этот Telegram от аккаунта на сайте.\n\n"
        "После привязки <b>ты будешь получать уведомления</b> о:\n"
        "✅ Подтверждении визита к партнёрам\n"
        "📝 Изменении визита\n"
        "❌ Отмене визита\n\n"
        "<a href='https://iesasport.ch/auth/cabinet/'>Личный кабинет →</a>"
    )


async def handle_link(chat_id: int, text: str, user_db) -> str:
    if user_db:
        return (
            "✅ Твой Telegram уже привязан к аккаунту.\n"
            "Используй /unlink чтобы отвязать."
        )
    code = await sync_to_async(generate_link_code)(chat_id)
    return (
        f"🔗 <b>Код для привязки аккаунта:</b>\n\n"
        f"<code>{code}</code>\n\n"
        f"Введи этот код в <b>Личном кабинете</b> на сайте "
        f"→ раздел «Telegram».\n\n"
        f"⏳ Действителен <b>10 минут</b>.\n"
        f"<a href='https://iesasport.ch/auth/cabinet/'>Открыть кабинет →</a>"
    )


async def handle_id(chat_id: int, text: str, user_db) -> str:
    account_line = ""
    if user_db:
        name = await sync_to_async(lambda: user_db.get_full_name() or user_db.username)()
        account_line = f"\n👤 Привязан к: <b>{name}</b>"
    return f"Твой Telegram chat_id:\n<code>{chat_id}</code>" + account_line


async def handle_status(chat_id: int, text: str, user_db) -> str:
    if not user_db:
        return (
            "❌ Telegram не привязан к аккаунту IESA Sport.\n\n"
            "Используй /link чтобы привязать."
        )
    name   = await sync_to_async(lambda: user_db.get_full_name() or user_db.username)()
    status = await sync_to_async(lambda: user_db.membership_status)()
    emoji  = "✅" if status == "active" else "⚠️"
    label  = "Активен" if status == "active" else "Неактивен"
    return (
        f"👤 <b>{name}</b>\n"
        f"{emoji} Статус членства: <b>{label}</b>\n\n"
        f"<a href='https://iesasport.ch/auth/cabinet/'>Личный кабинет →</a>"
    )


async def handle_unlink(chat_id: int, text: str, user_db) -> str:
    if not user_db:
        return "ℹ️ Этот Telegram не привязан ни к одному аккаунту."

    def _do_unlink():
        from users.models import User
        return User.objects.filter(telegram_chat_id=chat_id).update(
            telegram_chat_id=None,
            telegram_linked_at=None,
        )

    count = await sync_to_async(_do_unlink)()
    return "✅ Аккаунт успешно отвязан." if count else "ℹ️ Уже отвязан."


async def handle_echo(chat_id: int, text: str, user_db) -> str:
    return f"🔁 {text}"
