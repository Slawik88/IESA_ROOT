from aiogram import F, Router
from aiogram.types import Message

# Импорт модулей регистрирует их команды в общем реестре.
from bot.chat import account, achievements, admin_chat, admin_help, cosmetics, family, games, help, mafia, members, migration, moderation, onboarding, pets, profile, promo, purge, rank_commands, reports, sanctions, site, streak, star_dust, tags, top, transfer, vip, warps, word_chain  # noqa: F401
from bot.chat import aliases  # noqa: F401,E402  (после всех команд)
from bot.chat import mafia_online  # noqa: F401,E402  (отдельный режим, локальная команда без изменений)
from bot.chat import inactive  # noqa: F401,E402
from bot.chat.framework import dispatch, registry
from bot.chat.tracking import record_message
from bot.chat.warps_data import WARPS

warps.register_all(WARPS)


async def _feature_gate(ctx) -> str | None:
    """Админка: заблокированному игроку бот не отвечает; выключенная команда (раздел, весь бот) не запускается."""
    from services import feature_switches as fs
    from services import global_moderation
    if await global_moderation.is_blocked(ctx.db, ctx.user_id):
        return ""   # игрок заблокирован в боте из админки — молчим
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


async def _record_usage(ctx) -> None:
    from services import bot_metrics
    place = "private" if ctx.message.chat.type == "private" else "group"
    try:
        await bot_metrics.record_command(ctx.db, ctx.command.name, ctx.user_id, place)
    finally:   # метрика не должна мешать мастеру подключения
        if place == "group":   # первая команда в чате завершает подключение (мастер в onboarding.py)
            from bot.chat import onboarding
            await onboarding.on_command_used(ctx.bot, ctx.db, ctx.message.chat.id)


async def _silent(message, db) -> bool:
    """Бот молчит целиком: игрок заблокирован в админке или весь бот выключен (глобально или в чате)."""
    from services import feature_switches as fs
    from services import global_moderation
    if message.from_user and await global_moderation.is_blocked(db, message.from_user.id):
        return True
    chat = message.chat
    chat_id = chat.id if chat.type in ("group", "supergroup") else None
    return await fs.disabled(db, ["all"], chat_id) is not None


registry.gate = _feature_gate
registry.on_used = _record_usage
registry.silent = _silent

router = Router(name="chat")


async def _callback_gate(handler, event, data):
    """Кнопки под сообщениями бота: заблокированному игроку и при выключенном боте — отказ."""
    db = data.get("db")
    msg = getattr(event, "message", None)
    if db is not None and msg is not None:
        try:
            from services import feature_switches as fs
            from services import global_moderation
            chat_id = msg.chat.id if msg.chat.type in ("group", "supergroup") else None
            if (await global_moderation.is_blocked(db, event.from_user.id)
                    or await fs.disabled(db, ["all"], chat_id) is not None):
                await event.answer("⛔ Сейчас это недоступно.", show_alert=True)
                return None
        except Exception:
            pass
    return await handler(event, data)


for sub in (top.router, help.router, inactive.router, family.router, games.router, mafia.router, rank_commands.router, moderation.router, purge.router, sanctions.router, transfer.router, members.router, vip.router, pets.router, star_dust.router, word_chain.router):
    sub.callback_query.middleware(_callback_gate)
    router.include_router(sub)


router.message.register(migration.on_migrated, F.migrate_to_chat_id)   # раньше общего обработчика ниже


@router.edited_message()
async def on_edited_message(message: Message, bot, db) -> None:
    """Правка старого сообщения не должна обходить тишину ночной фазы Мафии: чужой текст туда не втиснешь."""
    from loguru import logger
    try:
        await mafia.gate_message(db, bot, message)
    except Exception as exc:
        logger.warning(f"mafia gate (edit) failed: {exc}")


@router.message()
async def on_message(message: Message, bot, db) -> None:
    """Каждое сообщение: закрытый чат, учёт активности, затем команда."""
    from loguru import logger
    from services import feature_switches
    from core import official_updates as official_policy
    if (message.chat.id == official_policy.CHAT_ID and message.is_topic_message
            and message.message_thread_id == official_policy.THREAD_ID):
        try:
            from infrastructure.repositories import patch_notes as official_repo
            await official_repo.ensure_tables(db)
            await official_repo.topic_seen(db, official_policy.CHAT_ID, official_policy.THREAD_ID)
        except Exception as error:
            logger.warning("official topic observation failed: {}", type(error).__name__)
    chat_id = message.chat.id if message.chat.type in ("group", "supergroup") else None
    try:
        bot_off = await feature_switches.disabled(db, ["all"], chat_id) is not None
    except Exception as exc:
        logger.warning(f"feature switches unavailable: {exc}")
        bot_off = False
    if bot_off:   # весь бот выключен: только закрытый чат, учёт сообщений и «бот админка»
        try:
            if await purge.purge_gate(db, bot, message) or await moderation.closed_gate(db, bot, message):
                return
        except Exception as exc:
            logger.warning(f"closed-chat gate failed: {exc}")
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
        if message.chat.type == "private" and message.from_user:   # пишет боту — значит, не блокировал
            await db.execute("UPDATE users SET dm_blocked_at = NULL WHERE user_tg_id = ? AND dm_blocked_at IS NOT NULL",
                             (message.from_user.id,))
    except Exception as exc:  # учёт не должен ломать команды
        logger.warning(f"message tracking failed: {exc}")
    try:
        await mafia.after_message(db, bot, message)
    except Exception as exc:
        logger.warning(f"mafia lobby repost failed: {exc}")
    # Addressed word-game turns must win over bare actions such as «чай» and «торт».
    handled = False
    if message.chat.type in ("group", "supergroup") and word_chain.is_reply(bot, message):
        if not await _silent(message, db):
            handled = await word_chain.on_reply(db, bot, message)
    if not handled:
        handled = await dispatch(registry, message, bot, db)
    if not handled and message.chat.type == "private":   # «привет» в личке: не молчим, показываем, с чего начать
        try:
            if not await _silent(message, db):
                await onboarding.dm_hint(message, bot, db)
        except Exception as exc:
            logger.warning(f"dm hint failed: {exc}")
    await achievements.after_message(db, message)   # после ответа на команду, сам ловит ошибки
