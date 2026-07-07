# bot/middlewares/global_sanctions_mw.py
# Глобальные баны/ограничения экосистемы бота (Implementation Block 6.4 + БЛОК 21.4).

from typing import Callable, Awaitable, Dict, Any
from aiogram.types import TelegramObject

from infrastructure.repositories.users import get_global_rank
from services import global_moderation
from services.roles import DEVELOPER_GLOBAL_RANK

# БЛОК 21.4: два уровня доступа при глобальном ban.
# Игровая инфраструктура (гача/магазин/аукцион/походы/переводы/...) закрыта,
# но справочно-административные команды остаются доступными — раньше бан глушил
# ВООБЩЕ ВСЁ, включая «бот апелляция»: забаненный физически не мог оспорить
# санкцию, хотя команда для этого существует.
_BANNED_ALLOWED_ALIASES: tuple = (
    "апелляция",                      # оспорить санкцию — критично
    "глоб санкции",                   # посмотреть свои санкции
    "помощь", "меню", "команды", "хелп",
    "топ",                            # + все под-варианты «топ ...»
    "я", "профиль", "стата", "стат", "мой профиль",
    "кто", "инфо", "досье", "анкета",
)


def _banned_allowlist_match(event: TelegramObject) -> bool:
    """True, если апдейт — текстовая команда из справочного allowlist'а.
    Кнопки (callback) и все остальные команды для забаненного глушатся."""
    msg = getattr(event, "message", None)
    text = (getattr(msg, "text", None) or "").lower().strip()
    if not text.startswith("бот"):
        return False
    head = text[3:].lstrip(" ,.").strip().split(",")[0].strip()
    for alias in _BANNED_ALLOWED_ALIASES:
        if head == alias or head.startswith(alias + " "):
            return True
    return False


async def global_sanctions_middleware(
    handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
    event: TelegramObject,
    data: Dict[str, Any],
) -> Any:
    db = data["db"]
    user = data.get("event_from_user")
    chat_obj = data.get("event_chat")

    user_banned = False
    if user:
        actor_rank = await get_global_rank(db, user.id)
        if actor_rank >= DEVELOPER_GLOBAL_RANK:
            return await handler(event, data)  # Разработчик — иммунитет

        if await global_moderation.is_user_banned(db, user.id):
            if not _banned_allowlist_match(event):
                return  # игровые команды/кнопки: бот молчит
            user_banned = True  # справочная команда — пропускаем дальше

    if chat_obj:
        if await global_moderation.is_chat_banned(db, chat_obj.id):
            return  # бан целого чата глушит всё, allowlist не действует

        data["chat_restricted"] = await global_moderation.get_chat_restriction(db, chat_obj.id)

    if user:
        data["user_restricted"] = await global_moderation.get_user_restriction(db, user.id)
        data["user_banned"] = user_banned

    return await handler(event, data)
