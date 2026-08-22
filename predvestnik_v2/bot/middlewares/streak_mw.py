"""Compatibility middleware for the retired currency streak.

Existing streak values remain visible as legacy records. Chat messages no
longer mutate that record or mint Mora, Diamonds, spin tokens, or achievements.
The replacement Rhythm system will use meaningful gameplay days, not raw text.
"""
from typing import Any, Awaitable, Callable, Dict

from aiogram.types import TelegramObject


async def streak_middleware(
    handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
    event: TelegramObject,
    data: Dict[str, Any],
) -> Any:
    """Pass the update through without economic or progression side effects."""
    return await handler(event, data)
