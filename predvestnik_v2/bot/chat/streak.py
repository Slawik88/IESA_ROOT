"""«бот стрик» — серия и компактная карточка активности."""
from __future__ import annotations

import html
from datetime import date, timedelta

from bot.chat import activity_graph  # noqa: F401  (график стрика идёт через skin_card.graph_media)
from bot.chat.framework import Ctx, registry
from bot.chat.targets import NOT_FOUND, names_someone, resolve_target
from bot.chat.tracking import local_now

WEEKS = 9
LEVELS = ("⬜", "🟩", "🟨", "🟧", "🟥")   # нет активности → очень много
DAY_NAMES = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")


def level(count: int, peak: int) -> int:
    if count <= 0 or peak <= 0:
        return 0
    share = count / peak
    return 1 if share <= 0.25 else 2 if share <= 0.5 else 3 if share <= 0.75 else 4


def heatmap(counts: dict[date, int], today: date) -> str:
    """Сетка как на GitHub: строки — дни недели, столбцы — недели, справа текущая."""
    last_monday = today - timedelta(days=today.weekday())
    first = last_monday - timedelta(weeks=WEEKS - 1)
    peak = max(counts.values(), default=0)
    rows = []
    for wd in range(7):
        cells = []
        for w in range(WEEKS):
            d = first + timedelta(weeks=w, days=wd)
            cells.append(" " if d > today else LEVELS[level(counts.get(d, 0), peak)])
        rows.append(f"<code>{DAY_NAMES[wd]}</code> " + "".join(cells))
    return "\n".join(rows)


async def activity(db, user_id: int, since: date, until: date) -> dict[date, int]:
    async with db.execute(
        "SELECT date, SUM(message_count) FROM daily_user_stats WHERE user_id = ? AND date BETWEEN ? AND ? "
        "GROUP BY date", (user_id, since.isoformat(), until.isoformat())) as cur:
        rows = await cur.fetchall()
    return {date.fromisoformat(r[0]): int(r[1]) for r in rows}


async def streak_of(db, user_id: int, today: date) -> tuple[int, int, bool]:
    """(текущий, лучший, засчитан ли сегодня). Пропущенный вчера день обнуляет серию."""
    async with db.execute(
        "SELECT streak, COALESCE(best_streak, 0), last_login FROM daily_login WHERE user_id = ? AND chat_id = 0",
        (user_id,)) as cur:
        row = await cur.fetchone()
    if not row or not row[2]:
        return 0, int(row[1]) if row else 0, False
    last = row[2].date()
    current = int(row[0] or 0) if last >= today - timedelta(days=1) else 0
    return current, max(int(row[1]), current), last == today


@registry.command("стрик", aliases=("серия", "активность"), usage="бот стрик [@ник]", section="profile",
                  summary="Серия активных дней и график сообщений за месяц.")
# СТИЛЬ v1 (оформлено, см. docs/CHAT_BOT_DESIGN_HANDOFF.md)
async def cmd_streak(ctx: Ctx) -> None:
    target, _ = await resolve_target(ctx.db, ctx.message, ctx.args)
    if target is None and names_someone(ctx.args):
        await ctx.reply(NOT_FOUND)
        return
    uid = target.user_id if target else ctx.user_id
    who = html.escape(target.label()[:120]) if target else "Ваш"
    today = local_now().date()
    current, best, done = await streak_of(ctx.db, uid, today)
    status = "✅ Сегодня засчитан" if done else "⏳ Напишите в чат, чтобы засчитать сегодня"
    from bot.chat import profile, profile_view   # profile сам импортирует streak
    from services import skins_chat
    chat = getattr(ctx.message, "chat", None)
    look = await skins_chat.safe_card_look(ctx.db, uid, chat.id) if chat is not None else None
    text = profile_view.streak(look, who, current, best, status) if look else (
        f"🔥 <b>{who} стрик: {current}</b>\n"
        f"Лучший: <b>{best}</b> дней\n{status}\n"
        "<i>Серия и график учитывают активность во всех чатах.</i>"
    )
    user = target or getattr(ctx.message, "from_user", None)
    name = getattr(user, "name", None) or getattr(user, "full_name", "") or ""
    # Same scope and cache as a private profile. No second history query and no
    # extra render while the previous profile image is still fresh.
    await profile.send_media_card(ctx, text, uid, None, look, name, getattr(user, "username", None))

