"""Личный итог сезона в личку (категория «Сезон», по согласию игрока).

Что входит (решение владельца 2026-11-11, «подробно»): уровень Пропуска сезона, место в таблицах Ритма и Сапёра
на конец сезона, сколько партий сыграно в Ритм и Сапёр, какие образы получены за сезон. Таблицы сезона 2 не
замораживаются (призовой была только таблица Ритма сезона 1), поэтому места считаются по окну сезона тем же
правилом, что и экран «Топ», сразу после конца сезона. Пустой итог (ничего не сыграно и не получено) не отправляется.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta

from core import league_pass as pass_rules
from core import seasons
from core.minesweeper_v2 import DIFFICULTIES
from core.skins_v3_catalog import SKINS

FIRST_SEASON = pass_rules.FIRST_SEASON   # итог шлётся с сезона 2 (новый Пропуск и таблицы по окну сезона)
DELAY = timedelta(hours=1)               # как SETTLEMENT_DELAY: результаты последних минут сезона успевают записаться
WINDOW = timedelta(days=2)               # после этого итог уже не новость
CACHE_TTL = 30 * 60                      # места одного сезона считаются раз в полчаса на весь проход, не на игрока
MAX_LOOKS = 5                            # образов в строке; остальные — «и ещё N»

_cache: dict[int, tuple[float, dict]] = {}


def due_season(now: datetime) -> int | None:
    """Сезон, итог которого пора рассылать сейчас, или None."""
    number = seasons.season_number(now) - 1
    if number < FIRST_SEASON:
        return None
    end = seasons.season_bounds(number)[1]
    return number if DELAY <= now - end < WINDOW else None


async def _places(db, sql: str, args: tuple) -> tuple[dict[int, int], int]:
    async with db.execute(sql, args) as c:
        rows = await c.fetchall()
    return {int(r[0]): int(r[1]) for r in rows}, len(rows)


async def _counts(db, sql: str, args: tuple) -> dict[int, int]:
    async with db.execute(sql, args) as c:
        return {int(r[0]): int(r[1]) for r in await c.fetchall()}


async def _has(db, table: str) -> bool:
    async with db.execute("SELECT to_regclass(?) IS NOT NULL", (table,)) as c:
        row = await c.fetchone()
    return bool(row and row[0])


async def standings(db, season: int) -> dict:
    """Места и число партий всех игроков сезона: один расчёт на полчаса, а не запрос на каждого игрока."""
    cached = _cache.get(season)
    if cached and time.monotonic() - cached[0] < CACHE_TTL:
        return cached[1]
    from infrastructure.repositories import minesweeper_v2 as sapper_repo
    from infrastructure.repositories import rhythm_v2 as rhythm_repo
    start, end = seasons.season_bounds(season)
    data: dict = {"rhythm": ({}, 0), "sapper": {}, "rhythm_games": {}, "sapper_games": {}}
    if await _has(db, "rhythm_v2_runs"):
        # то же правило, что у таблицы Ритма (лучший чистый забег за окно сезона), без подписей игроков
        data["rhythm"] = await _places(db, rhythm_repo._SEASON_BEST + "SELECT user_id, place FROM ranked", ("normal", start, end))
        data["rhythm_games"] = await _counts(
            db, "SELECT user_id, COUNT(*) FROM rhythm_v2_runs WHERE status = 'finished' AND finished_at >= ? AND finished_at < ? "
                "GROUP BY user_id", (start, end))
    if await _has(db, "minesweeper_v2_runs"):
        for key in DIFFICULTIES:
            data["sapper"][key] = await _places(db, sapper_repo._SEASON_BEST + "SELECT user_id, place FROM ranked", (key, start, end))
        data["sapper_games"] = await _counts(
            db, "SELECT user_id, COUNT(*) FROM minesweeper_v2_runs WHERE status IN ('won', 'lost') AND finished_at >= ? "
                "AND finished_at < ? GROUP BY user_id", (start, end))
    _cache.clear()   # держим только текущий сезон
    _cache[season] = (time.monotonic(), data)
    return data


async def _pass_level(db, user_id: int, season: int) -> int:
    if not await _has(db, "league_pass_progress"):
        return 0
    from infrastructure.repositories import league_pass as pass_repo
    return pass_rules.level_of(await pass_repo.xp(db, user_id=user_id, season=season))


async def _looks(db, user_id: int, season: int) -> list[str]:
    if not await _has(db, "skins_v3_owned"):
        return []
    start, end = seasons.season_bounds(season)
    async with db.execute("SELECT skin_id FROM skins_v3_owned WHERE user_id = ? AND acquired_at >= ? AND acquired_at < ? "
                          "ORDER BY acquired_at, skin_id", (int(user_id), start, end)) as c:
        return [SKINS[r[0]]["name"] for r in await c.fetchall() if r[0] in SKINS]


def _games(n: int) -> str:
    tail = n % 100
    word = "партий" if 11 <= tail <= 14 else {1: "партия", 2: "партии", 3: "партии", 4: "партии"}.get(n % 10, "партий")
    return f"{n} {word}"


async def report(db, user_id: int, season: int) -> dict | None:
    """Данные итога одного игрока; None — за сезон ничего не было."""
    table = await standings(db, season)
    uid = int(user_id)
    rhythm_places, rhythm_total = table["rhythm"]
    sapper = [(key, places[uid], total) for key, (places, total) in table["sapper"].items() if uid in places]
    best_sapper = min(sapper, key=lambda x: (x[1], -list(DIFFICULTIES).index(x[0])), default=None)
    data = {
        "season": season,
        "pass_level": await _pass_level(db, uid, season),
        "rhythm": (rhythm_places[uid], rhythm_total) if uid in rhythm_places else None,
        "sapper": best_sapper,
        "rhythm_games": table["rhythm_games"].get(uid, 0),
        "sapper_games": table["sapper_games"].get(uid, 0),
        "looks": await _looks(db, uid, season),
    }
    if not (data["pass_level"] or data["rhythm"] or data["sapper"] or data["rhythm_games"] or data["sapper_games"] or data["looks"]):
        return None
    return data


def text(data: dict) -> str:
    """Сообщение игроку: короткие строки, только то, что у него было (docs/PLAYER_COPY.md)."""
    lines = [f"🏁 <b>Итоги сезона {data['season']}</b>", "Сезон закончился. Вот как он прошёл у тебя:", ""]
    if data["pass_level"]:
        lines.append(f"🏆 Пропуск: {data['pass_level']}-й уровень из {pass_rules.LEVELS}.")
    if data["rhythm"]:
        place, total = data["rhythm"]
        lines.append(f"🎵 Ритм: {place}-е место из {total}.")
    if data["sapper"]:
        key, place, total = data["sapper"]
        lines.append(f"💣 Сапёр: {place}-е место из {total}, поле «{DIFFICULTIES[key].label}».")
    played = [f"{_games(n)} в {name}" for n, name in ((data["rhythm_games"], "Ритм"), (data["sapper_games"], "Сапёр")) if n]
    if played:
        lines.append("🎮 Сыграно: " + " и ".join(played) + ".")
    if data["looks"]:
        shown = data["looks"][:MAX_LOOKS]
        extra = len(data["looks"]) - len(shown)
        lines.append("🎨 Новые образы: " + ", ".join(shown) + (f" и ещё {extra}" if extra else "") + ".")
    lines += ["", "Новый сезон уже начался: места в таблицах снова пустые. Удачи!"]
    return "\n".join(lines)
