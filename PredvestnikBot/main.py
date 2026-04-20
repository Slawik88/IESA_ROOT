import asyncio
import logging
import os
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from aiogram.exceptions import TelegramConflictError

from aiogram.types import ChatPermissions, MenuButtonWebApp, WebAppInfo
from config import BOT_TOKEN, MINI_APP_URL
from database.db import get_locked_chats, init_db, set_chat_setting, init_promocodes_table

# ── Logging MUST be configured before any module that uses `log = getLogger()`
from utils.bot_logging import setup_logging
setup_logging()
log = logging.getLogger("main")

# Время запуска бота (для игнорирования старых сообщений)
BOT_START_TIME = datetime.now(timezone.utc)
from handlers.router import main_router, payment_router

# basicConfig already called by setup_logging() above — no-op duplication guard removed


async def notify_developer(bot: Bot, text: str):
    from config import DEVELOPER_ID
    if not DEVELOPER_ID:
        return
    try:
        await bot.send_message(DEVELOPER_ID, text)
    except Exception as _e:
        log.debug("%s", _e)


async def configure_mini_app_menu_button(bot: Bot):
    if not MINI_APP_URL:
        return
    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Открыть App",
                web_app=WebAppInfo(url=MINI_APP_URL),
            )
        )
        logging.info("Mini App menu button configured: %s", MINI_APP_URL)
    except Exception as exc:
        logging.warning("Could not configure Mini App menu button: %s", exc)


async def main():
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    from utils.bot_instance import set_bot
    set_bot(bot)

    # FSM-хранилище: PostgreSQL вместо MemoryStorage (диалоги переживают перезапуск)
    from database.pg_fsm_storage import PostgresStorage
    fsm_storage = PostgresStorage()
    dp = Dispatcher(storage=fsm_storage)

    # Инициализация базы данных
    await init_db()
    await init_promocodes_table()
    # Создание таблицы fsm_data (если нет)
    await fsm_storage.init_table()

    # Авто-разблокировка чатов, которые остались заблокированы после "бот чистка"
    _full_perms = ChatPermissions(
        can_send_messages=True, can_send_audios=True, can_send_documents=True,
        can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
        can_send_voice_notes=True, can_send_polls=True,
        can_send_other_messages=True, can_add_web_page_previews=True,
    )
    for _locked_chat_id in await get_locked_chats():
        try:
            await bot.set_chat_permissions(_locked_chat_id, _full_perms)
            await set_chat_setting(_locked_chat_id, "cleanup_locked", 0)
            logging.info("Auto-unlocked chat %s after bot restart", _locked_chat_id)
        except Exception as _e:
            logging.warning("Could not auto-unlock chat %s: %s", _locked_chat_id, _e)

    # Middleware: регистрация юзеров + антифлуд + замки + чёрный список
    from middlewares.message_counter import AutoModMiddleware, set_bot_start_time
    set_bot_start_time(BOT_START_TIME)  # Защита от обработки старых сообщений
    dp.message.outer_middleware(AutoModMiddleware())

    # Middleware: блокировка callback-кнопок экономики в изолированных чатах
    from middlewares.callback_isolation import CallbackIsolationMiddleware
    dp.callback_query.outer_middleware(CallbackIsolationMiddleware())

    # ── Global error handler: catch unhandled exceptions and log them ──
    from aiogram.types import ErrorEvent
    @dp.errors()
    async def _global_error_handler(error_event: ErrorEvent):
        logging.exception("Unhandled error in handler: %s", error_event.exception)
        return True

    # Роутеры — собраны в handlers/router.py (extras последним, payment отдельно)
    dp.include_router(main_router)
    dp.include_router(payment_router)  # Payment callbacks (no MainChatOnly filter)

    from config import BOT_STARTED_MSG, BOT_STOPPED_MSG
    print("✅ Бот запущен! Пиши 'бот помощь' в чат.")
    await notify_developer(bot, BOT_STARTED_MSG)
    await configure_mini_app_menu_button(bot)

    # Фоновые задачи (планировщик, boss flush, dev_event_poll) стартуют
    # автоматически через FastAPI lifespan в web_app.py

    # ─────────────────────────────────────────────────────────────────────────
    #  FastAPI веб-сервер (webhook + Mini App API + статика)
    # ─────────────────────────────────────────────────────────────────────────
    from web_app import app as fastapi_app, set_bot_and_dp
    set_bot_and_dp(bot, dp)

    import uvicorn
    port = int(os.environ.get("BOT_WEB_PORT", 8081))

    # ─────────────────────────────────────────────────────────────────────────
    # WEBHOOK vs POLLING GUARD — двухуровневая защита от TelegramConflictError
    # ─────────────────────────────────────────────────────────────────────────
    _webhook_url = (
        os.getenv("BOT_WEBHOOK_URL") or
        os.getenv("WEBHOOK_URL") or
        ""
    ).strip()

    _registered_webhook = ""
    try:
        _whi = await bot.get_webhook_info()
        _registered_webhook = (_whi.url or "").strip()
    except Exception as _whi_exc:
        logging.warning("Не удалось получить webhook info: %s", _whi_exc)
        if _webhook_url or os.getenv("DATABASE_URL"):
            _registered_webhook = "assumed-active (get_webhook_info failed)"

    _use_webhook = bool(_webhook_url or _registered_webhook)

    if _use_webhook:
        # ── Webhook-режим: FastAPI принимает апдейты через POST /webhook ──
        active = _webhook_url or _registered_webhook
        logging.info("🔗 WEBHOOK режим: %s — FastAPI на порту %d", active, port)

        # Регистрируем/обновляем webhook в Telegram (всегда, чтобы обновить allowed_updates)
        if _webhook_url:
            secret = os.getenv("WEBHOOK_SECRET", "")
            _desired_allowed = ["message", "callback_query", "chat_member", "my_chat_member", "pre_checkout_query", "shipping_query"]
            try:
                await bot.set_webhook(
                    url=_webhook_url + "/webhook",
                    secret_token=secret or None,
                    drop_pending_updates=(_webhook_url != _registered_webhook),
                    allowed_updates=_desired_allowed,
                )
                logging.info("Webhook обновлён: %s/webhook allowed=%s", _webhook_url, _desired_allowed)
            except Exception as _sw_exc:
                logging.error("Не удалось установить webhook: %s", _sw_exc)

        config = uvicorn.Config(
            fastapi_app, host="0.0.0.0", port=port,
            log_level="info", access_log=False,
        )
        server = uvicorn.Server(config)
        try:
            await server.serve()
        finally:
            await notify_developer(bot, BOT_STOPPED_MSG)
        return

    # ── Polling-режим (локальная разработка) + FastAPI в фоне ────────────────
    logging.info("📡 Polling + FastAPI на порту %d (локальная разработка).", port)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as _wh_exc:
        logging.warning("Не удалось удалить webhook: %s", _wh_exc)

    # Запускаем FastAPI в фоне (Mini App API работает и при поллинге)
    config = uvicorn.Config(
        fastapi_app, host="0.0.0.0", port=port,
        log_level="info", access_log=False,
    )
    server = uvicorn.Server(config)
    asyncio.create_task(server.serve())

    try:
        await dp.start_polling(
            bot,
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query", "chat_member", "my_chat_member", "pre_checkout_query", "shipping_query"],
        )
    except TelegramConflictError:
        logging.critical(
            "TelegramConflictError: другой экземпляр бота уже запущен! "
            "Убедитесь, что поллинг идёт только из одного процесса."
        )
        raise
    finally:
        await notify_developer(bot, BOT_STOPPED_MSG)



if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен.")