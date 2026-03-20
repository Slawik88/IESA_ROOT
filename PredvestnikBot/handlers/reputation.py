"""
Репутация, уровни XP и биография пользователя.
"""
import html as _html
from datetime import datetime, timedelta

from aiogram import Router
from aiogram.types import Message

from config import BIO_MAX_LENGTH, REP_PLUS_TRIGGERS, TOP_LIMIT
from database.db import (
    add_reputation_in_chat, can_give_rep, get_rep_last_time,
    get_top_by_xp_in_chat, get_top_reputation_in_chat, get_user,
    get_user_stats, set_bio_in_chat, level_for_xp, xp_for_level,
)
from filters.bot_command import BotCommand
from utils.helpers import resolve_target, user_mention
from utils.ranks import rank_name

router = Router()

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

    ok = await can_give_rep(message.from_user.id, target.id, message.chat.id)
    if not ok:
        last = await get_rep_last_time(message.from_user.id, target.id, message.chat.id)
        if last:
            try:
                last_dt = datetime.fromisoformat(last)
                next_dt = last_dt + timedelta(hours=24)
                now = datetime.utcnow()
                remaining = next_dt - now
                if remaining.total_seconds() > 0:
                    hours = int(remaining.total_seconds() // 3600)
                    minutes = int((remaining.total_seconds() % 3600) // 60)
                    await message.reply(f"⏳ Ты уже давал репутацию этому пользователю. Следующая через {hours}ч {minutes}м.")
                    return
            except (ValueError, TypeError):
                pass
        await message.reply("⏳ Ты уже давал репутацию этому пользователю сегодня.")
        return

    new_rep = await add_reputation_in_chat(message.from_user.id, target.id, message.chat.id, 1)
    await message.reply(
        f"⬆️ {user_mention(target.id, target.full_name)} получил +1 репутацию! "
        f"Теперь: <b>{new_rep:+d}</b>",
        parse_mode="HTML",
    )

    # Quest progress ("rep" type)
    from database.db import get_todays_quest, quest_tick, mark_quest_rewarded, add_xp_in_chat
    quest = get_todays_quest()
    if quest["type"] == "rep":
        from datetime import date
        today = date.today().isoformat()
        new_p, goal, just_done = await quest_tick(
            message.from_user.id, message.chat.id, today, quest["type"], quest["goal"],
        )
        if just_done:
            await add_xp_in_chat(message.from_user.id, message.chat.id, quest["xp"])
            await mark_quest_rewarded(message.from_user.id, message.chat.id, today)
            try:
                await message.answer(
                    f"🎉 {user_mention(message.from_user.id, message.from_user.full_name)} "
                    f"выполнил ежедневное задание! <b>+{quest['xp']} XP</b>",
                    parse_mode="HTML",
                )
            except Exception:
                pass


# ─── Команды репутации ────────────────────────────────────────────────────────

@router.message(BotCommand("репа", "репутация", "rep"))
async def cmd_rep(message: Message, cmd_args: str):
    uid, name, _ = await resolve_target(message, cmd_args)
    if uid is None:
        uid = message.from_user.id
        name = message.from_user.full_name

    stats = await get_user_stats(uid, message.chat.id)
    if not stats:
        await message.answer(
            "❌ Пользователь не найден.\n"
            "ℹ️ Ответь на сообщение или укажи: <code>бот репа @username</code>",
            parse_mode="HTML",
        )
        return

    await message.answer(
        f"⭐ <b>Репутация</b> {user_mention(uid, name)}: <b>{(stats['reputation'] or 0):+d}</b>",
        parse_mode="HTML",
    )


@router.message(BotCommand("топреп", "toprep", "репутациятоп"))
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


@router.message(BotCommand("топуровень", "toplevel", "топxp"))
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

@router.message(BotCommand("биография", "bio", "обомне"))
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
            "❌ Укажи текст биографии или <code>удалить</code>.\n"
            "Пример: <code>бот биография Привет всем, я новый участник!</code>",
            parse_mode="HTML",
        )
