import asyncio
import logging
import os
import re
import signal
from aiogram import Bot, Dispatcher
from aiogram.types import MenuButtonWebApp, WebAppInfo
from loguru import logger

from bot.config import config
from bot.core.database import init_db
from bot.middlewares.db import db_middleware
from bot.middlewares.config_mw import config_middleware
from bot.middlewares.preprod_gate_mw import preprod_gate_middleware
from bot.middlewares.global_sanctions_mw import global_sanctions_middleware
from bot.middlewares.purge_gate_mw import purge_gate_middleware
from bot.middlewares.outbound_throttle import OutboundThrottleMiddleware
from bot.handlers import main_router
from bot.handlers.payments import star_payment_reconciliation_task
from infrastructure.database import create_pool
from infrastructure.preprod import is_preprod
from services.scheduler import (
    maintenance_task,
    mafia_phase_task,
)

# Unique advisory lock key for this bot (arbitrary fixed integer).
# pg_advisory_lock blocks until no other session holds the same key,
# so a new deploy waits for the old dyno to die before it starts polling.
_ADVISORY_LOCK_KEY = 1748293847


_TELEGRAM_TOKEN_IN_URL = re.compile(
    r"(?i)(api\.telegram\.org/bot)\d+:[A-Za-z0-9_-]+"
)


class _SecretRedactionFilter(logging.Filter):
    """Keep Telegram bot credentials out of third-party HTTP logs."""

    @staticmethod
    def _redact(value):
        if isinstance(value, str):
            return _TELEGRAM_TOKEN_IN_URL.sub(r"\1<redacted>", value)
        if isinstance(value, tuple):
            return tuple(_SecretRedactionFilter._redact(item) for item in value)
        if isinstance(value, dict):
            return {
                key: _SecretRedactionFilter._redact(item)
                for key, item in value.items()
            }
        return value

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._redact(record.msg)
        record.args = self._redact(record.args)
        return True


class _SecretRedactingFormatter(logging.Formatter):
    """Redact formatted tracebacks as well as the LogRecord message fields."""

    def __init__(self, delegate: logging.Formatter):
        super().__init__()
        self._delegate = delegate

    def format(self, record: logging.LogRecord) -> str:
        rendered = self._delegate.format(record)
        return _SecretRedactionFilter._redact(rendered)


def _configure_safe_logging() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    redaction_filter = _SecretRedactionFilter()
    for handler in logging.getLogger().handlers:
        handler.addFilter(redaction_filter)
        formatter = handler.formatter or logging.Formatter()
        if not isinstance(formatter, _SecretRedactingFormatter):
            handler.setFormatter(_SecretRedactingFormatter(formatter))


def _spawn_supervised(name: str, coroutine, *, failed: asyncio.Event | None = None) -> asyncio.Task:
    """Keep a durable handle and make an unexpected task exit impossible to miss."""
    task = asyncio.create_task(coroutine, name=f"predvestnik:{name}")

    def _report_done(done: asyncio.Task) -> None:
        if done.cancelled():
            logger.info("Background task {} stopped by shutdown", name)
            return
        error = done.exception()
        if error is None:
            logger.critical("Background task {} exited unexpectedly", name)
        else:
            logger.opt(exception=error).critical("Background task {} crashed", name)
        if failed is not None:
            failed.set()

    task.add_done_callback(_report_done)
    return task


