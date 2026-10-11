"""Общие мелочи для кнопок под сообщениями бота."""
from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery


async def edit_or_send(call: CallbackQuery, text: str, **kw) -> None:
    """Обновить сообщение с кнопками. Повторное нажатие (текст уже такой) молчит; сообщение старше 48 часов
    Telegram считает недоступным и править не даёт — тогда пишем новым сообщением в тот же чат."""
    try:
        await call.message.edit_text(text, **kw)
    except TelegramBadRequest as exc:
        if "not modified" in str(exc):
            return
        await _send_fresh(call, text, **kw)
    except AttributeError:   # у «недоступного» сообщения нет edit_text
        await _send_fresh(call, text, **kw)


async def _send_fresh(call: CallbackQuery, text: str, **kw) -> None:
    try:
        await call.bot.send_message(call.message.chat.id, text, **kw)
    except Exception:  # noqa: BLE001 - бот мог лишиться права писать
        pass
