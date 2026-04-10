"""
Репутация, уровни XP и биография пользователя.
"""
import html as _html

from aiogram import Router
from aiogram.types import Message

from config import BIO_MAX_LENGTH, REP_DAILY_LIMIT, REP_MORA_REWARD_FROM, REP_MORA_REWARD_TO, REP_PLUS_TRIGGERS, TOP_LIMIT
from database.db import (
    add_mora, add_reputation_in_chat, get_rep_count_today,
    get_top_by_xp_in_chat, get_top_reputation_in_chat,
    get_user_stats, xp_for_level,
)
from filters.bot_command import BotCommand
from utils.helpers import resolve_target, user_mention

from filters.chat_mode import MainChatOnly
import logging
_log = logging.getLogger(__name__)
router = Router()
router.message.filter(MainChatOnly())


# Триггеры для выдачи репутации (+)
_PLUS_TRIGGERS = REP_PLUS_TRIGGERS


# ─── Авто-репутация через "+" / "-" ответом ───────────────────────────────────

@router.message(
    lambda m: (
        m.text
        and m.text.strip().lower() in _PLUS_TRIGGERS
        and m.reply_to_message
        and m.reply_to_message.from_user
        and m.chat.type in ("group", "supergroup")
    )
)
async def handle_rep_plus(message: Message):
    target = message.reply_to_message.from_user

    if target.id == message.from_user.id:
        await message.reply("❌ Нельзя повышать репутацию самому себе.")
        return
    if target.is_bot:
        return

    count_today = await get_rep_count_today(message.from_user.id, target.id, message.chat.id)
    if count_today >= REP_DAILY_LIMIT:
        await message.reply(
            f"⏳ Достигнут дневной лимит репутации для этого пользователя "
            f"(<b>{count_today}/{REP_DAILY_LIMIT}</b>). Сбросится в полночь UTC.",
            parse_mode="HTML",
        )
        return

    new_rep = await add_reputation_in_chat(message.from_user.id, target.id, message.chat.id, 1)
    count_today += 1
    await message.reply(
        f"⬆️ {user_mention(target.id, target.full_name)} получил +1 репутацию! "
        f"Теперь: <b>{new_rep:+d}</b>  "
        f"<i>({count_today}/{REP_DAILY_LIMIT} сегодня)</i>",
        parse_mode="HTML",
    )

    # Мора: +N получившему, +N давшему
    await add_mora(target.id, message.chat.id, REP_MORA_REWARD_TO)
    await add_mora(message.from_user.id, message.chat.id, REP_MORA_REWARD_FROM)

    # Quest progress ("rep" type)
    from database.db import get_user_quest, quest_tick, mark_quest_rewarded, add_xp_in_chat
    from utils.helpers import bot_today
    today = bot_today()
    quest = await get_user_quest(message.from_user.id, message.chat.id, today)
    if quest["type"] == "rep":
        new_p, goal, just_done = await quest_tick(
            message.from_user.id, message.chat.id, today, quest["type"], quest["goal"],
        )
        if just_done:
            _mora_reward = quest.get("mora", 5)
            await add_xp_in_chat(message.from_user.id, message.chat.id, quest["xp"])
            await add_mora(message.from_user.id, message.chat.id, _mora_reward)
            await mark_quest_rewarded(message.from_user.id, message.chat.id, today)
            try:
                await message.answer(
                    f"🎉 {user_mention(message.from_user.id, message.from_user.full_name)} "
                    f"выполнил ежедневное задание! <b>+{quest['xp']} XP</b>  <b>+{_mora_reward} Моры</b> 🪙",
                    parse_mode="HTML",
                )
            except Exception as _e:
                _log.debug("%s", _e)
# ─── Команды репутации ────────────────────────────────────────────────────────

