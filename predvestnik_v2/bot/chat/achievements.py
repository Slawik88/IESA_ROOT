"""Достижения: «бот достижения [@ник | название]» и объявления о новых уровнях.

Величины по возможности считаются из того, что бот и игры уже хранят (сообщения,
дни, стрик, переводы, браки, партии), поэтому у старых игроков прогресс есть сразу.
Для варп-команд истории нет — для них ведётся свой счётчик.

Уровень никогда не падает: в chat_achievement_levels хранится достигнутый максимум.
Первый подсчёт достижения для игрока тихий (строки ещё нет): иначе после запуска
каждый старый игрок получил бы в чат пачку объявлений.
"""
from __future__ import annotations

import html
import time
from bisect import bisect_right

from aiogram.types import Message
from loguru import logger

from bot.chat.achievements_data import ACHIEVEMENTS, BY_ID, MIN_LEVELS, Achievement, plural
from bot.chat.framework import Ctx, norm, registry
from bot.chat.targets import resolve_target

STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS chat_achievement_levels (
        user_id     BIGINT  NOT NULL,
        achievement TEXT    NOT NULL,
        level       INTEGER NOT NULL DEFAULT 0 CHECK (level >= 0),
        reached_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (user_id, achievement)
    )""",
    """CREATE TABLE IF NOT EXISTS chat_achievement_counters (
        user_id BIGINT NOT NULL,
        counter TEXT   NOT NULL,
        value   BIGINT NOT NULL DEFAULT 0 CHECK (value >= 0),
        PRIMARY KEY (user_id, counter)
    )""",
)

CHAT_EVERY = 60       # сек: как часто после сообщений пересчитывать «общение»
FULL_EVERY = 600      # сек: как часто пересчитывать всё (игры, семья, переводы)
_last_chat: dict[int, float] = {}
_last_full: dict[int, float] = {}


async def ensure_schema(db) -> None:
    for sql in STATEMENTS:
        await db.execute(sql)


def level_of(a: Achievement, value: int) -> int:
    return bisect_right(a.thresholds, value)


def medal(level: int, max_level: int) -> str:
    if level <= 0:
        return "▫️"
    if level >= max_level:
        return "👑"
    share = level / max_level
    return "🥉" if share <= 0.25 else "🥈" if share <= 0.5 else "🥇" if share <= 0.75 else "💎"


def fmt(n: int) -> str:
    return f"{int(n):,}".replace(",", " ")


# ── Источники величин ────────────────────────────────────────────────────────

_tables: dict[str, bool] = {}


async def _has_table(db, name: str) -> bool:
    """Таблицы игр создаются их модулями; пока таблицы нет, величина — 0. Запоминаем только «есть»."""
    if not _tables.get(name):
        async with db.execute("SELECT to_regclass(?::text) IS NOT NULL", (name,)) as cur:
            _tables[name] = bool((await cur.fetchone())[0])
    return _tables[name]


async def _scalar(db, sql: str, params: tuple, *tables: str) -> int:
    for t in tables:
        if not await _has_table(db, t):
            return 0
    async with db.execute(sql, params) as cur:
        row = await cur.fetchone()
    return int(row[0] or 0) if row else 0


async def counter(db, user_id: int, name: str) -> int:
    return await _scalar(db, "SELECT value FROM chat_achievement_counters WHERE user_id = ? AND counter = ?",
                         (user_id, name))


async def bump(db, user_id: int, name: str, by: int = 1) -> None:
    await db.execute(
        "INSERT INTO chat_achievement_counters (user_id, counter, value) VALUES (?, ?, ?) "
        "ON CONFLICT (user_id, counter) DO UPDATE SET value = chat_achievement_counters.value + EXCLUDED.value",
        (user_id, name, by))


_MAFIA_WIN = ("((m.winner = 'mafia' AND p.role IN ('mafia', 'don')) OR "
              "(m.winner = 'town' AND p.role IN ('citizen', 'doctor', 'detective')))")

SOURCES = {
    "messages": lambda db, u: _scalar(
        db, "SELECT SUM(user_messages_count_all_time) FROM user_chat_stats WHERE user_tg_id = ?", (u,)),
    "active_days": lambda db, u: _scalar(
        db, "SELECT COUNT(DISTINCT date) FROM daily_user_stats WHERE user_id = ? AND message_count > 0", (u,)),
    "best_day": lambda db, u: _scalar(
        db, "SELECT MAX(s) FROM (SELECT SUM(message_count) AS s FROM daily_user_stats "
            "WHERE user_id = ? GROUP BY date) t", (u,)),
    "chats": lambda db, u: _scalar(
        db, "SELECT COUNT(*) FROM user_chat_stats WHERE user_tg_id = ? AND user_messages_count_all_time > 0", (u,)),
    "streak": lambda db, u: _scalar(
        db, "SELECT GREATEST(COALESCE(best_streak, 0), COALESCE(streak, 0)) FROM daily_login "
            "WHERE user_id = ? AND chat_id = 0", (u,)),
    "warps_sent": lambda db, u: counter(db, u, "warps_sent"),
    "warps_received": lambda db, u: counter(db, u, "warps_received"),
    "transfers": lambda db, u: _scalar(
        db, "SELECT COUNT(*) FROM economic_operations WHERE user_id = ? AND reason_code = 'player_transfer_out'",
        (u,), "economic_operations"),
    "mora_given": lambda db, u: _scalar(
        db, "SELECT -SUM(delta) FROM economic_ledger WHERE user_id = ? AND currency = 'mora' "
            "AND reason_code = 'player_transfer_out'", (u,), "economic_ledger"),
    # Брак из реестра семей (текущий) или завершённый разводом; старые дубли по чатам не считаются.
    "marriage_days": lambda db, u: _scalar(
        db, "SELECT MAX(EXTRACT(EPOCH FROM (COALESCE(m.ended_at, NOW()) - m.marriage_date)) / 86400) "
            "FROM marriages m WHERE ? IN (m.user1_id, m.user2_id) AND (m.ended_at IS NOT NULL OR EXISTS "
            "(SELECT 1 FROM marriage_members mm WHERE mm.marriage_id = m.id AND mm.user_id = ?))",
        (u, u), "marriages", "marriage_members"),
    "mafia_games": lambda db, u: _scalar(
        db, "SELECT COUNT(*) FROM mafia_v1_players p JOIN mafia_v1_matches m ON m.id = p.match_id "
            "WHERE p.user_id = ? AND m.phase = 'finished' AND m.started_at IS NOT NULL", (u,), "mafia_v1_matches"),
    "mafia_wins": lambda db, u: _scalar(
        db, "SELECT COUNT(*) FROM mafia_v1_players p JOIN mafia_v1_matches m ON m.id = p.match_id "
            f"WHERE p.user_id = ? AND m.phase = 'finished' AND {_MAFIA_WIN}", (u,), "mafia_v1_matches"),
    "rhythm_runs": lambda db, u: _scalar(
        db, "SELECT COUNT(*) FROM rhythm_v2_runs WHERE user_id = ? AND status = 'finished'", (u,), "rhythm_v2_runs"),
    "minesweeper_wins": lambda db, u: _scalar(
        db, "SELECT COUNT(*) FROM minesweeper_v2_runs WHERE user_id = ? AND status = 'won'",
        (u,), "minesweeper_v2_runs"),
    "quests": lambda db, u: _scalar(
        db, "SELECT COUNT(*) FROM quest_v1_assignments WHERE user_id = ? AND completed_at IS NOT NULL",
        (u,), "quest_v1_assignments"),
}


async def value_of(db, user_id: int, a: Achievement) -> int:
    try:
        return await SOURCES[a.id](db, user_id)
    except Exception:
        logger.exception(f"achievement source failed: {a.id}")
        return 0


async def stored_levels(db, user_id: int) -> dict[str, int]:
    async with db.execute("SELECT achievement, level FROM chat_achievement_levels WHERE user_id = ?",
                          (user_id,)) as cur:
        return {r[0]: int(r[1]) for r in await cur.fetchall()}


async def evaluate(db, user_id: int, groups: set[str] | None = None) -> list[tuple[Achievement, int]]:
    """Пересчитать достижения игрока. Возвращает новые уровни, о которых надо объявить."""
    stored = await stored_levels(db, user_id)
    ups: list[tuple[Achievement, int]] = []
    for a in ACHIEVEMENTS:
        if groups is not None and a.group not in groups:
            continue
        level = level_of(a, await value_of(db, user_id, a))
        if a.id not in stored:
            # Первый подсчёт — тихий. ON CONFLICT: параллельный подсчёт уже вставил строку.
            await db.execute(
                "INSERT INTO chat_achievement_levels (user_id, achievement, level) VALUES (?, ?, ?) "
                "ON CONFLICT (user_id, achievement) DO NOTHING", (user_id, a.id, level))
            continue
        if level <= stored[a.id]:
            continue
        # Объявляет только тот, кто реально поднял уровень (защита от двух сообщений подряд).
        async with db.execute(
            "UPDATE chat_achievement_levels SET level = ?, reached_at = NOW() "
            "WHERE user_id = ? AND achievement = ? AND level < ? RETURNING 1",
            (level, user_id, a.id, level)) as cur:
            if await cur.fetchone():
                ups.append((a, level))
    return ups


def announcement(name: str, ups: list[tuple[Achievement, int]]) -> str:
    parts = [f"{a.icon} {a.name} — ур. {lvl}/{a.max_level}" + (" 👑" if lvl >= a.max_level else "")
             for a, lvl in ups]
    return f"🏆 {name}: новый уровень достижений\n" + "\n".join(parts)


async def announce(message: Message, name: str, ups: list[tuple[Achievement, int]]) -> None:
    if not ups:
        return
    try:
        await message.answer(announcement(html.escape(name), ups), parse_mode="HTML")
    except Exception as exc:   # объявление не должно ломать обработку сообщения
        logger.warning(f"achievement announce failed: {exc}")


def quiet_name(username: str | None, fallback: str) -> str:
    return f"@​{username}" if username else fallback


async def after_message(db, message: Message) -> None:
    """После учёта сообщения: «общение» не чаще раза в минуту, всё остальное — раз в 10 минут."""
    user = message.from_user
    if not user or user.is_bot or message.chat.type not in ("group", "supergroup"):
        return
    now = time.monotonic()
    if now - _last_full.get(user.id, -FULL_EVERY) >= FULL_EVERY:
        groups = None
        _last_full[user.id] = _last_chat[user.id] = now
    elif now - _last_chat.get(user.id, -CHAT_EVERY) >= CHAT_EVERY:
        groups = {"chat"}
        _last_chat[user.id] = now
    else:
        return
    try:
        ups = await evaluate(db, user.id, groups)
    except Exception:
        logger.exception("achievements after_message failed")
        return
    await announce(message, quiet_name(user.username, user.first_name), ups)


async def after_warp(db, message: Message, actor_id: int, target_id: int, target_name: str) -> None:
    if actor_id == target_id:
        return
    try:
        await bump(db, actor_id, "warps_sent")
        await bump(db, target_id, "warps_received")
        actor = message.from_user
        await announce(message, quiet_name(actor.username, actor.first_name),
                       await evaluate(db, actor_id, {"warps"}))
        await announce(message, target_name, await evaluate(db, target_id, {"warps"}))
    except Exception:
        logger.exception("achievements after_warp failed")


async def after_transfer(db, message: Message, user_id: int, name: str) -> None:
    try:
        await announce(message, name, await evaluate(db, user_id, {"transfers"}))
    except Exception:
        logger.exception("achievements after_transfer failed")


# ── Команды ──────────────────────────────────────────────────────────────────

def find(query: str) -> Achievement | None:
    q = norm(query)
    if not q:
        return None
    for a in ACHIEVEMENTS:
        if q in (norm(a.name), a.id, *(norm(x) for x in a.aliases)):
            return a
    return None


def line(a: Achievement, level: int, value: int) -> str:
    head = f"{medal(level, a.max_level)} {a.icon} <b>{a.name}</b> — ур. {level}/{a.max_level}"
    if level >= a.max_level:
        return head + " · максимум"
    nxt = a.thresholds[level]
    return f"{head} · {fmt(value)} / {fmt(nxt)}"


GROUP_TITLES = {"chat": "Общение", "warps": "Взаимодействия", "transfers": "Взаимодействия",
                "family": "Семья", "games": "Игры"}


async def card(db, user_id: int, who: str) -> str:
    ups = await evaluate(db, user_id)          # в карточке всегда свежие цифры
    fresh = {a.id for a, _ in ups}
    stored = await stored_levels(db, user_id)
    lines, total, total_max, title = [], 0, 0, None
    for a in ACHIEVEMENTS:
        value = await value_of(db, user_id, a)
        level = max(stored.get(a.id, 0), level_of(a, value))
        total += level
        total_max += a.max_level
        if GROUP_TITLES[a.group] != title:
            title = GROUP_TITLES[a.group]
            lines.append(f"\n<b>{title}</b>")
        lines.append(line(a, level, value) + (" ✨" if a.id in fresh else ""))
    return (f"🏆 <b>{who} достижения</b> · уровней: {total} из {total_max}\n" + "\n".join(lines) +
            "\n\nПодробно: <code>бот достижение болтун</code>")


async def detail(db, user_id: int, a: Achievement) -> str:
    value = await value_of(db, user_id, a)
    level = max((await stored_levels(db, user_id)).get(a.id, 0), level_of(a, value))
    nxt = a.thresholds[level:level + 5]
    ahead = " → ".join(fmt(x) for x in nxt) if nxt else "все уровни пройдены 👑"
    return (f"{a.icon} <b>{a.name}</b> · {medal(level, a.max_level)} ур. {level}/{a.max_level}\n"
            f"{a.measure}: <b>{fmt(value)}</b> {plural(value, a.unit)}\n\n"
            f"Следующие пороги: {ahead}\n"
            f"Последний уровень: {fmt(a.thresholds[-1])} {plural(a.thresholds[-1], a.unit)}")


@registry.command("достижения", aliases=("достижение", "ачивки", "ачивка"),
                  usage="бот достижения [@ник | название]", section="profile",
                  summary=f"Достижения и их уровни (в каждом от {MIN_LEVELS} уровней и больше).")
async def cmd_achievements(ctx: Ctx) -> None:
    target, rest = await resolve_target(ctx.db, ctx.message, ctx.args)
    uid = target.user_id if target else ctx.user_id
    a = find(rest)
    if a:
        await ctx.reply(await detail(ctx.db, uid, a))
        return
    if rest.strip() and not target:
        names = ", ".join(x.name.lower() for x in ACHIEVEMENTS)
        await ctx.reply(f"Нет такого достижения. Есть: {names}.")
        return
    await ctx.reply(await card(ctx.db, uid, target.label() if target else "Ваши"))
