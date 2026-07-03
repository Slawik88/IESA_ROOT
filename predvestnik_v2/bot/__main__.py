import asyncio
import logging
import os
import signal
from aiogram import Bot, Dispatcher
from aiogram.types import MenuButtonWebApp, WebAppInfo
from loguru import logger

from bot.config import config
from bot.core.database import init_db
from bot.middlewares.db import db_middleware
from bot.middlewares.config_mw import config_middleware
from bot.middlewares.global_sanctions_mw import global_sanctions_middleware
from bot.middlewares.pet_bonuses_mw import pet_bonuses_middleware
from bot.middlewares.streak_mw import streak_middleware
from bot.middlewares.outbound_throttle import OutboundThrottleMiddleware
from bot.handlers import main_router
from infrastructure.database import create_pool
from services.scheduler import (
    expedition_background_task, daily_deal_task,
    duel_and_auction_task, chest_spawn_task,
    anniversary_task, smart_pulse_task,
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

    # ── FastAPI starts FIRST so health checks pass immediately ────────────────
    # DigitalOcean probes the PORT immediately after container start.
    # create_pool() can block for up to ~3 min on a transient DB issue, so
    # FastAPI must be listening before we attempt any DB work.
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
    # ─────────────────────────────────────────────────────────────────────────

    logger.info("🐘 Подключение к PostgreSQL...")
    pool = await create_pool()

    logger.info("🗄️  Инициализация схемы БД...")
    await init_db()
    logger.info("✅ База данных готова!")

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
    # Троттлинг ВСЕХ исходящих запросов (не апдейтов!) — предотвращает flood
    # control Telegram при высокой активности чата (см. bot/middlewares/outbound_throttle.py).
    bot.session.middleware(OutboundThrottleMiddleware())
    dp = Dispatcher()

    logger.info("🔌 Подключение Middleware...")
    dp.update.middleware(config_middleware)
    dp.update.middleware(db_middleware)
    dp.update.middleware(global_sanctions_middleware)
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

        # Update the menu button URL to the mini app.
        # MINIAPP_URL must be HTTPS for WebAppInfo (Telegram requirement).
        _miniapp_url = os.getenv("MINIAPP_URL", "")
        if _miniapp_url.startswith("https://"):
            try:
                await bot.set_chat_menu_button(
                    menu_button=MenuButtonWebApp(
                        text="🔮 Мини-апп",
                        web_app=WebAppInfo(url=_miniapp_url),
                    )
                )
                logger.info(f"✅ Кнопка меню → {_miniapp_url}")
            except Exception as _e:
                logger.warning(f"Кнопка меню не установлена: {_e}")

        # Log RARITY_STICKER_ID so developer can easily copy it
        _rarity_sid = os.getenv("RARITY_STICKER_ID", "")
        if _rarity_sid:
            logger.info(f"🦄 RARITY_STICKER_ID установлен: {_rarity_sid}")
        else:
            logger.warning(
                "🦄 RARITY_STICKER_ID не задан. Чтобы добавить стикер Рарити:\n"
                "   1. Перешлите стикер боту в ЛС\n"
                "   2. В логах появится: 🎴 STICKER file_id=<id>\n"
                "   3. Скопируйте <id> → установите RARITY_STICKER_ID в DigitalOcean env"
            )

        logger.info("═" * 50)
        logger.info("🟢 БОТ ГОТОВ К ПРИЕМУ СООБЩЕНИЙ")
        logger.info("═" * 50)

        asyncio.create_task(expedition_background_task(bot))
        asyncio.create_task(daily_deal_task())
        asyncio.create_task(duel_and_auction_task(bot))
        asyncio.create_task(chest_spawn_task(bot))
        asyncio.create_task(anniversary_task(bot))
        asyncio.create_task(smart_pulse_task(bot))

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
