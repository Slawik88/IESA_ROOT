import asyncio
import logging
import os
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
from infrastructure.database import create_pool, get_pool
from services.scheduler import (
    expedition_background_task, daily_deal_task,
    duel_and_auction_task, chest_spawn_task,
    exchange_scheduler_task,
)

# Unique advisory lock key for this bot (arbitrary fixed integer).
# pg_advisory_lock blocks until no other session holds the same key,
# so a new deploy waits for the old dyno to die before it starts polling.
_ADVISORY_LOCK_KEY = 1748293847


async def main():
    logging.basicConfig(level=logging.INFO)

    logger.info("═" * 50)
    logger.info("🔮 ПРЕДВЕСТНИК V2 — ЗАПУСК СИСТЕМЫ")
    logger.info("═" * 50)
    logger.info("📊 Архитектура: PostgreSQL + asyncpg")

    logger.info("🐘 Подключение к PostgreSQL...")
    pool = await create_pool()

    logger.info("🗄️  Инициализация схемы БД...")
    await init_db()
    logger.info("✅ База данных готова!")

    # ── FastAPI starts BEFORE advisory lock so health checks pass immediately ──
    # DigitalOcean health checks port immediately after container start.
    # Advisory lock can block for ~90s during rolling redeploy — if FastAPI
    # starts after the lock, health checks time out and the deploy fails.
    _api_port = int(os.getenv("PORT", "0"))
    if _api_port:
        try:
            import uvicorn
            from FastAPI.main import app as _fastapi_app
            from FastAPI.prefix import strip_prefix_middleware

            _root_path = os.getenv("ROOT_PATH", "").rstrip("/")
            _mounted_app = (
                strip_prefix_middleware(_fastapi_app, _root_path)
                if _root_path else _fastapi_app
            )
            _api_cfg = uvicorn.Config(
                _mounted_app,
                host="0.0.0.0",
                port=_api_port,
                log_level="warning",
                lifespan="off",
            )
            asyncio.ensure_future(uvicorn.Server(_api_cfg).serve())
            logger.info(f"🌐 FastAPI мини-апп запущен на порту {_api_port} (prefix='{_root_path}')")
        except Exception as _e:
            logger.warning(f"FastAPI не запущен: {_e}")

    # ── Advisory lock: only one bot instance polls at a time ──────────────────
    # Acquires a session-level PostgreSQL advisory lock. If another instance
    # holds it (e.g. the previous dyno during a rolling redeploy), this call
    # blocks until that instance dies and its connection is closed.
    # The lock is automatically released when _lock_conn is closed in finally.
    logger.info("🔒 Ожидание advisory lock (единственный инстанс)...")
    _lock_conn = await pool.acquire()
    await _lock_conn.execute(f"SELECT pg_advisory_lock({_ADVISORY_LOCK_KEY})")
    logger.info("🔒 Advisory lock получен — этот инстанс единственный.")
    # ─────────────────────────────────────────────────────────────────────────

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
        # Release advisory lock by closing the dedicated connection
        try:
            await pool.release(_lock_conn)
        except Exception:
            pass
        logger.info("✅ Сессия закрыта.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Принудительное завершение.")
