from aiogram import Router
from aiogram.types import Message

# Импорт модулей регистрирует их команды в общем реестре.
from bot.chat import admin_chat, help, members, moderation, purge, rank_commands, sanctions, site, top  # noqa: F401
from bot.chat.framework import dispatch, registry
from bot.chat.tracking import record_message

router = Router(name="chat")
for sub in (top.router, help.router, rank_commands.router, moderation.router, purge.router, sanctions.router, members.router):
    router.include_router(sub)


@router.message()
async def on_message(message: Message, bot, db) -> None:
    """Каждое сообщение: закрытый чат, учёт активности, затем команда."""
    from loguru import logger
    try:
        if await purge.purge_gate(db, bot, message) or await moderation.closed_gate(db, bot, message):
            return
    except Exception as exc:
        logger.warning(f"closed-chat gate failed: {exc}")
    try:
        await record_message(db, message)
    except Exception as exc:  # учёт не должен ломать команды
        logger.warning(f"message tracking failed: {exc}")
    await dispatch(registry, message, bot, db)
