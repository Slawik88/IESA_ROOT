from aiogram import F, Router
from aiogram.types import Message

from bot.chat import top  # noqa: F401  (регистрирует команду «топ»)
from bot.chat.framework import dispatch, registry
from bot.chat.tracking import record_message

router = Router(name="chat")
router.include_router(top.router)


@router.message()
async def on_message(message: Message, bot, db) -> None:
    """Каждое сообщение: учёт активности, затем попытка выполнить команду."""
    try:
        await record_message(db, message)
    except Exception as exc:  # учёт не должен ломать команды
        from loguru import logger
        logger.warning(f"message tracking failed: {exc}")
    await dispatch(registry, message, bot, db)
