"""Модерация чата: варны, мут, кик, бан, защита, иммунитет, закрытие чата.

Данные — в существующих таблицах: user_warnings, user_chat_stats (muted_until,
immune_until, is_immune), chat_blacklist, chat_settings (max_warnings, is_closed),
moderation_logs.
"""
from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.chat import ranks
from bot.chat.access import is_developer
from bot.chat.admin_chat import send_admin
from bot.chat.durations import FOREVER, human, split_duration
from bot.chat.framework import Ctx, UsageError, registry
from bot.chat.targets import Target, resolve_target

router = Router(name="chat_moderation")
TG_FAIL = "⚠️ Telegram не дал это сделать. Бот должен быть админом группы с правом блокировки участников."
NO_PERMS = ChatPermissions(
    can_send_messages=False, can_send_audios=False, can_send_documents=False, can_send_photos=False,
    can_send_videos=False, can_send_video_notes=False, can_send_voice_notes=False, can_send_polls=False,
    can_send_other_messages=False, can_add_web_page_previews=False,
)


def esc(s: str | None) -> str:
    return html.escape(s or "")


async def commit(db) -> None:
    c = getattr(db, "commit", None)
    if c:
        await c()


async def log(db, chat_id: int, user_id: int, admin_id: int, action: str, reason: str = "") -> None:
    await db.execute(
        "INSERT INTO moderation_logs (chat_id, user_id, admin_id, action, reason) VALUES (?, ?, ?, ?, ?)",
        (chat_id, user_id, admin_id, action, reason or None),
    )


def until(td: timedelta | None) -> datetime | None:
    return datetime.now(timezone.utc) + td if td else None


# ── Общая проверка перед санкцией ─────────────────────────────────────────

class Denied(Exception):
    pass


async def prepare(ctx: Ctx, action: str, usage: str, *, punish: bool = True) -> tuple[Target, str]:
    chat_id = ctx.message.chat.id
    await ranks.sync_owner(ctx.db, ctx.bot, chat_id)
    if not await ranks.can(ctx.db, chat_id, ctx.user_id, action):
        raise Denied(f"⛔ У вашего ранга нет права: {ranks.ACTION_BY_KEY[action].label.lower()}.")
    target, rest = await resolve_target(ctx.db, ctx.message, ctx.args, allow_id=ctx.is_dev)
    if target is None:
        raise UsageError(usage)
    me = await ctx.bot.me()
    if target.user_id == me.id:
        raise Denied("🙂 К самому боту это не применяется.")
    if punish:
        if is_developer(target.user_id):
            raise Denied("⛔ К разработчику бота нельзя применять санкции.")
        if target.user_id == ctx.user_id:
            raise Denied("⛔ Себя наказать нельзя.")
        if not ctx.is_dev:
            mine = await ranks.get_rank(ctx.db, chat_id, ctx.user_id)
            theirs = await ranks.get_rank(ctx.db, chat_id, target.user_id)
            if theirs >= mine:
                raise Denied("⛔ Нельзя применить санкцию к тому, чей ранг не ниже вашего.")
    return target, rest


def moderation_command(name: str, *, usage: str, summary: str, example: str = "", aliases: tuple = ()):
    """Регистрация команды модерации: отказ и ошибки Telegram — понятным текстом."""
    def deco(fn):
        async def wrapped(ctx: Ctx) -> None:
            try:
                await fn(ctx)
            except Denied as e:
                await ctx.reply(str(e))
            except (TelegramBadRequest, TelegramForbiddenError):
                await ctx.reply(TG_FAIL)
        registry.command(name, usage=usage, summary=summary, example=example or usage,
                         aliases=aliases, private=False, section="moderation")(wrapped)
        return fn
    return deco


def _parse_duration(rest: str, usage: str) -> tuple[timedelta | str | None, str]:
    try:
        return split_duration(rest)
    except ValueError as e:
        raise UsageError(f"{usage}\nНе понял срок «{e}». Примеры: 30м, 2ч, 5д, 1н, навсегда")


# ── Варны ─────────────────────────────────────────────────────────────────

async def active_warns(db, chat_id: int, user_id: int) -> list:
    async with db.execute(
        "SELECT id, reason, created_at, expires_at, admin_id FROM user_warnings "
        "WHERE chat_id = ? AND user_id = ? AND revoked_at IS NULL "
        "AND (expires_at IS NULL OR expires_at > NOW()) ORDER BY id",
        (chat_id, user_id),
    ) as cur:
        return await cur.fetchall()


