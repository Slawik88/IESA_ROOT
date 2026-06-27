# bot/middlewares/tos_mw.py
# БЛОК22 (compliance): легаси-гард принятия ToS/Privacy.
# При любом осмысленном действии не принявшего игрока — просим принять документы
# с ПРЯМЫМИ ссылками. Принявшие проходят за один SELECT. Девелопер — иммунитет.

import os
from typing import Callable, Awaitable, Dict, Any
from aiogram.types import (TelegramObject, InlineKeyboardMarkup,
                           InlineKeyboardButton)

from infrastructure.repositories.users import is_tos_accepted, get_global_rank
from services.roles import DEVELOPER_GLOBAL_RANK


def _legal_urls() -> tuple[str | None, str | None]:
    """Прямые публичные ссылки на документы (из MINIAPP_URL). None — если не https."""
    base = os.getenv("MINIAPP_URL", "").rstrip("/")
    if not base.startswith("https://"):
        return None, None
    return f"{base}/legal/tos", f"{base}/legal/privacy"


def build_consent_kb() -> InlineKeyboardMarkup:
    """Клавиатура онбординга: прямые ссылки на документы + кнопка «Принять»."""
    tos_url, priv_url = _legal_urls()
    rows: list[list[InlineKeyboardButton]] = []
    if tos_url and priv_url:
        rows.append([
            InlineKeyboardButton(text="📖 Правила (ToS)", url=tos_url),
            InlineKeyboardButton(text="🔒 Конфиденциальность", url=priv_url),
        ])
    rows.append([InlineKeyboardButton(text="✅ Принять и играть",
                                      callback_data="tos:accept")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def consent_text(is_new: bool) -> str:
    if is_new:
        head = ("👋 <b>Добро пожаловать в PREDVESTNIK!</b>\n\n"
                "Чтобы продолжить, необходимо принять наши документы.")
    else:
        head = ("📋 <b>В PREDVESTNIK обновились юридические документы.</b>\n\n"
                "Чтобы продолжить и сохранить прогресс, примите новые правила.")
    return head + "\n\nОзнакомьтесь по кнопкам ниже и нажмите «Принять»."


async def tos_middleware(
    handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
    event: TelegramObject,
    data: Dict[str, Any],
) -> Any:
    db = data.get("db")
    user = data.get("event_from_user")
    if not user or db is None:
        return await handler(event, data)

    # Принявшие (подавляющее большинство после раската) — один SELECT и пропуск.
    if await is_tos_accepted(db, user.id):
        return await handler(event, data)

    # Не принял → иммунитет разработчику (чтобы не залочиться).
    try:
        if await get_global_rank(db, user.id) >= DEVELOPER_GLOBAL_RANK:
            return await handler(event, data)
    except Exception:
        pass

    msg = getattr(event, "message", None)
    cq = getattr(event, "callback_query", None)

    # Гейтим только сообщения и колбэки; служебные апдейты (my_chat_member,
    # inline_query и пр.) пропускаем, чтобы не ломать подключение бота к чатам.
    if msg is None and cq is None:
        return await handler(event, data)

    # Сам accept-callback пропускаем — иначе кнопка «Принять» не сработает.
    if cq is not None and (cq.data or "").startswith("tos:"):
        return await handler(event, data)

    is_start = bool(msg and (msg.text or "").startswith("/start"))
    is_command = bool(msg and (msg.text or "").startswith("/"))
    chat = data.get("event_chat")
    is_private = bool(chat and getattr(chat, "type", "") == "private")

    # Промпт показываем на осмысленных взаимодействиях (или в личке), чтобы не
    # спамить группу на каждое обычное сообщение (XP-трекинг просто блокируется).
    if is_private or is_command or cq is not None:
        try:
            bot = data["bot"]
            target = chat.id if chat else user.id
            await bot.send_message(target, consent_text(is_new=is_start),
                                   reply_markup=build_consent_kb(),
                                   parse_mode="HTML")
            if cq is not None:
                await cq.answer("Сначала примите документы 📋")
        except Exception:
            pass
    return  # блокируем действие до принятия
