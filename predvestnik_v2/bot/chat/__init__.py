from aiogram import Router
from aiogram.types import Message

# Импорт модулей регистрирует их команды в общем реестре.
from bot.chat import account, achievements, admin_chat, family, games, help, mafia, members, moderation, profile, promo, purge, rank_commands, sanctions, site, streak, top, transfer, warps  # noqa: F401
from bot.chat.framework import dispatch, registry
from bot.chat.tracking import record_message
from bot.chat.warps_data import WARPS

warps.register_all(WARPS)

router = Router(name="chat")
for sub in (top.router, help.router, family.router, games.router, mafia.router, rank_commands.router, moderation.router, purge.router, sanctions.router, transfer.router, members.router):
    router.include_router(sub)


@router.message()
async def on_message(message: Message, bot, db) -> None:
    """Каждое сообщение: закрытый чат, учёт активности, затем команда."""
    from loguru import logger
    try:
        if await mafia.gate_message(db, bot, message):
            return
    except Exception as exc:
        logger.warning(f"mafia gate failed: {exc}")
    try:
        if await purge.purge_gate(db, bot, message) or await moderation.closed_gate(db, bot, message):
            return
    except Exception as exc:
        logger.warning(f"closed-chat gate failed: {exc}")
    try:
        await record_message(db, message)
    except Exception as exc:  # учёт не должен ломать команды
        logger.warning(f"message tracking failed: {exc}")
    try:
        await mafia.after_message(db, bot, message)
    except Exception as exc:
        logger.warning(f"mafia lobby repost failed: {exc}")
    await dispatch(registry, message, bot, db)
    await achievements.after_message(db, message)   # после ответа на команду, сам ловит ошибки
