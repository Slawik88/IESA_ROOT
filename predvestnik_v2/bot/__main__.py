import asyncio
import logging
import signal
from aiogram import Bot, Dispatcher
from loguru import logger

from bot.config import config
from bot.core.database import init_db
from bot.middlewares.db import db_middleware
from bot.middlewares.config_mw import config_middleware
from bot.middlewares.pet_bonuses_mw import pet_bonuses_middleware
from bot.middlewares.streak_mw import streak_middleware
from bot.handlers import main_router
from infrastructure.database import create_pool
from services.scheduler import (
    expedition_background_task, daily_deal_task,
    duel_and_auction_task, chest_spawn_task,
    exchange_scheduler_task,
)


async def main():
    logging.basicConfig(level=logging.INFO)

    logger.info("═" * 50)
    logger.info("🔮 ПРЕДВЕСТНИК V2 — ЗАПУСК СИСТЕМЫ")
    logger.info("═" * 50)
    logger.info("📊 Архитектура: PostgreSQL + asyncpg")

    logger.info("🐘 Подключение к PostgreSQL...")
    await create_pool()

    logger.info("🗄️  Инициализация схемы БД...")
    await init_db()
    logger.info("✅ База данных готова!")

    logger.info("⚙️  Инициализация Telegram Bot API...")
    bot = Bot(token=config.bot_token)
    dp = Dispatcher()

    logger.info("🔌 Подключение Middleware...")
    dp.update.middleware(config_middleware)
    dp.update.middleware(db_middleware)
    dp.update.middleware(pet_bonuses_middleware)
    dp.update.middleware(streak_middleware)

    logger.info("📡 Регистрация роутеров...")
    dp.include_router(main_router)
    logger.info("✅ Все роутеры подключены!")

    def _on_sigterm():
        logger.warning("🛑 SIGTERM получен — завершение.")
        raise SystemExit(0)

    try:
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, _on_sigterm)
    except (NotImplementedError, AttributeError):
        pass  # Windows

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("═" * 50)
        logger.info("🟢 БОТ ГОТОВ К ПРИЕМУ СООБЩЕНИЙ")
        logger.info("═" * 50)

        asyncio.create_task(expedition_background_task(bot))
        asyncio.create_task(daily_deal_task())
        asyncio.create_task(duel_and_auction_task(bot))
        asyncio.create_task(chest_spawn_task(bot))
        asyncio.create_task(exchange_scheduler_task(bot))

        await dp.start_polling(bot)
    finally:
        logger.warning("🛑 Завершение сессии бота...")
        await bot.session.close()
        logger.info("✅ Сессия закрыта.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Принудительное завершение.")
