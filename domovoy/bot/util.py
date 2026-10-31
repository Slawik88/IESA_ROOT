"""
bot/util.py — помощники тонкого слоя: дом пользователя, защита обработчиков.
"""
from functools import wraps
from typing import Awaitable, Callable

from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from core.money import AmountError
from infrastructure import repositories as repo
from services import households
from services.households import DomainError


async def resolve_house(tg_id: int):
    """Выбранный дом пользователя; единственный дом выбирается сам."""
    user = await repo.users.get_user(tg_id)
    if user and user["active_house_id"]:
        house = await households.get_house(user["active_house_id"])
        if house:
            membership = await households.membership(house["id"], tg_id)
            if membership and membership["status"] == "active":
                return house
        await repo.users.set_active_house(tg_id, None)
    houses = await households.houses_of_user(tg_id)
    if len(houses) == 1:
        await repo.users.set_active_house(tg_id, houses[0]["id"])
        return await households.get_house(houses[0]["id"])
    return None


def guard(handler: Callable[..., Awaitable]):
    """Доменные отказы (DomainError/AmountError) превращаются в понятное сообщение."""

    @wraps(handler)
    async def wrapper(event, *args, **kwargs):
        try:
            return await handler(event, *args, **kwargs)
        except DomainError as exc:
            text = str(exc)
        except AmountError as exc:
            text = str(exc)
        if isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)
        elif isinstance(event, Message):
            await event.answer(text)
        else:
            raise
        return None

    return wrapper


async def safe_edit(cb: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None = None):
    """Отредактировать сообщение; недоступное — ответить новым (старые кнопки живут часами)."""
    try:
        await cb.message.edit_text(text, reply_markup=markup)
    except Exception:
        await cb.message.answer(text, reply_markup=markup)


def fmt_date(iso_date: str) -> str:
    """'2026-10-31' → '31.10'."""
    parts = iso_date.split("-")
    return f"{parts[2]}.{parts[1]}" if len(parts) == 3 else iso_date
