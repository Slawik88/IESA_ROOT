"""«бот санкции» — списки чата: баны (чёрный список), кики, муты, варны, защита.

У каждого игрока — карточка с кнопками снятия; сроки меняются повторной командой.
"""
from __future__ import annotations

import html

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup

from bot.chat import ranks
from bot.chat.framework import Ctx, registry
from bot.chat.moderation import TG_FAIL, active_warns, commit, do_unban, log, revoke_all_warns
from bot.chat.style import quote

router = Router(name="chat_sanctions")
PAGE = 8
TABS = {"ban": "⛔ Баны", "mute": "🔇 Муты", "warn": "⚠️ Варны", "kick": "👢 Кики", "shield": "🛡 Защита"}


class SanCB(CallbackData, prefix="sn"):
    uid: int        # кто открыл меню
    chat: int
    tab: str
    page: int
    user: int = 0   # карточка игрока; 0 — список
    act: str = ""   # unban | unmute | unwarn | unshield


def _name(uid: int, uname: str | None) -> str:
    return f"@​{uname}" if uname else f"id{uid}"


def _when(dt) -> str:
    if dt is None:
        return "навсегда"
    try:
        if dt.year >= 9999:
            return "навсегда"
    except AttributeError:
        return str(dt)
    return "до " + dt.strftime("%d.%m %H:%M")


async def _rows(db, chat: int, tab: str) -> list[tuple[int, str | None, str]]:
    if tab == "ban":
        sql = ("SELECT b.user_id, u.user_tg_username, b.expires_at, b.reason FROM chat_blacklist b "
               "LEFT JOIN users u ON u.user_tg_id = b.user_id WHERE b.chat_id = ? "
               "AND (b.expires_at IS NULL OR b.expires_at > NOW()) ORDER BY b.added_at DESC")
    elif tab == "mute":
        sql = ("SELECT s.user_tg_id, u.user_tg_username, s.muted_until, NULL FROM user_chat_stats s "
               "LEFT JOIN users u ON u.user_tg_id = s.user_tg_id WHERE s.chat_tg_id = ? "
               "AND s.muted_until > NOW() ORDER BY s.muted_until")
    elif tab == "warn":
        sql = ("SELECT w.user_id, u.user_tg_username, COUNT(*), NULL FROM user_warnings w "
               "LEFT JOIN users u ON u.user_tg_id = w.user_id WHERE w.chat_id = ? AND w.revoked_at IS NULL "
               "AND (w.expires_at IS NULL OR w.expires_at > NOW()) GROUP BY w.user_id, u.user_tg_username "
               "ORDER BY COUNT(*) DESC")
    elif tab == "kick":
        sql = ("SELECT l.user_id, u.user_tg_username, MAX(l.created_at), NULL FROM moderation_logs l "
               "LEFT JOIN users u ON u.user_tg_id = l.user_id WHERE l.chat_id = ? AND l.action = 'kick' "
               "AND l.created_at > NOW() - INTERVAL '30 days' GROUP BY l.user_id, u.user_tg_username "
               "ORDER BY MAX(l.created_at) DESC")
    else:
        sql = ("SELECT s.user_tg_id, u.user_tg_username, s.immune_until, s.is_immune FROM user_chat_stats s "
               "LEFT JOIN users u ON u.user_tg_id = s.user_tg_id WHERE s.chat_tg_id = ? "
               "AND (s.is_immune OR s.immune_until > NOW()) ORDER BY s.is_immune DESC, s.immune_until")
    async with db.execute(sql, (chat,)) as cur:
        data = await cur.fetchall()
    out = []
    for uid, uname, val, extra in data:
        if tab == "warn":
            detail = f"{val} шт."
        elif tab == "kick":
            detail = val.strftime("%d.%m") if val else ""
        elif tab == "shield":
            detail = "иммунитет" if extra else _when(val)
        else:
            detail = _when(val)
        out.append((int(uid), uname, detail))
    return out


async def list_view(db, uid: int, chat: int, tab: str, page: int) -> tuple[str, InlineKeyboardMarkup]:
    rows = await _rows(db, chat, tab)
    pages = max(1, -(-len(rows) // PAGE))
    page = max(0, min(page, pages - 1))
    chunk = rows[page * PAGE:(page + 1) * PAGE]
    lines = [f"📋 <b>{TABS[tab]}</b> · {len(rows)}"]   # СТИЛЬ v1 (оформлено): строки списка одной цитатой
    entries: list[str] = []
    if not rows:
        lines.append("\nСписок пуст.")
    kb: list[list[InlineKeyboardButton]] = []
    tabs = [InlineKeyboardButton(text=("• " + t + " •") if k == tab else t,
                                 callback_data=SanCB(uid=uid, chat=chat, tab=k, page=0).pack())
            for k, t in TABS.items()]
    kb.append(tabs[:3])
    kb.append(tabs[3:])
    for user_id, uname, detail in chunk:
        entries.append(f"<b>{html.escape(_name(user_id, uname))}</b> · {html.escape(detail)}")
        if tab != "kick":
            kb.append([InlineKeyboardButton(
                text=f"{_name(user_id, uname).replace(chr(0x200b), '')} — открыть",
                callback_data=SanCB(uid=uid, chat=chat, tab=tab, page=page, user=user_id).pack())])
    if pages > 1:
        kb.append([
            InlineKeyboardButton(text="◀️", callback_data=SanCB(uid=uid, chat=chat, tab=tab, page=(page - 1) % pages).pack()),
            InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="sn:noop"),
            InlineKeyboardButton(text="▶️", callback_data=SanCB(uid=uid, chat=chat, tab=tab, page=(page + 1) % pages).pack()),
        ])
    if entries:
        lines.append(quote(entries))
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=kb)