async def main():
    _configure_safe_logging()
    background_tasks: list[asyncio.Task] = []
    background_failed = asyncio.Event()

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
            background_tasks.append(_spawn_supervised(
                "miniapp", uvicorn.Server(_api_cfg).serve(), failed=background_failed,
            ))
            logger.info(f"🌐 FastAPI мини-апп запущен на порту {_api_port} (prefix='{_root_path}')")
            if is_preprod():
                # This second app is bound to loopback only and is never put
                # behind the Quick Tunnel.  It gives the automated browser one
                # synthetic identity without forging Telegram WebApp initData.
                from FastAPI.preprod_test_auth import TEST_AUTH_PORT, app as _test_auth_app
                _test_cfg = uvicorn.Config(
                    _test_auth_app, host="127.0.0.1", port=TEST_AUTH_PORT,
                    log_level="warning", lifespan="off",
                )
                background_tasks.append(_spawn_supervised(
                    "preprod-browser-auth", uvicorn.Server(_test_cfg).serve(), failed=background_failed,
                ))
                logger.info(f"🧪 Loopback browser-test auth started on 127.0.0.1:{TEST_AUTH_PORT}")
        except Exception as _e:
            logger.warning(f"FastAPI не запущен: {_e}")
    # ─────────────────────────────────────────────────────────────────────────

    logger.info("🐘 Подключение к PostgreSQL...")
    pool = await create_pool()

    logger.info("🗄️  Инициализация схемы БД...")
    await init_db()
    # FastAPI is deliberately co-hosted with lifespan disabled so that the bot
    # owns startup.  New Mini App tables/feature flags therefore must be
    # initialised here too; otherwise they exist only in a standalone ASGI run.
    from infrastructure.pg_adapter import PGAdapter
    from infrastructure.repositories import system_flags
    from infrastructure.repositories import rhythm_v2 as rhythm_v2_repo
    from infrastructure.repositories import mafia_v1 as mafia_v1_repo
    from infrastructure.repositories import minesweeper_v2 as minesweeper_v2_repo
    from infrastructure.repositories import pets_v1 as pets_v1_repo
    from infrastructure.repositories import achievements_v1 as achievements_v1_repo
    from infrastructure.repositories import public_profiles_v1 as public_profiles_v1_repo
    from infrastructure.repositories import global_skins_v1 as global_skins_v1_repo
    async with pool.acquire() as _startup_connection:
        _startup_db = PGAdapter(_startup_connection)
        await system_flags.ensure_table(_startup_db)
        await rhythm_v2_repo.ensure_tables(_startup_db)
        await mafia_v1_repo.ensure_tables(_startup_db)
        await minesweeper_v2_repo.ensure_tables(_startup_db)
        await pets_v1_repo.ensure_tables(_startup_db)
        await achievements_v1_repo.ensure_tables(_startup_db)
        await public_profiles_v1_repo.ensure_tables(_startup_db)
        await global_skins_v1_repo.ensure_tables(_startup_db)
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
    # Keep non-allowlisted users outside DB and business middleware when the
    # temporary Cloudflare-backed test bot is publicly reachable.
    dp.update.middleware(preprod_gate_middleware)
    dp.update.middleware(db_middleware)
    dp.update.middleware(global_sanctions_middleware)
    dp.update.middleware(purge_gate_middleware)   # admin_audit B5: режим письма при чистке

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
        # A queued ``successful_payment`` is money already paid by a player.
        # Never discard it during a rolling restart; the payment ledger makes a
        # replay safe, and the Stars-history task below repairs a crash window.
        await bot.delete_webhook(drop_pending_updates=False)

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

        background_tasks.extend([
            _spawn_supervised("maintenance", maintenance_task(), failed=background_failed),
            _spawn_supervised("mafia-phases", mafia_phase_task(bot), failed=background_failed),
        ])
        # Preprod intentionally has no Stars history/reconciliation access.
        # Do not spawn a coroutine that correctly returns immediately and then
        # misclassify that policy as a supervisor crash.
        if is_preprod():
            logger.info("Stars reconciliation is intentionally not scheduled on isolated preprod.")
        else:
            background_tasks.append(_spawn_supervised(
                "stars-reconciliation", star_payment_reconciliation_task(bot, pool), failed=background_failed,
            ))

        polling = asyncio.create_task(dp.start_polling(bot), name="predvestnik:polling")
        failed_wait = asyncio.create_task(background_failed.wait(), name="predvestnik:background-failure")
        done, pending = await asyncio.wait({polling, failed_wait}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        if failed_wait in done:
            raise RuntimeError("background task stopped; terminating for supervisor restart")
        await polling
    finally:
        logger.warning("🛑 Завершение сессии бота...")
        for task in background_tasks:
            task.cancel()
        if background_tasks:
            await asyncio.gather(*background_tasks, return_exceptions=True)
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
