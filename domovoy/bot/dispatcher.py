"""
bot/dispatcher.py — сборка диспетчера: порядок роутеров важен.
"""
from aiogram import BaseMiddleware, Dispatcher, Router
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation

from bot.handlers import cleaning, dev, money, money_files, settings, start, transaction_form
from bot import cb


class PrivateCallbacks(BaseMiddleware):
    """Данные дома и формы доступны в личке; в группе — только привязка чата."""

    async def __call__(self, handler, event, data):
        if event.message is None:
            await event.answer("Откройте меню в личке у бота через /start", show_alert=True)
            return
        if event.message.chat.type != "private" and event.data != cb.settings_bind_chat():
            await event.answer("Откройте меню в личке у бота через /start", show_alert=True)
            return
        return await handler(event, data)


async def stale_callback(event):
    await event.answer("Эта кнопка устарела. Откройте меню через /start.", show_alert=True)


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage(), events_isolation=SimpleEventIsolation())
    dp.callback_query.outer_middleware(PrivateCallbacks())
    # start — первым: он сбрасывает состояния и раздаёт меню.
    dp.include_routers(start.router, cleaning.router, money.router, transaction_form.router,
                       money_files.router, settings.router, dev.router)
    fallback = Router(name="fallback")
    fallback.callback_query.register(stale_callback)
    dp.include_router(fallback)
    return dp
