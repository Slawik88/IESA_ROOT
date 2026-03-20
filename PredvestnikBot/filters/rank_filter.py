from aiogram import Bot
from aiogram.filters import BaseFilter
from aiogram.types import Message

from config import DEVELOPER_ID
from database.db import get_user_stats
from utils.ranks import has_permission


class RankFilter(BaseFilter):
    """Пропускает команду только если ранг пользователя >= min_rank."""

    def __init__(self, min_rank: str):
        self.min_rank = min_rank

    async def __call__(self, message: Message, bot: Bot) -> bool:
        if not message.from_user:
            return False

        uid = message.from_user.id
        cid = message.chat.id

        # Разработчик всегда проходит любой фильтр
        if DEVELOPER_ID and uid == DEVELOPER_ID:
            return True

        stats = await get_user_stats(uid, cid)
        if not stats:
            return False
        return has_permission(stats["rank"], self.min_rank)

