import asyncio
import logging
from aiogram import Bot, Dispatcher
from loguru import logger

from bot.config import config
from bot.core.database import init_db
from bot.middlewares.db import db_middleware
from bot.middlewares.config_mw import config_middleware
from bot.middlewares.pet_bonuses_mw import pet_bonuses_middleware
from bot.middlewares.streak_mw import streak_middleware
from bot.handlers import main_router
from services.scheduler import (
    expedition_background_task, daily_deal_task,
    duel_and_auction_task, chest_spawn_task,
    exchange_scheduler_task,
)

async def main():
    # Включаем логирование ошибок aiogram
    logging.basicConfig(level=logging.INFO)
    
    # Красивый баннер запуска
    logger.info("═" * 50)
    logger.info("🔮 ПРЕДВЕСТНИК V2 — ЗАПУСК СИСТЕМЫ")
    logger.info("═" * 50)
    logger.info("📊 Архитектура: Layered Architecture")
    logger.info("🗄️  Инициализация базы данных...")
    
    # Создаем таблицы (если их нет)
    await init_db()
    logger.info("✅ База данных готова!")
    
    logger.info("⚙️  Инициализация Telegram Bot API...")
    bot = Bot(token=config.bot_token)
    dp = Dispatcher()
    
    # 1. Подключаем Middleware (Он ловит сообщения, регает юзеров и дает опыт)
    logger.info("🔌 Подключение Middleware...")
    dp.update.middleware(config_middleware)
    dp.update.middleware(db_middleware)
    # pet_bonuses и streak запускаются после db (FIFO), только для message-событий
    dp.update.middleware(pet_bonuses_middleware)
    dp.update.middleware(streak_middleware)
    
    # 2. Подключаем Роутеры (Наши команды)
    logger.info("📡 Регистрация роутеров...")
    dp.include_router(main_router)
    logger.info("✅ Все роутеры подключены!")
    
    try:
        # ЭТА СТРОЧКА УДАЛЯЕТ ВСЕ СООБЩЕНИЯ ЗА ВРЕМЯ ПРОСТОЯ:
        await bot.delete_webhook(drop_pending_updates=True) 
        logger.info("═" * 50)
        logger.info("🟢 БОТ ГОТОВ К ПРИЕМУ СООБЩЕНИЙ")
        logger.info("═" * 50)
        # Запускаем фоновые задачи (Экспедиции)
        asyncio.create_task(expedition_background_task(bot))
        asyncio.create_task(daily_deal_task())
        asyncio.create_task(duel_and_auction_task(bot))
        asyncio.create_task(chest_spawn_task(bot))
        asyncio.create_task(exchange_scheduler_task(bot))
        logger.info("🟢 БОТ ГОТОВ К ПРИЕМУ СООБЩЕНИЙ")
        await dp.start_polling(bot)
    finally:
        logger.warning("🛑 Завершение сессии бота...")
        await bot.session.close()
        logger.info("✅ Сессия закрыта. До свидания!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Принудительное завершение.")