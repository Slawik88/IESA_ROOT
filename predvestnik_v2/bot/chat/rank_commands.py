"""Команды рангов: «бот ранг», «бот снять ранг», «бот ранги», «бот права».
Плюс синхронизация владельца чата с Telegram."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.chat import ranks
from bot.chat.framework import Ctx, UsageError, registry
from bot.chat.targets import resolve_target

router = Router(name="chat_ranks")


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@registry.command(
    "ранг", usage="бот ранг, @ник [ранг]", private=False, section="moderation",
    summary="Показать или выдать ранг. Ранг — номер 0–8 или название.",
    example="бот ранг, @ник модератор",
)
async def cmd_rank(ctx: Ctx) -> None:
    chat_id = ctx.message.chat.id
    await ranks.sync_owner(ctx.db, ctx.bot, chat_id)
    target, rest = await resolve_target(ctx.db, ctx.message, ctx.args, allow_id=ctx.is_dev)
    if target is None:
        if rest.strip():
            raise UsageError("бот ранг, @ник [ранг]")
        own = await ranks.get_rank(ctx.db, chat_id, ctx.user_id)
        await ctx.reply(f"Ваш ранг в этом чате: <b>{ranks.rank_name(own)}</b>")
        return
    target_rank = await ranks.get_rank(ctx.db, chat_id, target.user_id)
    if not rest.strip():
        await ctx.reply(f"{_esc(target.label())}: <b>{ranks.rank_name(target_rank)}</b>")
        return
    new_rank = ranks.find_rank(rest)
    if new_rank is None:
        names = ", ".join(f"{i} {n}" for i, (_, n) in enumerate(ranks.RANKS[:-1]))
        await ctx.reply(f"🤔 Не знаю ранг «{_esc(rest)}».\nДоступные: {names}")
        return
    await _assign(ctx, target, target_rank, new_rank)


@registry.command(
    "снять ранг", usage="бот снять ранг, @ник", private=False, section="moderation",
    summary="Вернуть игроку ранг «Участник».",
)
async def cmd_rank_reset(ctx: Ctx) -> None:
    await ranks.sync_owner(ctx.db, ctx.bot, ctx.message.chat.id)
    target, _ = await resolve_target(ctx.db, ctx.message, ctx.args, allow_id=ctx.is_dev)
    if target is None:
        raise UsageError("бот снять ранг, @ник")
    target_rank = await ranks.get_rank(ctx.db, ctx.message.chat.id, target.user_id)
    await _assign(ctx, target, target_rank, 0)


async def _assign(ctx: Ctx, target, target_rank: int, new_rank: int) -> None:
    chat_id = ctx.message.chat.id
    if not await ranks.can(ctx.db, chat_id, ctx.user_id, "set_rank"):
        await ctx.reply("⛔ У вашего ранга нет права выдавать ранги.")
        return
    if ranks.is_developer(target.user_id) and not ctx.is_dev:
        await ctx.reply("⛔ Ранг разработчика бота изменить нельзя.")
        return
    actor_rank = await ranks.get_rank(ctx.db, chat_id, ctx.user_id)
    reason = ranks.check_assign(actor_rank, target_rank, new_rank)
    if reason:
        await ctx.reply(f"⛔ {reason}")
        return
    await ranks.store_rank(ctx.db, chat_id, target.user_id, new_rank)
    await ctx.reply(
        f"✅ {_esc(target.label())}: {ranks.rank_name(target_rank)} → <b>{ranks.rank_name(new_rank)}</b>"
    )


@registry.command(
    "ранги", aliases=("состав", "админы"), usage="бот ранги", private=False, section="moderation",
    summary="Кто в этом чате с каким рангом.",
)
async def cmd_ranks(ctx: Ctx) -> None:
    chat_id = ctx.message.chat.id
    owner = await ranks.sync_owner(ctx.db, ctx.bot, chat_id)
    async with ctx.db.execute(
        "SELECT s.user_tg_id, u.user_tg_username, s.chat_rank "
        "FROM user_chat_stats s LEFT JOIN users u ON u.user_tg_id = s.user_tg_id "
        "WHERE s.chat_tg_id = ? AND s.is_left = FALSE "
        "AND COALESCE(s.chat_rank, 0) > 0",
        (chat_id,),
    ) as cur:
        rows = await cur.fetchall()
    groups: dict[int, list[str]] = {}
    names: dict[int, str] = {}
    for uid, uname, cr in rows:
        rank = int(cr or 0)
        label = f"@​{uname}" if uname else f"id{uid}"
        names[int(uid)] = label
        if int(uid) != owner and rank > 0:
            groups.setdefault(min(rank, ranks.OWNER - 1), []).append(label)
    lines = ["🏛 <b>Состав чата</b>"]
    if owner:
        owner_label = names.get(owner)
        if owner_label is None:
            async with ctx.db.execute("SELECT user_tg_username FROM users WHERE user_tg_id = ?", (owner,)) as cur:
                r = await cur.fetchone()
            owner_label = f"@​{r[0]}" if r and r[0] else f"id{owner}"
        lines.append(f"\n{ranks.rank_name(ranks.OWNER)}\n{_esc(owner_label)}")
    for rank in sorted(groups, reverse=True):
        lines.append(f"\n{ranks.rank_name(rank)}\n" + "\n".join(_esc(n) for n in sorted(groups[rank], key=str.lower)))
    if len(lines) == 1:
        lines.append("\nРангов пока ни у кого нет.")
    await ctx.reply("\n".join(lines))


# ── «бот права»: пороги рангов по действиям ───────────────────────────────

class RightsCB(CallbackData, prefix="rights"):
    uid: int
    chat: int
    act: str
    val: int   # -1 — экран выбора ранга, -2 — главный экран


async def _rights_main(db, uid: int, chat: int) -> tuple[str, InlineKeyboardMarkup]:
    rmap = await ranks.rights_map(db, chat)
    lines = ["⚙️ <b>Права рангов</b>", "Действие доступно с указанного ранга и выше.\n"]
    for a in ranks.ACTIONS:
        lines.append(f"• {a.label}: <b>{ranks.rank_name(rmap[a.key])}</b>")
    buttons = [
        InlineKeyboardButton(text=a.label, callback_data=RightsCB(uid=uid, chat=chat, act=a.key, val=-1).pack())
        for a in ranks.ACTIONS
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def _rights_choose(uid: int, chat: int, act: str, current: int) -> tuple[str, InlineKeyboardMarkup]:
    a = ranks.ACTION_BY_KEY[act]
    buttons = [
        InlineKeyboardButton(
            text=("✅ " if i == current else "") + ranks.rank_name(i),
            callback_data=RightsCB(uid=uid, chat=chat, act=act, val=i).pack(),
        )
        for i in range(len(ranks.RANKS))
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=RightsCB(uid=uid, chat=chat, act="", val=-2).pack())])
    return f"⚙️ <b>{a.label}</b>\nС какого ранга разрешить?", InlineKeyboardMarkup(inline_keyboard=rows)


@registry.command(
    "права", usage="бот права", private=False, section="settings",
    summary="Настроить, с какого ранга доступно каждое действие.",
)
async def cmd_rights(ctx: Ctx) -> None:
    chat_id = ctx.message.chat.id
    await ranks.sync_owner(ctx.db, ctx.bot, chat_id)
    if not await ranks.can(ctx.db, chat_id, ctx.user_id, "rights"):
        await ctx.reply("⛔ Менять права рангов может только владелец чата (или ранг, которому он это разрешил).")
        return
    text, kb = await _rights_main(ctx.db, ctx.user_id, chat_id)
    await ctx.reply(text, reply_markup=kb)


@router.callback_query(RightsCB.filter())
async def on_rights(call: CallbackQuery, callback_data: RightsCB, db) -> None:
    cb = callback_data
    if call.from_user.id != cb.uid:
        await call.answer("Это меню другого игрока.", show_alert=True)
        return
    if not await ranks.can(db, cb.chat, cb.uid, "rights"):
        await call.answer("Нет права менять права рангов.", show_alert=True)
        return
    if cb.val == -2 or cb.act not in ranks.ACTION_BY_KEY:
        text, kb = await _rights_main(db, cb.uid, cb.chat)
    elif cb.val == -1:
        current = (await ranks.rights_map(db, cb.chat))[cb.act]
        text, kb = _rights_choose(cb.uid, cb.chat, cb.act, current)
    else:
        val = max(0, min(cb.val, ranks.OWNER))
        if cb.act == "rights" and val < ranks.OWNER and not ranks.is_developer(cb.uid) \
                and await ranks.get_rank(db, cb.chat, cb.uid) < ranks.OWNER:
            await call.answer("Передать право настройки может только владелец.", show_alert=True)
            return
        await ranks.set_right(db, cb.chat, cb.act, val, cb.uid)
        await call.answer(f"Сохранено: {ranks.rank_name(val)}")
        text, kb = await _rights_main(db, cb.uid, cb.chat)
    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass
    await call.answer()
