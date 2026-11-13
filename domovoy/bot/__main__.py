"""
bot/__main__.py — точка входа «Домового». Запуск: `cd domovoy && python -m bot`.
"""
import asyncio
import sys
from contextlib import contextmanager

from aiogram import Bot
from loguru import logger

from bot.dispatcher import build_dispatcher
from core import config
from core.constants import SCHEDULER_TICK_SECONDS
from infrastructure.db import db
from infrastructure.schema import ensure_schema
from services import scheduler


def web_server(bot):
    import uvicorn
    from web.app import create_app

    class EmbeddedServer(uvicorn.Server):
        @contextmanager
        def capture_signals(self):
            # Завершением процесса управляет aiogram.
            yield

    return EmbeddedServer(uvicorn.Config(create_app(bot=bot), host="127.0.0.1", port=8011,
                                         access_log=False, log_level="warning", lifespan="off"))


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
    server = web_server(bot)
    site = asyncio.create_task(server.serve(), name="domovoy-web")
    polling = asyncio.create_task(dp.start_polling(bot), name="domovoy-polling")
    try:
        done, _ = await asyncio.wait({polling, site}, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
        if site in done:
            raise RuntimeError("Закрытый веб-сервис неожиданно остановлен")
    finally:
        server.should_exit = True
        for task in (reminders, site, polling):
            task.cancel()
        await asyncio.gather(reminders, site, polling, return_exceptions=True)
        await bot.session.close()
        await db.close()
        logger.info("👋 Домовой остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
