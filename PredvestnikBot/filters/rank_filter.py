from aiogram import Bot
from aiogram.filters import BaseFilter
from aiogram.types import ChatMemberOwner, Message

from database.db import get_user_stats, set_rank_in_chat
from utils.ranks import has_permission

# Кэш: (chat_id, user_id) подтверждённых Telegram-создателей в этой сессии
_creator_cache: set[tuple[int, int]] = set()


async def check_and_promote_creator(bot: Bot, chat_id: int, user_id: int):
    """Если пользователь — Создатель чата, повышает его до 'owner' в user_stats."""
    key = (chat_id, user_id)
    if key in _creator_cache:
        return True
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if isinstance(member, ChatMemberOwner):
            # Ограничиваем кэш по размеру
            if len(_creator_cache) > 500:
                _creator_cache.clear()
            _creator_cache.add(key)
            stats = await get_user_stats(user_id, chat_id)
            if not stats or stats["rank"] not in ("owner", "developer"):
                await set_rank_in_chat(user_id, chat_id, "owner")
            return True
    except Exception:
        pass
    return False


class RankFilter(BaseFilter):
    """Пропускает команду только если ранг пользователя >= min_rank."""

    def __init__(self, min_rank: str):
        self.min_rank = min_rank

    async def __call__(self, message: Message, bot: Bot) -> bool:
        if not message.from_user:
            return False

        uid = message.from_user.id
        cid = message.chat.id

        # Telegram-создатель всегда проходит любой RankFilter
        if message.chat.type in ("group", "supergroup"):
            if await check_and_promote_creator(bot, cid, uid):
                return True

        stats = await get_user_stats(uid, cid)
        if not stats:
            return False
        return has_permission(stats["rank"], self.min_rank)

