"""
filters/chat_mode.py — Chat isolation mode filters.

MainChatOnly: blocks economy/game commands in admin and test isolated chats.
The `is_isolated_chat` boolean is injected by AutoModMiddleware via the data dict,
so this filter works correctly without extra DB calls.
"""
from aiogram.filters import BaseFilter
from aiogram.types import Message


class MainChatOnly(BaseFilter):
    """Pass-through filter for economy/game command routers.

    Returns False (blocks the command) when:
      - The message is from a group AND
      - The middleware has injected is_isolated_chat=True
        (chat is in admin_groups or test_chats)

    Private chats always pass. Non-group contexts always pass.
    """

    async def __call__(
        self,
        message: Message,
        is_isolated_chat: bool = False,
    ) -> bool:
        # Private chats and channels: always pass
        if message.chat.type not in ("group", "supergroup"):
            return True
        # Isolated chats: block
        return not is_isolated_chat
