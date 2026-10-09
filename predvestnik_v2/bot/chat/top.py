"""«бот топ» — рейтинг по сообщениям: игроки чата, все игроки, чаты."""
from __future__ import annotations

from datetime import date, timedelta

from aiogram import Router
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.chat.framework import Ctx, registry
from bot.chat.style import quote
from bot.chat.tracking import local_now

PAGE_SIZE = 25
ZW = "​"   # «@» + нулевой пробел: ник виден, но участника не пингует
PERIODS = {"d": "День", "w": "Неделя", "lw": "Прошлая неделя"}
SCOPES = {"c": "Этот чат", "g": "Все игроки", "k": "Топ чатов"}
MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


class TopCB(CallbackData, prefix="top"):
    uid: int
    scope: str
    period: str
    page: int
    chat: int


def period_range(period: str, today: date) -> tuple[str, str]:
    if period == "d":
        a = b = today
    elif period == "w":
        a, b = today - timedelta(days=today.weekday()), today
    else:
        monday = today - timedelta(days=today.weekday())
        a, b = monday - timedelta(days=7), monday - timedelta(days=1)
    return a.isoformat(), b.isoformat()


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fmt_num(n: int) -> str:
    return f"{int(n):,}".replace(",", " ")


def render(title: str, rows: list[tuple[int, str, int]], page: int, pages: int, period: str, scope: str) -> str:
    head = f"🏆 <b>{title}</b>\n<i>{PERIODS[period]}</i>"
    if not rows:
        return head + "\n\nПока тихо — сообщений за этот период нет."
    width = len(fmt_num(rows[0][2]))
    lines = []
    for pos, name, cnt in rows:
        mark = MEDALS.get(pos, f"<b>{pos}.</b>")
        lines.append(f"{mark} {_esc(name)} · <code>{fmt_num(cnt).rjust(width)}</code>")
    foot = f"\n\n<i>Страница {page + 1} из {pages}</i>" if pages > 1 else ""
    return head + "\n\n" + quote(lines) + foot


def keyboard(uid: int, scope: str, period: str, page: int, pages: int, chat: int) -> InlineKeyboardMarkup:
    def cb(**kw) -> str:
        data = dict(uid=uid, scope=scope, period=period, page=0, chat=chat)
        data.update(kw)
        return TopCB(**data).pack()

    def label(text: str, active: bool) -> str:
        return f"• {text} •" if active else text

    rows = [
        [InlineKeyboardButton(text=label(t, k == period), callback_data=cb(period=k)) for k, t in PERIODS.items()],
        [InlineKeyboardButton(text=label(t, k == scope), callback_data=cb(scope=k)) for k, t in SCOPES.items()],
    ]
    if pages > 1:
        rows.append([
            InlineKeyboardButton(text="◀️", callback_data=cb(page=(page - 1) % pages)),
            InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="top:noop"),
            InlineKeyboardButton(text="▶️", callback_data=cb(page=(page + 1) % pages)),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def build(db, scope: str, period: str, page: int, chat: int) -> tuple[str, int]:
    a, b = period_range(period, local_now().date())
    if scope == "k":
        async with db.execute(
            "SELECT COUNT(DISTINCT chat_id) FROM daily_user_stats WHERE date BETWEEN ? AND ?", (a, b)
        ) as cur:
            total = (await cur.fetchone())[0] or 0
        pages = max(1, -(-total // PAGE_SIZE))
        page = min(page, pages - 1)
        async with db.execute(
            "SELECT d.chat_id, COALESCE(s.chat_title, 'Чат ' || d.chat_id) AS name, SUM(d.message_count) AS c "
            "FROM daily_user_stats d LEFT JOIN chat_settings s ON s.chat_id = d.chat_id "
            "WHERE d.date BETWEEN ? AND ? GROUP BY d.chat_id, s.chat_title "
            "ORDER BY c DESC, d.chat_id LIMIT ? OFFSET ?",
            (a, b, PAGE_SIZE, page * PAGE_SIZE),
        ) as cur:
            data = await cur.fetchall()
        rows = [(page * PAGE_SIZE + i + 1, r[1], int(r[2])) for i, r in enumerate(data)]
        return render("Топ чатов", rows, page, pages, period, scope), pages

    where, params = "date BETWEEN ? AND ?", [a, b]
    title = "Топ всех игроков"
    if scope == "c":
        where += " AND chat_id = ?"
        params.append(chat)
        title = "Топ чата"
    async with db.execute(
        f"SELECT COUNT(DISTINCT user_id) FROM daily_user_stats WHERE {where}", params
    ) as cur:
        total = (await cur.fetchone())[0] or 0
    pages = max(1, -(-total // PAGE_SIZE))
    page = min(page, pages - 1)
    async with db.execute(
        f"SELECT d.user_id, u.user_tg_username, SUM(d.message_count) AS c "
        f"FROM daily_user_stats d LEFT JOIN users u ON u.user_tg_id = d.user_id "
        f"WHERE {where.replace('date', 'd.date').replace('chat_id', 'd.chat_id')} "
        f"GROUP BY d.user_id, u.user_tg_username ORDER BY c DESC, d.user_id LIMIT ? OFFSET ?",
        params + [PAGE_SIZE, page * PAGE_SIZE],
    ) as cur:
        data = await cur.fetchall()
    rows = [
        (page * PAGE_SIZE + i + 1, f"@{ZW}{r[1]}" if r[1] else f"id{r[0]}", int(r[2]))
        for i, r in enumerate(data)
    ]
    return render(title, rows, page, pages, period, scope), pages


@registry.command(
    "топ", usage="бот топ", aliases=("top",), section="stats",
    summary="Рейтинг по сообщениям: чат, все игроки или топ чатов. Период переключается кнопками.",
)
async def cmd_top(ctx: Ctx) -> None:
    chat = ctx.message.chat
    scope = "c" if chat.type in ("group", "supergroup") else "g"
    text, pages = await build(ctx.db, scope, "d", 0, chat.id)
    await ctx.reply(text, reply_markup=keyboard(ctx.user_id, scope, "d", 0, pages, chat.id))


router = Router(name="chat_top")


@router.callback_query(TopCB.filter())
async def on_top(call: CallbackQuery, callback_data: TopCB, db) -> None:
    if call.from_user.id != callback_data.uid:
        await call.answer("Это меню другого игрока. Вызовите своё: «бот топ».", show_alert=True)
        return
    scope, period = callback_data.scope, callback_data.period
    if scope not in SCOPES or period not in PERIODS:
        await call.answer()
        return
    text, pages = await build(db, scope, period, callback_data.page, callback_data.chat)
    page = min(callback_data.page, pages - 1)
    try:
        await call.message.edit_text(
            text, parse_mode="HTML",
            reply_markup=keyboard(callback_data.uid, scope, period, page, pages, callback_data.chat),
        )
    except Exception:
        pass   # «message is not modified» при повторном нажатии
    await call.answer()


@router.callback_query(lambda c: c.data == "top:noop")
async def on_noop(call: CallbackQuery) -> None:
    await call.answer()