async def card_view(db, uid: int, chat: int, tab: str, page: int, user: int) -> tuple[str, InlineKeyboardMarkup]:
    async with db.execute(
        "SELECT u.user_tg_username, s.muted_until, s.immune_until, s.is_immune FROM users u "
        "LEFT JOIN user_chat_stats s ON s.user_tg_id = u.user_tg_id AND s.chat_tg_id = ? WHERE u.user_tg_id = ?",
        (chat, user)) as cur:
        row = await cur.fetchone()
    uname = row[0] if row else None
    async with db.execute(
        "SELECT expires_at, reason FROM chat_blacklist WHERE chat_id = ? AND user_id = ? "
        "AND (expires_at IS NULL OR expires_at > NOW())", (chat, user)) as cur:
        ban = await cur.fetchone()
    warns = await active_warns(db, chat, user)
    lines = [f"👤 <b>{html.escape(_name(user, uname))}</b>"]
    b = lambda text, act: InlineKeyboardButton(
        text=text, callback_data=SanCB(uid=uid, chat=chat, tab=tab, page=page, user=user, act=act).pack())
    actions = []
    if ban:
        lines.append(f"⛔ Бан {_when(ban[0])}" + (f" · {html.escape(ban[1])}" if ban[1] else ""))
        actions.append(b("Снять бан", "unban"))
    muted = row[1] if row else None
    if muted is not None:
        async with db.execute("SELECT ? > NOW()", (muted,)) as cur:
            active = (await cur.fetchone())[0]
        if active:
            lines.append(f"🔇 Мут {_when(muted)}")
            actions.append(b("Снять мут", "unmute"))
    if warns:
        lines.append(f"⚠️ Варнов: {len(warns)}")
        actions.append(b("Снять варны", "unwarn"))
    if row and (row[3] or row[2] is not None):
        lines.append("💠 Иммунитет" if row[3] else f"🛡 Защита {_when(row[2])}")
        actions.append(b("Снять защиту", "unshield"))
    if len(lines) == 1:
        lines.append("Действующих санкций нет.")
    else:
        lines = [lines[0], quote(lines[1:])]
    who = f"@{uname}" if uname else f"id{user}"
    lines.append(f"\n<i>Изменить срок — повторите команду с новым сроком:</i>\n<code>бот мут, {html.escape(who)} 2ч</code>")
    kb = [actions[i:i + 2] for i in range(0, len(actions), 2)]
    kb.append([InlineKeyboardButton(text="◀️ К списку", callback_data=SanCB(uid=uid, chat=chat, tab=tab, page=page).pack())])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=kb)


@registry.command(
    "санкции", aliases=("чс", "черный список", "списки"), usage="бот санкции", private=False,
    section="moderation", summary="Списки чата: баны, муты, варны, кики, защита. Снятие — кнопками.",
)
async def cmd_sanctions(ctx: Ctx) -> None:
    chat = ctx.message.chat.id
    if not await ranks.can(ctx.db, chat, ctx.user_id, "lists"):
        await ctx.reply("⛔ У вашего ранга нет права смотреть списки санкций.")
        return
    text, kb = await list_view(ctx.db, ctx.user_id, chat, "ban", 0)
    await ctx.reply(text, reply_markup=kb)


NEED = {"unban": "unban", "unmute": "unmute", "unwarn": "unwarn", "unshield": "shield"}


@router.callback_query(SanCB.filter())
async def on_sanctions(call: CallbackQuery, callback_data: SanCB, bot: Bot, db) -> None:
    cb = callback_data
    if call.from_user.id != cb.uid:
        await call.answer("Это меню другого игрока. Откройте своё: «бот санкции».", show_alert=True)
        return
    if cb.tab not in TABS or not await ranks.can(db, cb.chat, cb.uid, "lists"):
        await call.answer("Нет доступа.", show_alert=True)
        return
    if cb.act:
        if cb.act not in NEED or not await ranks.can(db, cb.chat, cb.uid, NEED[cb.act]):
            await call.answer("У вашего ранга нет на это права.", show_alert=True)
            return
        try:
            await _apply(bot, db, cb.chat, cb.user, cb.uid, cb.act)
        except (TelegramBadRequest, TelegramForbiddenError):
            await call.answer(TG_FAIL, show_alert=True)
            return
        await call.answer("Готово")
    if cb.user:
        text, kb = await card_view(db, cb.uid, cb.chat, cb.tab, cb.page, cb.user)
    else:
        text, kb = await list_view(db, cb.uid, cb.chat, cb.tab, cb.page)
    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass
    await call.answer()


async def _apply(bot: Bot, db, chat: int, user: int, actor: int, act: str) -> None:
    if act == "unban":
        await do_unban(bot, db, chat, user, actor)
    elif act == "unmute":
        info = await bot.get_chat(chat)
        await bot.restrict_chat_member(chat, user, permissions=info.permissions or ChatPermissions(can_send_messages=True))
        await db.execute("UPDATE user_chat_stats SET muted_until = NULL WHERE chat_tg_id = ? AND user_tg_id = ?", (chat, user))
        await log(db, chat, user, actor, "unmute")
        await commit(db)
    elif act == "unwarn":
        await revoke_all_warns(db, chat, user, actor)
    elif act == "unshield":
        await db.execute("UPDATE user_chat_stats SET immune_until = NULL, is_immune = FALSE "
                         "WHERE chat_tg_id = ? AND user_tg_id = ?", (chat, user))
        await log(db, chat, user, actor, "unshield")
        await commit(db)


@router.callback_query(lambda c: c.data == "sn:noop")
async def on_noop(call: CallbackQuery) -> None:
    await call.answer()
