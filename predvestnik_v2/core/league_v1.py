"""Pure rules of the ranked League (early-access demo): level ladders, stars and pass experience.

Both games are ladders of levels.  Every player gets their own board / rune order, but a level's
conditions (size, mines, depth of logic; tempo, length, gift plan) are identical for everyone, and
for Minesweeper the server proves each board can be cleared without a guess.  Progress resets every
season.  Stars: 1 = level passed (opens the next one), 2 and 3 = how well.  Rewards in the demo are
fake: experience is only shown, nothing is granted.  Design: docs/SEASON_2_RATING_AND_PASS.md.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from typing import Final

from core import rhythm_v2 as rhythm

FLAG_KEY: Final = "feature:early_access"   # admin «Права»: from which role the early access is open
DEMO_SEASON: Final = "demo-1"
GAMES: Final = ("minesweeper", "rhythm")
MAX_LEVEL: Final = 1000
XP_BY_STARS: Final = {1: 60, 2: 80, 3: 100}   # pass experience for the best stars of a level, once per season


class LeagueRuleError(ValueError):
    pass


def check_level(level: int) -> int:
    if not 1 <= int(level) <= MAX_LEVEL:
        raise LeagueRuleError("Такого уровня нет.")
    return int(level)


def xp_gain(old_stars: int, new_stars: int) -> int:
    """Experience a result adds: only the improvement over the best stars already held."""
    return max(0, XP_BY_STARS.get(new_stars, 0) - XP_BY_STARS.get(old_stars, 0))


# ── Minesweeper ladder ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MinesLevel:
    level: int
    width: int
    height: int
    mines: int
    tier: int        # depth of logic the board must need: 1 obvious, 2 pairs of numbers, 3 whole-group reasoning
    par_base_s: int  # third star time: par_base_s + seconds per click (generous, never the main difficulty)


# (first level of the band, width, height)
_MINES_BANDS: Final = ((1, 3, 3), (4, 4, 4), (8, 5, 5), (13, 6, 6), (19, 7, 7), (26, 8, 8), (35, 9, 9),
                       (46, 10, 10), (61, 11, 11), (81, 12, 12), (101, 12, 14), (121, 12, 16))


def mines_level(level: int) -> MinesLevel:
    level = check_level(level)
    width, height = next((w, h) for start, w, h in reversed(_MINES_BANDS) if level >= start)
    density = min(0.24, 0.10 + 0.0016 * level)
    mines = max(2, round(width * height * density))
    tier = 1 if level <= 5 else 2 if level <= 20 else 3
    return MinesLevel(level, width, height, mines, tier, par_base_s=30)


def mines_par_seconds(spec: MinesLevel, clicks: int) -> int:
    """Generous third-star time: 30 s plus 4 s per needed click, more for deeper logic."""
    return int(spec.par_base_s + clicks * 4 * (1.0, 1.0, 1.3, 1.6)[spec.tier])


def mines_stars(*, won: bool, wrong_flags: int, elapsed_ms: int, par_s: int) -> int:
    """1 = cleared; 2 = cleared without a wrong flag; 3 = also within the generous par time."""
    if not won:
        return 0
    if wrong_flags:
        return 1
    return 3 if elapsed_ms <= par_s * 1000 else 2


# ── Rhythm ladder ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RhythmLevel:
    level: int
    signals: int          # length of the level
    base_window_ms: int   # reaction window of the first signal
    growth_pct: int       # tempo growth per 20 signals inside the level
    hearts: int
    star_pct: tuple[int, int]   # 2 and 3 stars: share of the reference score


RHYTHM_FLOOR_MS: Final = 260
RHYTHM_CHUNK: Final = rhythm.CHUNK_SIZE
MAX_SCORE_BONUS_PCT: Final = 80   # all gifts together never add more than +80% (no endless stacking)


def rhythm_level(level: int) -> RhythmLevel:
    level = check_level(level)
    signals = min(60, 30 + 2 * (level // 4))
    window = max(400, int(2200 * 0.988 ** (level - 1)))
    growth = 8 if level <= 100 else min(16, 8 + (level - 100) // 10)
    return RhythmLevel(level, signals, window, growth, hearts=3, star_pct=(70, 90))


def rhythm_reference(spec: RhythmLevel) -> int:
    """Score of a flawless, fastest-tier run without gifts: the yardstick of the stars."""
    return sum(100 + min(rhythm.COMBO_CAP, i * rhythm.COMBO_STEP) for i in range(spec.signals))


def rhythm_stars(spec: RhythmLevel, *, alive: bool, score: int) -> int:
    """1 = reached the end with a heart left; 2 and 3 = score at least 70% / 90% of the reference."""
    if not alive:
        return 0
    reference = rhythm_reference(spec)
    two, three = spec.star_pct
    return 3 if score * 100 >= reference * three else 2 if score * 100 >= reference * two else 1


def rhythm_pace(spec: RhythmLevel, signal_no: int, perks: dict) -> int:
    chunk = (signal_no - 1) // RHYTHM_CHUNK
    pace = 100 * (100 + spec.growth_pct) ** chunk // 100 ** chunk
    return max(100, pace + rhythm._total(perks, "pace_pct"))


def rhythm_window(spec: RhythmLevel, signal_no: int, perks: dict) -> int:
    raw = spec.base_window_ms * 100 // rhythm_pace(spec, signal_no, perks)
    percent = max(rhythm.MIN_WINDOW_PCT, rhythm._total(perks, "window_pct") + (40 if perks["ebb"] > 0 else 0)
                  + (25 if perks.get("recovery", 0) > 0 else 0))
    return max(RHYTHM_FLOOR_MS, raw * (100 + percent) // 100)


def rhythm_score(*, elapsed_ms: int, window_ms: int, combo_before: int, perks: dict, health: int) -> int:
    """core.rhythm_v2.score_for_correct with the League's upper bound on the summed bonus."""
    tier = 0 if elapsed_ms * 3 <= window_ms else 1 if elapsed_ms * 3 <= window_ms * 2 else 2
    timing = (100, 70, 45)[tier]
    if rhythm._any(perks, "sharp_eye"):
        timing = timing * 3 // 2 if tier == 0 else timing // 2 if tier == 2 else timing
    step = rhythm.COMBO_STEP + rhythm._total(perks, "combo_step")
    cap = rhythm.COMBO_CAP + rhythm._total(perks, "combo_cap")
    raw = (timing + min(cap, combo_before * step)) * (3 if perks["bloody"] > 0 else 1)
    bonus = sum(item.cadence_bonus_pct * count for key, count in perks["owned"].items()
                if (item := rhythm.perk(key)).cadence_every and (combo_before + 1) % item.cadence_every == 0)
    if health <= 2:
        bonus += rhythm._total(perks, "low_health_bonus_pct")
    percent = min(MAX_SCORE_BONUS_PCT, max(rhythm.MIN_SCORE_PCT, rhythm._total(perks, "score_pct") + bonus))
    return max(1, raw * (100 + percent) // 100)


def rhythm_drafts(spec: RhythmLevel) -> int:
    """A gift choice after every full 20 signals that still has signals after it."""
    return (spec.signals - 1) // RHYTHM_CHUNK


def gift_plan(season: str, level: int, draft_no: int) -> tuple[str, ...]:
    """Three gifts of one choice: the same for every player of this season and level (state never changes them)."""
    key = hashlib.sha256(f"league:{season}".encode()).digest()
    pool = [item for item in rhythm.PERKS if not item.filler]
    pool.sort(key=lambda item: hmac.new(key, f"{level}:{draft_no}:{item.id}".encode(), hashlib.sha256).digest())
    chosen = pool[:3]
    if not any(item.kind == "safe" for item in chosen):
        chosen[-1] = next(item for item in pool if item.kind == "safe")
    return tuple(item.id for item in chosen)


def gift_allowed(perk_id: str, *, health: int, perks: dict) -> bool:
    return rhythm._eligible(rhythm.perk(perk_id), health=health, perks=perks)
