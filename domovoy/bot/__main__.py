"""
bot/__main__.py — точка входа «Домового». Запуск: `cd domovoy && python -m bot`.
"""
import asyncio
import sys

from aiogram import Bot
from loguru import logger

from bot.dispatcher import build_dispatcher
from core import config
from core.constants import SCHEDULER_TICK_SECONDS
from infrastructure.db import db
from infrastructure.schema import ensure_schema
from services import scheduler


async def scheduler_loop(bot: Bot) -> None:
    """Фоновый цикл напоминаний; падение тика не убивает цикл."""
    while True:
        try:
            await scheduler.tick(bot)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception(f"⏰ Цикл планировщика упал: {exc}")
        await asyncio.sleep(SCHEDULER_TICK_SECONDS)


async def main() -> None:
    logger.remove()
    logger.add(sys.stderr, level=config.LOG_LEVEL)
    if not config.BOT_TOKEN:
        raise RuntimeError("DOMOVOY_BOT_TOKEN не задан — заполните domovoy/.env")

    await db.connect()
    await ensure_schema()

    bot = Bot(config.BOT_TOKEN)
    me = await bot.get_me()
    logger.info(f"🤖 Домовой @{me.username} выходит на связь")

    dp = build_dispatcher()
    reminders = asyncio.create_task(scheduler_loop(bot), name="domovoy-reminders")
    try:
        await dp.start_polling(bot)
    finally:
        reminders.cancel()
        try:
            await reminders
        except asyncio.CancelledError:
            pass
        await db.close()
        logger.info("👋 Домовой остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
