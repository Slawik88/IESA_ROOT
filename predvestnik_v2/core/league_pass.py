"""Season pass from season 2 (owner, 22.10.2026): experience from League levels and, less, from casual games.

Two rows: free for everyone, VIP for an active VIP at the moment of claiming.  Rewards are Mora, Diamonds,
a few Zarniki (30 free / 80 VIP per season, owner's cap) and chest keys of every tier: the chests hold the
food, pet cards and jokers.  Never skins.  Amounts live in this one table.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Final

from core import seasons
from core.chests_v1 import KEY_TIER_NAMES

FIRST_SEASON: Final = 2           # season 1 keeps the old free pass (core.season_pass)
LEVELS: Final = 30
XP_PER_LEVEL: Final = 300
CLAIM_GRACE: Final = timedelta(days=30)
REASON: Final = "season_pass_v2_reward"
TRACKS: Final = ("free", "vip")

# Casual games: less than a ranked level, and at most CASUAL_DAILY_CAP a UTC day.  Casual runs are timed
# on the phone, so the cap is what keeps a forged result worth no more than an honest active day.
CASUAL_DAILY_CAP: Final = 300
RHYTHM_SCORE_PER_XP: Final = 300
RHYTHM_MAX_XP: Final = 60
MINES_WIN_XP: Final = {"easy": 12, "normal": 20, "hard": 40}

# Pets (owner, 23.10.2026): real progress with a pet gives a little experience, under its own daily cap, so
# pets alone fill about a third of the pass (100 a day × a month ≈ 10 of 30 levels) and never replace play.
# Only an action that costs something counts: food, energy, Mora, Essence, cards or a weekly attempt.
# Free toggles (active pet, builds and presets, equip/unequip, opening a tracking cell, the starter gear)
# give nothing — otherwise a tap loop would be a farm.  What takes time counts when it pays off: an activity
# when it completes, a Trail run when it is claimed.  One receipt per action: a replayed request adds nothing.
PET_DAILY_CAP: Final = 100
PET_XP: Final = {
    "feed": 10,              # еда тратится
    "activity_done": 20,     # занятие завершилось (старт не считается)
    "expedition": 10,        # решение в экспедиции
    "trail_claim": 20,       # забран поход/экспедиция Тропы (энергия потрачена на старте)
    "tracking": 10,          # начато выслеживание (попытки ограничены)
    "outing": 10,            # начата вылазка
    "trial": 30,             # испытание недели, одна сдача в неделю
    "level_up": 20,          # улучшение: карточки и Мора
    "camp_upgrade": 20,      # стройка в лагере: Мора и Эссенция
    "reforge": 20,           # перековка талисмана: Эссенция
    "gear_craft": 10,        # снаряжение создано
    "gear_upgrade": 10,      # снаряжение улучшено
    "duplicate": 10,         # дубликат питомца из сундука
}
_PET_REQUEST_KIND: Final = {"feed": "feed", "choose_expedition": "expedition", "claim": "trail_claim", "track_start": "tracking",
                            "outing_start": "outing", "trial": "trial", "level_up": "level_up", "camp_upgrade": "camp_upgrade",
                            "reforge": "reforge"}

# level: (free, VIP).  A reward is {"mora": n} | {"diamonds": n} | {"zarniki": n} | {"key": tier}.
TRACK: Final = {
    1: ({"mora": 100}, {"mora": 300}), 2: ({"key": 1}, {"key": 3}), 3: ({"mora": 100}, {"diamonds": 5}),
    4: ({"key": 1}, {"key": 3}), 5: ({"zarniki": 5}, {"zarniki": 10}), 6: ({"mora": 150}, {"mora": 400}),
    7: ({"key": 3}, {"key": 4}), 8: ({"diamonds": 3}, {"diamonds": 5}), 9: ({"mora": 150}, {"mora": 400}),
    10: ({"zarniki": 5}, {"zarniki": 10}), 11: ({"key": 1}, {"key": 3}), 12: ({"mora": 150}, {"mora": 500}),
    13: ({"key": 3}, {"key": 4}), 14: ({"diamonds": 3}, {"diamonds": 8}), 15: ({"zarniki": 5}, {"zarniki": 10}),
    16: ({"mora": 200}, {"mora": 500}), 17: ({"key": 1}, {"key": 3}), 18: ({"key": 4}, {"key": 4}),
    19: ({"diamonds": 4}, {"diamonds": 8}), 20: ({"zarniki": 5}, {"zarniki": 15}), 21: ({"mora": 200}, {"mora": 600}),
    22: ({"key": 3}, {"key": 4}), 23: ({"diamonds": 5}, {"diamonds": 10}), 24: ({"mora": 250}, {"mora": 600}),
    25: ({"zarniki": 5}, {"zarniki": 15}), 26: ({"key": 4}, {"key": 6}), 27: ({"mora": 250}, {"mora": 700}),
    28: ({"key": 3}, {"key": 4}), 29: ({"zarniki": 5}, {"zarniki": 20}), 30: ({"key": 6}, {"key": 6}),
}
_ICON = {"mora": "🪙", "diamonds": "💎", "zarniki": "✨"}
_NAME = {"mora": "Моры", "diamonds": "Алмазов", "zarniki": "Зарников"}


def _total(track: int, kind: str) -> int:
    return sum(rows[track].get(kind, 0) for rows in TRACK.values())


assert len(TRACK) == LEVELS and _total(0, "zarniki") == 30 and _total(1, "zarniki") == 80


class PassRuleError(ValueError):
    pass


def level_of(xp: int) -> int:
    return max(0, min(LEVELS, int(xp) // XP_PER_LEVEL))


def reward(level: int, track: str) -> dict:
    if track not in TRACKS or int(level) not in TRACK:
        raise PassRuleError("Такой награды нет.")
    return dict(TRACK[int(level)][TRACKS.index(track)])


def reward_text(item: dict) -> str:
    if "key" in item:
        return f"🗝 {KEY_TIER_NAMES[item['key']]} ключ · {item['key']}★+"
    kind, amount = next(iter(item.items()))
    return f"{_ICON[kind]} {amount} {_NAME[kind]}"


def rhythm_casual_xp(score: int) -> int:
    return min(RHYTHM_MAX_XP, max(0, int(score)) // RHYTHM_SCORE_PER_XP)


def mines_casual_xp(*, won: bool, difficulty: str) -> int:
    return MINES_WIN_XP.get(difficulty, 0) if won else 0


def pet_action_kind(request: dict) -> str | None:
    """Which counted pet action a saved pet request is; None for a free one (see PET_XP)."""
    kind = request.get("type") if isinstance(request, dict) else None
    if kind == "equipment":
        return {"craft": "gear_craft", "upgrade": "gear_upgrade"}.get(request.get("operation"))
    return _PET_REQUEST_KIND.get(kind)


def capped(gain: int, earned_today: int, cap: int = CASUAL_DAILY_CAP) -> int:
    """Experience left under today's cap (games and pets each have their own)."""
    return max(0, min(int(gain), int(cap) - max(0, int(earned_today))))


def active(now: datetime) -> bool:
    return seasons.season_number(now) >= FIRST_SEASON


def claim_deadline(season: int) -> datetime:
    return seasons.season_bounds(season)[1] + CLAIM_GRACE


def claimable_seasons(now: datetime) -> list[int]:
    now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    current = seasons.season_number(now)
    return [n for n in (current - 1, current) if n >= FIRST_SEASON and (n == current or now < claim_deadline(n))]