@router.message(BotCommand("репутация", "репа", "rep"))
async def cmd_rep(message: Message, cmd_args: str):
    uid, name, _ = await resolve_target(message, cmd_args)
    if uid is None:
        uid = message.from_user.id
        name = message.from_user.full_name

    stats = await get_user_stats(uid, message.chat.id)
    if not stats:
        await message.answer(
            "❌ Пользователь не найден.\n"
            "ℹ️ Ответь на сообщение или укажи: <code>бот репутация @username</code>",
            parse_mode="HTML",
        )
        return

    await message.answer(
        f"⭐ <b>Репутация</b> {user_mention(uid, name)}: <b>{(stats['reputation'] or 0):+d}</b>",
        parse_mode="HTML",
    )


@router.message(BotCommand("топ репутация", "топреп", "toprep"))
async def cmd_top_rep(message: Message, cmd_args: str):
    top = await get_top_reputation_in_chat(message.chat.id, TOP_LIMIT)
    if not top:
        await message.answer("📊 Рейтинг репутации пуст.")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 <b>Топ репутации:</b>\n"]
    for i, u in enumerate(top):
        place = medals[i] if i < 3 else f"{i + 1}."
        rep = u["reputation"] or 0
        lines.append(f"{place} {_html.escape(u['full_name'])} — <b>{rep:+d}</b>")

    await message.answer("\n".join(lines), parse_mode="HTML")


# ─── Уровень ──────────────────────────────────────────────────────────────────

@router.message(BotCommand("уровень", "level", "xp"))
async def cmd_level(message: Message, cmd_args: str):
    uid, name, _ = await resolve_target(message, cmd_args)
    if uid is None:
        uid = message.from_user.id
        name = message.from_user.full_name

    stats = await get_user_stats(uid, message.chat.id)
    if not stats:
        await message.answer(
            "❌ Пользователь не найден.\n"
            "ℹ️ Ответь на сообщение или укажи: <code>бот уровень @username</code>",
            parse_mode="HTML",
        )
        return

    xp = stats["xp"] or 0
    lvl = stats["level"] or 1
    next_lvl_xp = xp_for_level(lvl + 1)
    bar_filled = min(10, int((xp - xp_for_level(lvl)) / max(1, next_lvl_xp - xp_for_level(lvl)) * 10))
    bar = "█" * bar_filled + "░" * (10 - bar_filled)

    await message.answer(
        f"🌟 <b>Уровень</b> {user_mention(uid, name)}\n\n"
        f"📊 Уровень: <b>{lvl}</b>\n"
        f"✨ XP: <b>{xp}</b> / {next_lvl_xp}\n"
        f"[{bar}]",
        parse_mode="HTML",
    )


@router.message(BotCommand("топ уровень", "топуровень", "toplevel"))
async def cmd_top_level(message: Message, cmd_args: str):
    top_xp = await get_top_by_xp_in_chat(message.chat.id, TOP_LIMIT)

    if not top_xp:
        await message.answer("📊 Нет данных.")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = ["🌟 <b>Топ по уровням:</b>\n"]
    for i, u in enumerate(top_xp):
        place = medals[i] if i < 3 else f"{i + 1}."
        lines.append(f"{place} {_html.escape(u['full_name'])} — ур. {u['level'] or 1} ({u['xp'] or 0} XP)")

    await message.answer("\n".join(lines), parse_mode="HTML")


# ─── Биография ────────────────────────────────────────────────────────────────

@router.message(BotCommand("обо мне", "биография", "bio"))
async def cmd_bio(message: Message, cmd_args: str):
    if cmd_args.lower() in ("удалить", "убрать", "del", "delete", "clear"):
        await set_bio_in_chat(message.from_user.id, message.chat.id, None)
        await message.answer("✅ Биография удалена.")
    elif cmd_args:
        if len(cmd_args) > BIO_MAX_LENGTH:
            await message.answer(f"❌ Биография не может быть длиннее {BIO_MAX_LENGTH} символов.")
            return
        await set_bio_in_chat(message.from_user.id, message.chat.id, cmd_args)
        import html as _html
        await message.answer(f"✅ Биография установлена:\n<i>{_html.escape(cmd_args)}</i>", parse_mode="HTML")
    else:
        await message.answer(
            "❌ Укажи текст или <code>удалить</code>.\n"
            "Пример: <code>бот обо мне Привет всем, я новый участник!</code>",
            parse_mode="HTML",
        )
