"""Skins V3 collecting: ranks, milestones, rarity rows, set rewards and the skin of the week.

Everything here is a pure function of the catalog and the clock, with no randomness: the player can read every
reward before earning it. The rewards are status (rank, set crest, badges) and a small Essence bonus that is a fixed
share of what the owned skins cost, so collecting never becomes a cheaper road to a raised skin
(tools/test_skins_v3_economy.py adds all free Essence up and checks it).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Final

from core.skins_v3 import BONUS_SHARE, BUY_PRICE_ZARNIKI, FEATURED_SHARE, TIERS, bonus_essence
from core.skins_v3_catalog import SEASONS, SETS, SKINS

ROW_SHARE: Final = 0.02

# (owned skins, Essence, rank earned). The last step is "every skin" and follows the catalog size.
_STEPS: Final = ((3, 80, "Собиратель"), (6, 160, "Коллекционер"), (10, 320, "Знаток образов"),
                 (15, 520, "Хранитель витрины"), (20, 800, "Мастер коллекции"))
_ALL: Final = (1200, "Легенда витрины")
BASE_RANK: Final = "Новичок витрины"
# (skins raised to their ceiling, badge)
MAXED_BADGES: Final = ((1, "Огранщик"), (3, "Мастер тиров"), (6, "Виртуоз"), (10, "Вершина"))

SET_GLYPH: Final = {"lotus": "🪷", "sakura": "🌸", "night_pumpkins": "🎃"}
# Ranks, rarity rows and the skin of the week count only permanent skins; a season skin earns its own set and crest.
PERMANENT: Final = tuple(sid for sid, skin in SKINS.items() if not skin.get("season"))


def milestones() -> list[dict]:
    steps = [{"id": f"own:{at}", "at": at, "essence": essence, "rank": rank} for at, essence, rank in _STEPS]
    steps.append({"id": "own:all", "at": len(PERMANENT), "essence": _ALL[0], "rank": _ALL[1]})
    return steps


def rank_for(owned_count: int) -> str:
    title = BASE_RANK
    for step in milestones():
        if owned_count >= step["at"]:
            title = step["rank"]
    return title


def maxed_badge(maxed_count: int) -> str | None:
    title = None
    for at, name in MAXED_BADGES:
        if maxed_count >= at:
            title = name
    return title


def owned_permanent(owned) -> int:
    return sum(1 for sid in owned if sid in PERMANENT)


def row_members(rarity: str) -> list[str]:
    return [sid for sid in PERMANENT if SKINS[sid]["tier"] == rarity]


def row_bonus(rarity: str) -> int:
    return bonus_essence(sum(BUY_PRICE_ZARNIKI[SKINS[m]["tier"]] for m in row_members(rarity)), ROW_SHARE)


def set_bonus(set_id: str) -> int:
    return bonus_essence(sum(BUY_PRICE_ZARNIKI[SKINS[m]["tier"]] for m in SETS[set_id]["members"]), BONUS_SHARE)


def featured_bonus(skin_id: str) -> int:
    return bonus_essence(BUY_PRICE_ZARNIKI[SKINS[skin_id]["tier"]], FEATURED_SHARE)


def total_one_time_essence() -> int:
    """Every Essence bonus a player can ever collect for owning skins (the economy test caps this)."""
    return (sum(m["essence"] for m in milestones()) + sum(row_bonus(r) for r in TIERS if row_members(r))
            + sum(set_bonus(s) for s in SETS))


# ── Seasons ──────────────────────────────────────────────────────────────────────────────────────────────────
def _utc(day: str) -> datetime:
    return datetime.fromisoformat(day).replace(tzinfo=timezone.utc)


def season_window(season_id: str, now: datetime | None = None) -> dict:
    spec = SEASONS[season_id]
    moment = now.astimezone(timezone.utc) if now else datetime.now(timezone.utc)
    start, end = _utc(spec["starts"]), _utc(spec["ends"])
    return {"id": season_id, "name": spec["name"], "starts_at": start.isoformat(), "ends_at": end.isoformat(), "open": start <= moment < end,
            "state": "soon" if moment < start else "open" if moment < end else "over"}


def season_of(skin_id: str, now: datetime | None = None) -> dict | None:
    season_id = SKINS[skin_id].get("season")
    return season_window(season_id, now) if season_id else None


# ── Skin of the week ─────────────────────────────────────────────────────────────────────────────────────────────
_EPOCH: Final = date(2026, 1, 5)   # a Monday; weeks are UTC Monday to Monday, like the quests


def _rotation() -> list[str]:
    """Round-robin over rarities (D, C, B, A, S, SS, SSS, D, C, ...), so every week mixes cheap and rare."""
    lanes = [row_members(t) for t in TIERS]
    order: list[str] = []
    for position in range(max(len(lane) for lane in lanes)):
        order.extend(lane[position] for lane in lanes if position < len(lane))
    return order


def week_index(now: datetime | None = None) -> int:
    day = (now.astimezone(timezone.utc) if now else datetime.now(timezone.utc)).date()
    return (day - _EPOCH).days // 7


def featured(now: datetime | None = None) -> dict:
    index = week_index(now)
    order = _rotation()
    start = _EPOCH + timedelta(days=index * 7)
    ends = datetime(start.year, start.month, start.day, tzinfo=timezone.utc) + timedelta(days=7)
    skin_id = order[index % len(order)]
    return {"skin_id": skin_id, "week": start.isoformat(), "ends_at": ends.isoformat(), "bonus_essence": featured_bonus(skin_id)}
