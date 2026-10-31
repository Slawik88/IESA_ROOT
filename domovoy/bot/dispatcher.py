"""
bot/dispatcher.py — сборка диспетчера: порядок роутеров важен.
"""
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import cleaning, dev, money, settings, start


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    # start — первым: он сбрасывает состояния и раздаёт меню.
    dp.include_routers(start.router, cleaning.router, money.router, settings.router, dev.router)
    return dp
