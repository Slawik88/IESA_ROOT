from aiogram import Router
from aiogram.types import Message

# Импорт модулей регистрирует их команды в общем реестре.
from bot.chat import account, achievements, admin_chat, family, games, help, mafia, members, moderation, profile, promo, purge, rank_commands, sanctions, site, streak, top, transfer, vip, warps  # noqa: F401
from bot.chat.framework import dispatch, registry
from bot.chat.tracking import record_message
from bot.chat.warps_data import WARPS

warps.register_all(WARPS)


async def _feature_gate(ctx) -> str | None:
    """Выключатели из админки: команда не запускается, если она (или её раздел, или весь бот) выключена."""
    from services import feature_switches as fs
    chat = ctx.message.chat
    chat_id = chat.id if chat.type in ("group", "supergroup") else None
    cmd = ctx.command
    hit = await fs.disabled(ctx.db, fs.command_features(cmd.name, cmd.section, cmd.group), chat_id)
    if hit is None:
        return None
    feature, reason = hit
    if feature == "all":
        return ""   # весь бот выключен — молчим
    return "⛔ Сейчас это недоступно" + (f": {reason}" if reason else ".")


registry.gate = _feature_gate

router = Router(name="chat")
for sub in (top.router, help.router, family.router, games.router, mafia.router, rank_commands.router, moderation.router, purge.router, sanctions.router, transfer.router, members.router, vip.router):
    router.include_router(sub)


@router.message()
async def on_message(message: Message, bot, db) -> None:
    """Каждое сообщение: закрытый чат, учёт активности, затем команда."""
    from loguru import logger
    from services import feature_switches
    chat_id = message.chat.id if message.chat.type in ("group", "supergroup") else None
    try:
        bot_off = await feature_switches.disabled(db, ["all"], chat_id) is not None
    except Exception as exc:
        logger.warning(f"feature switches unavailable: {exc}")
        bot_off = False
    if bot_off:   # весь бот выключен: только учёт сообщений (статистика), без ответов и ворот
        try:
            await record_message(db, message)
        except Exception as exc:
            logger.warning(f"message tracking failed: {exc}")
        await dispatch(registry, message, bot, db)   # выключатель пропустит только «бот админка»
        return
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