async def warn_limit(db, chat_id: int) -> int:
    async with db.execute("SELECT max_warnings FROM chat_settings WHERE chat_id = ?", (chat_id,)) as cur:
        row = await cur.fetchone()
    return int(row[0]) if row and row[0] else 3


class WarnLimitCB(CallbackData, prefix="wl"):
    act: str      # forgive | mute | kick | ban
    chat: int
    user: int


def warn_limit_kb(chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    b = lambda text, act: InlineKeyboardButton(text=text, callback_data=WarnLimitCB(act=act, chat=chat_id, user=user_id).pack())
    return InlineKeyboardMarkup(inline_keyboard=[
        [b("🕊 Простить", "forgive"), b("🔇 Мут", "mute")],
        [b("👢 Кик", "kick"), b("⛔ Бан", "ban")],
    ])


@moderation_command(
    "варн", usage="бот варн, @ник [срок] [причина]", example="бот варн, @ник 7д флуд",
    summary="Предупреждение. Со сроком — сгорит само, без срока — пока не снимут.",
)
async def cmd_warn(ctx: Ctx) -> None:
    usage = "бот варн, @ник [срок] [причина]"
    target, rest = await prepare(ctx, "warn", usage)
    dur, reason = _parse_duration(rest, usage)
    chat_id = ctx.message.chat.id
    if isinstance(dur, timedelta):
        await ctx.db.execute(
            "INSERT INTO user_warnings (chat_id, user_id, admin_id, reason, expires_at) "
            "VALUES (?, ?, ?, ?, NOW() + (? * INTERVAL '1 second'))",
            (chat_id, target.user_id, ctx.user_id, reason or None, int(dur.total_seconds())),
        )
    else:
        await ctx.db.execute(
            "INSERT INTO user_warnings (chat_id, user_id, admin_id, reason) VALUES (?, ?, ?, ?)",
            (chat_id, target.user_id, ctx.user_id, reason or None),
        )
    await log(ctx.db, chat_id, target.user_id, ctx.user_id, "warn", reason)
    await commit(ctx.db)
    count, limit = len(await active_warns(ctx.db, chat_id, target.user_id)), await warn_limit(ctx.db, chat_id)
    kind = f"на {human(dur)}" if isinstance(dur, timedelta) else "бессрочный"
    text = f"⚠️ {esc(target.label())} получает варн ({count}/{limit}), {kind}."
    if reason:
        text += f"\nПричина: {esc(reason)}"
    await ctx.reply(text)
    if count >= limit:
        await send_admin(
            ctx.bot, ctx.db, chat_id,
            f"🚨 <b>Лимит варнов превышен</b>\n{esc(target.label())} — {count}/{limit} в «{esc(ctx.message.chat.title)}».\n"
            "Что сделать?",
            markup=warn_limit_kb(chat_id, target.user_id),
        )


@moderation_command("снять варн", usage="бот снять варн, @ник", summary="Снять последний действующий варн.")
async def cmd_unwarn(ctx: Ctx) -> None:
    target, _ = await prepare(ctx, "unwarn", "бот снять варн, @ник", punish=False)
    chat_id = ctx.message.chat.id
    warns = await active_warns(ctx.db, chat_id, target.user_id)
    if not warns:
        await ctx.reply(f"У {esc(target.label())} нет действующих варнов.")
        return
    await ctx.db.execute(
        "UPDATE user_warnings SET revoked_at = NOW(), revoked_by = ? WHERE id = ?", (ctx.user_id, warns[-1][0])
    )
    await log(ctx.db, chat_id, target.user_id, ctx.user_id, "unwarn")
    await commit(ctx.db)
    await ctx.reply(f"✅ С {esc(target.label())} снят варн. Осталось: {len(warns) - 1}.")


@moderation_command("снять варны", usage="бот снять варны, @ник", summary="Снять все действующие варны.")
async def cmd_unwarn_all(ctx: Ctx) -> None:
    target, _ = await prepare(ctx, "unwarn", "бот снять варны, @ник", punish=False)
    n = await revoke_all_warns(ctx.db, ctx.message.chat.id, target.user_id, ctx.user_id)
    await ctx.reply(f"✅ С {esc(target.label())} снято варнов: {n}.")


async def revoke_all_warns(db, chat_id: int, user_id: int, admin_id: int) -> int:
    warns = await active_warns(db, chat_id, user_id)
    if warns:
        await db.execute(
            "UPDATE user_warnings SET revoked_at = NOW(), revoked_by = ? WHERE chat_id = ? AND user_id = ? "
            "AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at > NOW())",
            (admin_id, chat_id, user_id),
        )
        await log(db, chat_id, user_id, admin_id, "unwarn_all")
        await commit(db)
    return len(warns)


@registry.command(
    "варны", usage="бот варны [@ник]", private=False, section="moderation",
    summary="Действующие варны игрока (без ника — свои).",
)
async def cmd_warns(ctx: Ctx) -> None:
    chat_id = ctx.message.chat.id
    target, _ = await resolve_target(ctx.db, ctx.message, ctx.args)
    uid = target.user_id if target else ctx.user_id
    label = target.label() if target else "У вас"
    warns = await active_warns(ctx.db, chat_id, uid)
    limit = await warn_limit(ctx.db, chat_id)
    if not warns:
        await ctx.reply(f"{esc(label)}: действующих варнов нет. Лимит чата: {limit}.")
        return
    lines = [f"⚠️ <b>Варны</b> {esc(label)}: {len(warns)}/{limit}"]
    for i, (_, reason, created, expires, _) in enumerate(warns, 1):
        when = created.strftime("%d.%m") if created else ""
        till = f"до {expires.strftime('%d.%m %H:%M')}" if expires else "бессрочный"
        lines.append(f"{i}. {when} · {till}" + (f"\n   {esc(reason)}" if reason else ""))
    await ctx.reply("\n".join(lines))


@registry.command(
    "лимит варнов", usage="бот лимит варнов, 5", private=False, section="moderation",
    summary="Сколько варнов можно набрать, прежде чем бот позовёт админов.",
)
async def cmd_warn_limit(ctx: Ctx) -> None:
    chat_id = ctx.message.chat.id
    value = ctx.args.strip()
    if not value:
        await ctx.reply(f"Лимит варнов в этом чате: <b>{await warn_limit(ctx.db, chat_id)}</b>.")
        return
    if not value.isdigit() or not 1 <= int(value) <= 50:
        raise UsageError("бот лимит варнов, 5   (число от 1 до 50)")
    if not await ranks.can(ctx.db, chat_id, ctx.user_id, "warn_limit"):
        await ctx.reply("⛔ У вашего ранга нет права менять лимит варнов.")
        return
    await ctx.db.execute(
        "INSERT INTO chat_settings (chat_id, max_warnings) VALUES (?, ?) "
        "ON CONFLICT (chat_id) DO UPDATE SET max_warnings = EXCLUDED.max_warnings",
        (chat_id, int(value)),
    )
    await commit(ctx.db)
    await ctx.reply(f"✅ Лимит варнов: <b>{value}</b>.")


# ── Мут ───────────────────────────────────────────────────────────────────

async def do_mute(bot: Bot, db, chat_id: int, user_id: int, admin_id: int, dur, reason: str = "") -> None:
    td = dur if isinstance(dur, timedelta) else None
    await bot.restrict_chat_member(chat_id, user_id, permissions=NO_PERMS, until_date=until(td))
    if td:
        await db.execute(
            "UPDATE user_chat_stats SET muted_until = NOW() + (? * INTERVAL '1 second') "
            "WHERE chat_tg_id = ? AND user_tg_id = ?", (int(td.total_seconds()), chat_id, user_id))
    else:
        await db.execute(
            "UPDATE user_chat_stats SET muted_until = 'infinity' WHERE chat_tg_id = ? AND user_tg_id = ?",
            (chat_id, user_id))
    await log(db, chat_id, user_id, admin_id, "mute", reason)
    await commit(db)


@moderation_command(
    "мут", usage="бот мут, @ник срок [причина]", example="бот мут, @ник 2ч спам",
    summary="Запретить писать на время (или навсегда).",
)
async def cmd_mute(ctx: Ctx) -> None:
    usage = "бот мут, @ник срок [причина]"
    target, rest = await prepare(ctx, "mute", usage)
    dur, reason = _parse_duration(rest, usage)
    if dur is None:
        raise UsageError(usage + "\nСрок обязателен: 30м, 2ч, 5д или навсегда")
    await do_mute(ctx.bot, ctx.db, ctx.message.chat.id, target.user_id, ctx.user_id, dur, reason)
    text = f"🔇 {esc(target.label())} не может писать {('на ' + human(dur)) if dur != FOREVER else 'бессрочно'}."
    await ctx.reply(text + (f"\nПричина: {esc(reason)}" if reason else ""))


@moderation_command("снять мут", aliases=("размут",), usage="бот снять мут, @ник", summary="Вернуть право писать.")
async def cmd_unmute(ctx: Ctx) -> None:
    target, _ = await prepare(ctx, "unmute", "бот снять мут, @ник", punish=False)
    chat_id = ctx.message.chat.id
    chat = await ctx.bot.get_chat(chat_id)
    perms = chat.permissions or ChatPermissions(can_send_messages=True)
    await ctx.bot.restrict_chat_member(chat_id, target.user_id, permissions=perms)
    await ctx.db.execute(
        "UPDATE user_chat_stats SET muted_until = NULL WHERE chat_tg_id = ? AND user_tg_id = ?",
        (chat_id, target.user_id))
    await log(ctx.db, chat_id, target.user_id, ctx.user_id, "unmute")
    await commit(ctx.db)
    await ctx.reply(f"🔊 {esc(target.label())} снова может писать.")


# ── Кик и бан ─────────────────────────────────────────────────────────────

async def do_kick(bot: Bot, db, chat_id: int, user_id: int, admin_id: int, reason: str = "") -> None:
    await bot.ban_chat_member(chat_id, user_id)
    await bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
    await db.execute(
        "UPDATE user_chat_stats SET is_left = TRUE WHERE chat_tg_id = ? AND user_tg_id = ?", (chat_id, user_id))
    await log(db, chat_id, user_id, admin_id, "kick", reason)
    await commit(db)


async def do_ban(bot: Bot, db, chat_id: int, user_id: int, admin_id: int, dur, reason: str = "") -> None:
    td = dur if isinstance(dur, timedelta) else None
    await bot.ban_chat_member(chat_id, user_id, until_date=until(td))
    if td:
        await db.execute(
            "INSERT INTO chat_blacklist (chat_id, user_id, reason, added_by, expires_at) "
            "VALUES (?, ?, ?, ?, NOW() + (? * INTERVAL '1 second')) ON CONFLICT (chat_id, user_id) DO UPDATE SET "
            "reason = EXCLUDED.reason, added_by = EXCLUDED.added_by, added_at = NOW(), expires_at = EXCLUDED.expires_at",
            (chat_id, user_id, reason or None, admin_id, int(td.total_seconds())))
    else:
        await db.execute(
            "INSERT INTO chat_blacklist (chat_id, user_id, reason, added_by, expires_at) VALUES (?, ?, ?, ?, NULL) "
            "ON CONFLICT (chat_id, user_id) DO UPDATE SET reason = EXCLUDED.reason, added_by = EXCLUDED.added_by, "
            "added_at = NOW(), expires_at = NULL",
            (chat_id, user_id, reason or None, admin_id))
    await db.execute(
        "UPDATE user_chat_stats SET is_left = TRUE WHERE chat_tg_id = ? AND user_tg_id = ?", (chat_id, user_id))
    await log(db, chat_id, user_id, admin_id, "ban", reason)
    await commit(db)


async def is_blacklisted(db, chat_id: int, user_id: int) -> bool:
    async with db.execute(
        "SELECT 1 FROM chat_blacklist WHERE chat_id = ? AND user_id = ? "
        "AND (expires_at IS NULL OR expires_at > NOW())", (chat_id, user_id)) as cur:
        return await cur.fetchone() is not None


@moderation_command(
    "кик", usage="бот кик, @ник [причина]",
    summary="Удалить из группы. Вернуться можно по ссылке.",
)
async def cmd_kick(ctx: Ctx) -> None:
    target, reason = await prepare(ctx, "kick", "бот кик, @ник [причина]")
    await do_kick(ctx.bot, ctx.db, ctx.message.chat.id, target.user_id, ctx.user_id, reason)
    await ctx.reply(f"👢 {esc(target.label())} удалён из чата." + (f"\nПричина: {esc(reason)}" if reason else ""))


@moderation_command(
    "бан", usage="бот бан, @ник [срок] [причина]", example="бот бан, @ник 5д",
    summary="Удалить и внести в чёрный список: при входе бот сразу выгонит.",
)
async def cmd_ban(ctx: Ctx) -> None:
    usage = "бот бан, @ник [срок] [причина]"
    target, rest = await prepare(ctx, "ban", usage)
    dur, reason = _parse_duration(rest, usage)
    await do_ban(ctx.bot, ctx.db, ctx.message.chat.id, target.user_id, ctx.user_id, dur, reason)
    term = f"на {human(dur)}" if isinstance(dur, timedelta) else "навсегда"
    await ctx.reply(f"⛔ {esc(target.label())} забанен {term}." + (f"\nПричина: {esc(reason)}" if reason else ""))


@moderation_command("снять бан", aliases=("разбан",), usage="бот снять бан, @ник",
                    summary="Убрать из чёрного списка, вход снова открыт.")
async def cmd_unban(ctx: Ctx) -> None:
    target, _ = await prepare(ctx, "unban", "бот снять бан, @ник", punish=False)
    await do_unban(ctx.bot, ctx.db, ctx.message.chat.id, target.user_id, ctx.user_id)
    await ctx.reply(f"✅ {esc(target.label())} разбанен и может вернуться в чат.")


async def do_unban(bot: Bot, db, chat_id: int, user_id: int, admin_id: int) -> None:
    await bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
    await db.execute("DELETE FROM chat_blacklist WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    await log(db, chat_id, user_id, admin_id, "unban")
    await commit(db)


# ── Защита и иммунитет (от чистки) ────────────────────────────────────────

@moderation_command(
    "защита", usage="бот защита, @ник срок", example="бот защита, @ник 5д",
    summary="Защита от чистки на время.",
)
async def cmd_shield(ctx: Ctx) -> None:
    usage = "бот защита, @ник срок"
    target, rest = await prepare(ctx, "shield", usage, punish=False)
    dur, _ = _parse_duration(rest, usage)
    if not isinstance(dur, timedelta):
        raise UsageError(usage + "\nНужен срок: 2ч, 5д, 1н. Навсегда — это «бот иммунитет».")
    chat_id = ctx.message.chat.id
    await ctx.db.execute(
        "INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, immune_until) VALUES (?, ?, NOW() + (? * INTERVAL '1 second')) "
        "ON CONFLICT (user_tg_id, chat_tg_id) DO UPDATE SET immune_until = EXCLUDED.immune_until",
        (target.user_id, chat_id, int(dur.total_seconds())))
    await log(ctx.db, chat_id, target.user_id, ctx.user_id, "shield", human(dur))
    await commit(ctx.db)
    await ctx.reply(f"🛡 {esc(target.label())} защищён от чистки на {human(dur)}.")


@moderation_command("снять защиту", usage="бот снять защиту, @ник", summary="Убрать защиту от чистки.")
async def cmd_unshield(ctx: Ctx) -> None:
    target, _ = await prepare(ctx, "shield", "бот снять защиту, @ник", punish=False)
    await _set_flag(ctx, target, "immune_until = NULL", "unshield")
    await ctx.reply(f"✅ С {esc(target.label())} снята защита.")


@moderation_command("иммунитет", usage="бот иммунитет, @ник", summary="Защита от чистки навсегда, пока не снимут.")
async def cmd_immune(ctx: Ctx) -> None:
    target, _ = await prepare(ctx, "immune", "бот иммунитет, @ник", punish=False)
    await _set_flag(ctx, target, "is_immune = TRUE", "immune")
    await ctx.reply(f"💠 {esc(target.label())} получает иммунитет к чистке.")


@moderation_command("снять иммунитет", usage="бот снять иммунитет, @ник", summary="Убрать иммунитет.")
async def cmd_unimmune(ctx: Ctx) -> None:
    target, _ = await prepare(ctx, "immune", "бот снять иммунитет, @ник", punish=False)
    await _set_flag(ctx, target, "is_immune = FALSE", "unimmune")
    await ctx.reply(f"✅ С {esc(target.label())} снят иммунитет.")


async def _set_flag(ctx: Ctx, target: Target, assignment: str, action: str) -> None:
    chat_id = ctx.message.chat.id
    await ctx.db.execute(
        "INSERT INTO user_chat_stats (user_tg_id, chat_tg_id) VALUES (?, ?) ON CONFLICT DO NOTHING",
        (target.user_id, chat_id))
    await ctx.db.execute(
        f"UPDATE user_chat_stats SET {assignment} WHERE chat_tg_id = ? AND user_tg_id = ?", (chat_id, target.user_id))
    await log(ctx.db, chat_id, target.user_id, ctx.user_id, action)
    await commit(ctx.db)


# ── Закрытый чат ──────────────────────────────────────────────────────────

async def set_closed(ctx: Ctx, closed: bool) -> None:
    chat_id = ctx.message.chat.id
    await ranks.sync_owner(ctx.db, ctx.bot, chat_id)
    if not await ranks.can(ctx.db, chat_id, ctx.user_id, "close_chat"):
        if not ctx.prefixed:
            return   # «+чат» без «бот» от обычного участника — просто сообщение
        await ctx.reply("⛔ У вашего ранга нет права закрывать и открывать чат.")
        return
    await ctx.db.execute(
        "INSERT INTO chat_settings (chat_id, is_closed) VALUES (?, ?) "
        "ON CONFLICT (chat_id) DO UPDATE SET is_closed = EXCLUDED.is_closed", (chat_id, closed))
    await log(ctx.db, chat_id, 0, ctx.user_id, "close_chat" if closed else "open_chat")
    await commit(ctx.db)
    await ctx.reply("🔒 Чат закрыт. Писать могут только те, кому это разрешено рангом."
                    if closed else "🔓 Чат открыт, пишут все.")


@registry.command("закрыть чат", aliases=("-чат",), bare=True, private=False, section="moderation",
                  usage="бот закрыть чат  (или просто -чат)", summary="Писать смогут только ранги с правом.")
async def cmd_close(ctx: Ctx) -> None:
    await set_closed(ctx, True)


@registry.command("открыть чат", aliases=("+чат",), bare=True, private=False, section="moderation",
                  usage="бот открыть чат  (или просто +чат)", summary="Снова пишут все.")
async def cmd_open(ctx: Ctx) -> None:
    await set_closed(ctx, False)


async def closed_gate(db, bot: Bot, message: Message) -> bool:
    """Закрытый чат: удалить сообщение того, кому писать нельзя. True — удалено."""
    if message.chat.type not in ("group", "supergroup") or not message.from_user or message.from_user.is_bot:
        return False
    async with db.execute("SELECT is_closed FROM chat_settings WHERE chat_id = ?", (message.chat.id,)) as cur:
        row = await cur.fetchone()
    if not row or not row[0]:
        return False
    if await ranks.can(db, message.chat.id, message.from_user.id, "write_closed"):
        return False
    try:
        await message.delete()
    except Exception:
        return False
    return True


# ── Кнопки под сообщением «лимит варнов» ──────────────────────────────────

@router.callback_query(WarnLimitCB.filter())
async def on_warn_limit(call: CallbackQuery, callback_data: WarnLimitCB, bot: Bot, db) -> None:
    cb, actor = callback_data, call.from_user.id
    need = {"forgive": "unwarn", "mute": "mute", "kick": "kick", "ban": "ban"}[cb.act]
    if not await ranks.can(db, cb.chat, actor, need):
        await call.answer("У вашего ранга нет на это права.", show_alert=True)
        return
    if cb.act != "forgive" and is_developer(cb.user):
        await call.answer("К разработчику бота санкции не применяются.", show_alert=True)
        return
    async with db.execute("SELECT user_tg_username FROM users WHERE user_tg_id = ?", (cb.user,)) as cur:
        row = await cur.fetchone()
    who = f"@{row[0]}" if row and row[0] else f"id{cb.user}"
    try:
        if cb.act == "forgive":
            await revoke_all_warns(db, cb.chat, cb.user, actor)
            result = f"🕊 Прощён: варны сняты ({esc(call.from_user.full_name)})"
        elif cb.act == "mute":
            await call.message.answer(
                "Скопируйте и укажите срок:\n"
                f"<code>бот мут, {esc(who)} 1ч</code>", parse_mode="HTML")
            await call.answer()
            return
        elif cb.act == "kick":
            await do_kick(bot, db, cb.chat, cb.user, actor, "лимит варнов")
            result = f"👢 Кикнут ({esc(call.from_user.full_name)})"
        else:
            await do_ban(bot, db, cb.chat, cb.user, actor, FOREVER, "лимит варнов")
            result = f"⛔ Забанен ({esc(call.from_user.full_name)})"
    except (TelegramBadRequest, TelegramForbiddenError):
        await call.answer(TG_FAIL, show_alert=True)
        return
    try:
        await call.message.edit_text(f"{call.message.html_text}\n\n<b>{result}</b>", parse_mode="HTML")
    except Exception:
        pass
    await call.answer("Готово")
