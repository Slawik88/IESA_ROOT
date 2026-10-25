"""Authoritative, dependency-free rules for the approved endless Rune Rhythm.

Rune gifts ("рун-дары") replace the old pre-run augmentations: at the end of
every chunk (20 signals) the run pauses and offers three gifts, the player takes one, and
the effect lives inside the run only.  Every gift carries a bonus AND a cost.
Everyone plays the same ranked mode.

This module deliberately knows nothing about the legacy Reconstruction campaign,
rewards, pets or client-side animation.  Its output is stored and enforced by
the service layer; a browser only renders it and submits a rune tap.
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Final, Literal

from core import rhythm_weather as weather
from core.rhythm_gifts import PERK_BY_ID as _PERK_BY_ID, PERKS, Perk  # noqa: F401  (re-exported: the catalog lives in rhythm_gifts)


RULESET_VERSION: Final = "rhythm-v2-rules-8"     # + series gifts (core/rhythm_gifts.py); rules-7 added chunk weather
PREVIOUS_RULESET_VERSION: Final = "rhythm-v2-rules-6"   # new runs before the season-2 switch (core/rhythm_weather.py)
LEGACY_RULESET_VERSIONS: Final = frozenset({"rhythm-v2-rules-5"})   # offered gifts without the three newer ones
SUPPORTED_RULESETS: Final = frozenset({"rhythm-v2-rules-5", "rhythm-v2-rules-6", "rhythm-v2-rules-7", RULESET_VERSION})
Mode = Literal["normal", "augments"]  # "augments" is only a legacy alias of "normal"
RUNES: Final = ("left", "center", "right")
CHUNK_SIZE: Final = 20
SPEED_GROWTH_PERCENT: Final = 8   # pace grows by this much per finished chunk, compounding
BASE_HEALTH: Final = 5
MAX_HEALTH: Final = 7
MIN_WINDOW_MS: Final = 350
HARD_FLOOR_MS: Final = 200      # after the pace plateau the floor keeps sinking, so no run is endless
FLOOR_FALL_START_CHUNK: Final = 14
FLOOR_FALL_MS_PER_CHUNK: Final = 15
BASE_WINDOW_MS: Final = 2_200
RESUME_LEAD_MS: Final = 3_000   # breathing room after a gift is taken
TAP_GRACE_MS: Final = 250       # network slack: a tap this late past the window still counts (scored as the slowest tier)



COMBO_STEP: Final = 4
COMBO_CAP: Final = 80
MIN_SCORE_PCT: Final = -60
MIN_WINDOW_PCT: Final = -45
MAX_COMBO_KEEP_PCT: Final = 75   # no stack of gifts may make the series unbreakable


class RhythmRuleError(ValueError):
    pass


def perk(perk_id: str) -> Perk:
    try:
        return _PERK_BY_ID[perk_id]
    except KeyError as exc:
        raise RhythmRuleError("unknown rune gift") from exc


def new_perks() -> dict:
    """Live state of the gifts of one run; persisted next to the run row."""
    return {"owned": {}, "shield": 0, "ebb": 0, "bloody": 0, "miss_debt": 0, "recovery": 0, "revive": 0, "weather": 0}


def normalize_perks(value) -> dict:
    value = value if isinstance(value, dict) else {}
    result = new_perks()
    owned = value.get("owned") if isinstance(value.get("owned"), dict) else {}
    result["owned"] = {key: max(0, int(count)) for key, count in owned.items()
                       if key in _PERK_BY_ID and int(count) > 0}
    for key in ("shield", "ebb", "bloody", "miss_debt", "recovery", "revive"):
        result[key] = max(0, int(value.get(key, 0) or 0))
    result["recovery"] = min(3, result["recovery"])
    result["revive"] = min(BASE_HEALTH, result["revive"])
    result["weather"] = 1 if value.get("weather") else 0   # derived from the run's ruleset by the service
    return result


def _total(perks: dict, field: str) -> int:
    return sum(getattr(_PERK_BY_ID[key], field) * count for key, count in perks["owned"].items())


def _any(perks: dict, field: str) -> bool:
    return any(getattr(_PERK_BY_ID[key], field) for key in perks["owned"])


def expected_rune(seed: bytes, signal_no: int) -> str:
    """A deterministic server-side sequence; seed never goes to the client."""
    if signal_no < 1:
        raise RhythmRuleError("signal number must be positive")
    digest = hmac.new(seed, f"rune:{signal_no}".encode(), hashlib.sha256).digest()
    return RUNES[digest[0] % len(RUNES)]


def chunk_for_signal(signal_no: int) -> int:
    if signal_no < 1:
        raise RhythmRuleError("signal number must be positive")
    return (signal_no - 1) // CHUNK_SIZE


def draft_pending(*, next_signal_no: int, picks: int) -> bool:
    """One gift is owed for every finished chunk; the clock is paused until taken."""
    return picks < chunk_for_signal(next_signal_no)


def _eligible(item: Perk, *, health: int, perks: dict) -> bool:
    if item.filler:
        return True
    if perks["owned"].get(item.id, 0) >= item.max_stack:
        return False
    if item.sacrifice and health <= item.sacrifice:
        return False
    if item.recovery_signals and health <= 1:
        return False
    if item.heal and health >= MAX_HEALTH:
        return False
    if item.id == "blood_price":
        return health >= 3
    if item.cap_health:
        return health > item.cap_health
    return True


def ruleset_number(version: str | None) -> int:
    """The trailing number of "rhythm-v2-rules-N"; a missing or unreadable version means the current rules."""
    try:
        return int(str(version if version is not None else RULESET_VERSION).rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return ruleset_number(None)


def in_pool(item: Perk, ruleset_version: str | None) -> bool:
    """A run offers only the gifts that existed in its ruleset, so a new gift never reshuffles a run in progress."""
    return item.since <= ruleset_number(ruleset_version)


def perk_offers(seed: bytes, draft_no: int, *, health: int, perks: dict, ruleset_version: str | None = None) -> tuple[str, ...]:
    """Three repeatable offers for one draft, always including a safe gift."""
    if draft_no < 1:
        raise RhythmRuleError("draft number must be positive")
    def ranking(items):
        return sorted(
            (item for item in items if _eligible(item, health=health, perks=perks)),
            key=lambda item: hmac.new(seed, f"perk:{draft_no}:{item.id}".encode(), hashlib.sha256).digest(),
        )
    ranked = ranking(item for item in PERKS if not item.filler and in_pool(item, ruleset_version))
    chosen = ranked[:3]
    if len(chosen) < 3:
        chosen += ranking(item for item in PERKS if item.filler)[:3 - len(chosen)]
    if not chosen:
        raise RhythmRuleError("no rune gift can be offered")
    safe = next((item for item in ranked if item.kind == "safe"), None)
    if safe and not any(item.kind == "safe" for item in chosen):
        chosen[-1] = safe
    return tuple(item.id for item in chosen)


def apply_perk(perk_id: str, *, health: int, perks: dict) -> tuple[int, dict]:
    item = perk(perk_id)
    if not _eligible(item, health=health, perks=perks):
        raise RhythmRuleError("this rune gift cannot be taken now")
    perks = {**perks, "owned": dict(perks["owned"])}
    perks["owned"][item.id] = perks["owned"].get(item.id, 0) + 1
    health = min(MAX_HEALTH, health + item.heal) - item.sacrifice
    perks["shield"] += item.shield
    perks["ebb"] = max(perks["ebb"], item.ebb)
    perks["bloody"] = max(perks["bloody"], item.bloody)
    perks["revive"] = max(perks.get("revive", 0), item.revive)
    if item.cap_health:
        health = min(health, item.cap_health)
    if item.id == "blood_price":
        health -= 1
    return health, perks


def pace_percent(signal_no: int, perks: dict | None = None) -> int:
    """Compounding pace: 100% at the start, +8% per finished chunk, plus gifts."""
    pace = 100 * (100 + SPEED_GROWTH_PERCENT) ** chunk_for_signal(signal_no) // 100 ** chunk_for_signal(signal_no)
    return max(100, pace + (_total(perks, "pace_pct") if perks else 0))


def speed_percent(signal_no: int, perks: dict | None = None) -> int:
    return pace_percent(signal_no, perks)


def min_window_ms(signal_no: int) -> int:
    over = max(0, chunk_for_signal(signal_no) - FLOOR_FALL_START_CHUNK)
    return max(HARD_FLOOR_MS, MIN_WINDOW_MS - over * FLOOR_FALL_MS_PER_CHUNK)


def window_ms(signal_no: int, perks: dict | None = None) -> int:
    perks = perks or new_perks()
    raw = BASE_WINDOW_MS * 100 // pace_percent(signal_no, perks)
    percent = max(MIN_WINDOW_PCT, _total(perks, "window_pct") + (40 if perks["ebb"] > 0 else 0) + (25 if perks.get("recovery", 0) > 0 else 0)
                  + weather.window_pct(signal_no, perks))
    return max(min_window_ms(signal_no), raw * (100 + percent) // 100)


def initial_health() -> int:
    return BASE_HEALTH


def situational_bonus_pct(perks: dict, *, combo_before: int, health: int) -> int:
    """Score bonus that depends on the moment: the cadence tap, low health and a long unbroken series."""
    bonus = sum(item.cadence_bonus_pct * count for key, count in perks["owned"].items()
                if (item := _PERK_BY_ID[key]).cadence_every and (combo_before + 1) % item.cadence_every == 0)
    bonus += sum(item.streak_bonus_pct * count for key, count in perks["owned"].items()
                 if (item := _PERK_BY_ID[key]).streak_bonus_pct and combo_before >= item.streak_bonus_from)
    return bonus + (_total(perks, "low_health_bonus_pct") if health <= 2 else 0)


def combo_after_error(combo: int, perks: dict) -> int:
    """The series after a mistake: zero, or the share an Anchor lets survive."""
    return combo * min(MAX_COMBO_KEEP_PCT, _total(perks, "combo_keep_pct")) // 100


def score_for_correct(*, elapsed_ms: int, allowed_window_ms: int, combo_before: int,
                      perks: dict | None = None, health: int = BASE_HEALTH, signal_no: int | None = None) -> int:
    perks = perks or new_perks()
    if elapsed_ms < 0 or elapsed_ms > allowed_window_ms:
        raise RhythmRuleError("correct score requires an in-window tap")
    # Exact taps are worth more, but combo growth is bounded rather than
    # exponentially exploding the leaderboard.
    tier = 0 if elapsed_ms * 3 <= allowed_window_ms else 1 if elapsed_ms * 3 <= allowed_window_ms * 2 else 2
    timing = (100, 70, 45)[tier]
    if _any(perks, "sharp_eye"):
        timing = timing * 3 // 2 if tier == 0 else timing // 2 if tier == 2 else timing
    step = COMBO_STEP + _total(perks, "combo_step")
    cap = COMBO_CAP + _total(perks, "combo_cap")
    raw = (timing + min(cap, combo_before * step)) * (3 if perks["bloody"] > 0 else 1)
    bonus = situational_bonus_pct(perks, combo_before=combo_before, health=health)
    percent = max(MIN_SCORE_PCT, _total(perks, "score_pct") + bonus + weather.score_pct(signal_no, perks))
    return max(1, raw * (100 + percent) // 100)


def after_correct(perks: dict, *, health: int, streak_after: int, signal_no: int | None = None) -> tuple[int, dict]:
    perks = dict(perks)
    perks["bloody"] = max(0, perks["bloody"] - 1)
    perks["ebb"] = max(0, perks["ebb"] - 1)
    perks["recovery"] = max(0, perks.get("recovery", 0) - 1)
    every = min((item.regen_every for key in perks["owned"] if (item := _PERK_BY_ID[key]).regen_every), default=0)
    if weather.regen_every(signal_no, perks):
        every = min(every or weather.SPRING_EVERY, weather.regen_every(signal_no, perks))
    if every and streak_after > 0 and streak_after % every == 0:
        health = min(MAX_HEALTH, health + 1)
    recharge = min((item.shield_every for key in perks["owned"] if (item := _PERK_BY_ID[key]).shield_every), default=0)
    cap = max((item.shield_cap for key in perks["owned"] if (item := _PERK_BY_ID[key]).shield_every), default=0)
    if recharge and streak_after > 0 and streak_after % recharge == 0 and perks["shield"] < cap:
        perks["shield"] += 1
    return health, perks


def after_error(*, health: int, perks: dict, timed_out: bool, signal_no: int | None = None) -> tuple[int, dict]:
    """A shield eats the whole mistake; otherwise gifts decide how deep it cuts."""
    perks = dict(perks)
    perks["ebb"] = max(0, perks["ebb"] - 1)
    perks["recovery"] = max(0, perks.get("recovery", 0) - 1)
    if perks["shield"] > 0:
        perks["shield"] -= 1
        return health, perks
    if timed_out and _any(perks, "timeout_free"):
        # Waiting is never free for long: every second miss still costs a heart.
        perks["miss_debt"] += 1
        if perks["miss_debt"] % 2 == 1:
            return health, perks
    damage = 1 + _total(perks, "damage_extra") + (0 if timed_out else _total(perks, "wrong_extra")) + weather.damage_extra(signal_no, perks)
    remaining = max(0, health - damage)
    if remaining == 0 and perks.get("revive", 0) > 0:
        remaining, perks["revive"] = perks["revive"], 0   # the Phoenix: once, the run goes on
    if remaining > 0:
        perks['recovery'] = max(perks['recovery'], max((item.recovery_signals for key in perks['owned'] if (item := _PERK_BY_ID[key]).recovery_signals), default=0))
    return remaining, perks


def owned_gifts(perks: dict) -> list[dict]:
    return [{"id": key, "name": _PERK_BY_ID[key].name, "count": count} for key, count in perks["owned"].items()]
