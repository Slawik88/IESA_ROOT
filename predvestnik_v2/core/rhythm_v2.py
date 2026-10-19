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

from dataclasses import dataclass
import hashlib
import hmac
from typing import Final, Literal


RULESET_VERSION: Final = "rhythm-v2-rules-6"
Mode = Literal["normal", "augments"]  # "augments" is only a legacy alias of "normal"
PerkKind = Literal["safe", "boost", "risk"]
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


@dataclass(frozen=True)
class Perk:
    id: str
    kind: PerkKind
    name: str
    bonus: str
    cost: str
    max_stack: int = 2
    filler: bool = False        # only offered when fewer than three real gifts remain
    # Permanent per-copy effects (summed over copies):
    window_pct: int = 0
    score_pct: int = 0
    pace_pct: int = 0
    damage_extra: int = 0       # extra hearts lost by every mistake
    wrong_extra: int = 0        # extra hearts lost by a wrong rune only
    combo_step: int = 0         # extra score per combo step (base 4)
    combo_cap: int = 0          # extra combo bonus cap (base 80)
    regen_every: int = 0        # +1 heart every N correct taps in a row
    timeout_free: bool = False  # every second missed signal costs no heart
    sharp_eye: bool = False     # exact taps pay more, slow taps pay less
    cadence_every: int = 0     # periodic scoring within an unbroken combo
    cadence_bonus_pct: int = 0
    low_health_bonus_pct: int = 0
    recovery_signals: int = 0  # wider windows after paid health loss, not shields
    sacrifice: int = 0        # hearts paid immediately on selection
    # One-off effects applied when the gift is taken:
    heal: int = 0
    shield: int = 0
    ebb: int = 0                # signals with a wider window
    bloody: int = 0             # taps with triple score
    cap_health: int = 0         # health is cut to this value (0 = no cut)


# Every gift changes authoritative fields and always carries a price.
PERKS: Final[tuple[Perk, ...]] = (
    Perk("iron_heart", "safe", "Железное сердце", "+2 сердца сразу", "окно нажатия уже на 10%", window_pct=-10, heal=2),
    Perk("stone_shield", "safe", "Каменный щит", "гасит одну ошибку", "очки ниже на 12%", score_pct=-12, shield=1),
    Perk("tailwind", "safe", "Попутный ветер", "окно нажатия шире на 18%", "очки ниже на 18%", window_pct=18, score_pct=-18),
    Perk("vampire", "safe", "Вампир", "+1 сердце за каждые 15 верных подряд", "очки ниже на 10%", score_pct=-10, regen_every=15),
    Perk("ebb_tide", "safe", "Отлив", "следующие 12 тактов окно шире на 40%", "темп выше на 8% навсегда", pace_pct=8, ebb=12),
    Perk("gold_vein", "boost", "Золотая жила", "очки выше на 35%", "каждая ошибка отнимает на сердце больше", score_pct=35, damage_extra=1),
    Perk("sprint", "boost", "Спринт", "очки выше на 30%", "темп выше на 12%", score_pct=30, pace_pct=12),
    Perk("echo_chain", "boost", "Цепь эха", "серия растёт вдвое быстрее и копит больше", "окно нажатия уже на 8%", window_pct=-8, combo_step=4, combo_cap=80),
    Perk("steady_hand", "boost", "Твёрдая рука", "пропущенные такты вдвое реже отнимают сердце", "неверная руна отнимает ещё одно сердце", max_stack=1, timeout_free=True, wrong_extra=1),
    Perk("sharp_eye", "boost", "Меткий глаз", "точные нажатия дают в 1,5 раза больше очков", "медленные нажатия дают вдвое меньше", max_stack=1, sharp_eye=True),
    Perk("gambit", "risk", "Ставка", "очки выше на 30%", "окно нажатия уже на 12%", score_pct=30, window_pct=-12),
    Perk("blood_price", "risk", "Цена крови", "тройные очки на 20 верных нажатий", "теряешь сердце сразу", max_stack=1, bloody=20),
    Perk("metronome", "boost", "Метроном", "каждое 4-е нажатие в серии: +115% очков", "остальные нажатия: −15% очков", max_stack=1, score_pct=-15, cadence_every=4, cadence_bonus_pct=130),
    Perk("last_spark", "risk", "Последняя искра", "при 1–2 сердцах: +25% очков", "−1 сердце сразу; при 3+ сердцах: −8% очков", max_stack=1, score_pct=-8, low_health_bonus_pct=33, sacrifice=1),
    Perk("second_wind", "safe", "Второе дыхание", "после потери сердца окно шире на 25% в течение 3 тактов", "очки ниже на 12%", max_stack=1, score_pct=-12, recovery_signals=3),
    Perk("breather", "safe", "Передышка", "+1 сердце", "темп выше на 5%", max_stack=99, pace_pct=5, heal=1, filler=True),
    Perk("glass_cannon", "risk", "Стеклянная пушка", "очки выше на 60%", "здоровье падает до 2 сердец", max_stack=1, score_pct=60, cap_health=2),
)
_PERK_BY_ID: Final = {item.id: item for item in PERKS}
_NEW_PERK_IDS: Final = frozenset({"metronome", "last_spark", "second_wind"})
assert len(_PERK_BY_ID) == len(PERKS) == 17

COMBO_STEP: Final = 4
COMBO_CAP: Final = 80
MIN_SCORE_PCT: Final = -60
MIN_WINDOW_PCT: Final = -45


class RhythmRuleError(ValueError):
    pass


def perk(perk_id: str) -> Perk:
    try:
        return _PERK_BY_ID[perk_id]
    except KeyError as exc:
        raise RhythmRuleError("unknown rune gift") from exc


def new_perks() -> dict:
    """Live state of the gifts of one run; persisted next to the run row."""
    return {"owned": {}, "shield": 0, "ebb": 0, "bloody": 0, "miss_debt": 0, "recovery": 0}


def normalize_perks(value) -> dict:
    value = value if isinstance(value, dict) else {}
    result = new_perks()
    owned = value.get("owned") if isinstance(value.get("owned"), dict) else {}
    result["owned"] = {key: max(0, int(count)) for key, count in owned.items()
                       if key in _PERK_BY_ID and int(count) > 0}
    for key in ("shield", "ebb", "bloody", "miss_debt", "recovery"):
        result[key] = max(0, int(value.get(key, 0) or 0))
    result["recovery"] = min(3, result["recovery"])
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


def perk_offers(seed: bytes, draft_no: int, *, health: int, perks: dict, legacy: bool = False) -> tuple[str, ...]:
    """Three repeatable offers for one draft, always including a safe gift."""
    if draft_no < 1:
        raise RhythmRuleError("draft number must be positive")
    def ranking(items):
        return sorted(
            (item for item in items if _eligible(item, health=health, perks=perks)),
            key=lambda item: hmac.new(seed, f"perk:{draft_no}:{item.id}".encode(), hashlib.sha256).digest(),
        )
    ranked = ranking(item for item in PERKS if not item.filler and (not legacy or item.id not in _NEW_PERK_IDS))
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
    percent = max(MIN_WINDOW_PCT, _total(perks, "window_pct") + (40 if perks["ebb"] > 0 else 0) + (25 if perks.get("recovery", 0) > 0 else 0))
    return max(min_window_ms(signal_no), raw * (100 + percent) // 100)


def initial_health() -> int:
    return BASE_HEALTH


def score_for_correct(*, elapsed_ms: int, allowed_window_ms: int, combo_before: int,
                      perks: dict | None = None, health: int = BASE_HEALTH) -> int:
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
    bonus = sum(item.cadence_bonus_pct * count for key, count in perks['owned'].items()
                if (item := _PERK_BY_ID[key]).cadence_every and (combo_before + 1) % item.cadence_every == 0)
    if health <= 2:
        bonus += _total(perks, 'low_health_bonus_pct')
    percent = max(MIN_SCORE_PCT, _total(perks, "score_pct") + bonus)
    return max(1, raw * (100 + percent) // 100)


def after_correct(perks: dict, *, health: int, streak_after: int) -> tuple[int, dict]:
    perks = dict(perks)
    perks["bloody"] = max(0, perks["bloody"] - 1)
    perks["ebb"] = max(0, perks["ebb"] - 1)
    perks["recovery"] = max(0, perks.get("recovery", 0) - 1)
    every = min((item.regen_every for key in perks["owned"] if (item := _PERK_BY_ID[key]).regen_every), default=0)
    if every and streak_after > 0 and streak_after % every == 0:
        health = min(MAX_HEALTH, health + 1)
    return health, perks


def after_error(*, health: int, perks: dict, timed_out: bool) -> tuple[int, dict]:
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
    damage = 1 + _total(perks, "damage_extra") + (0 if timed_out else _total(perks, "wrong_extra"))
    remaining = max(0, health - damage)
    if remaining > 0:
        perks['recovery'] = max(perks['recovery'], max((item.recovery_signals for key in perks['owned'] if (item := _PERK_BY_ID[key]).recovery_signals), default=0))
    return remaining, perks


def owned_gifts(perks: dict) -> list[dict]:
    return [{"id": key, "name": _PERK_BY_ID[key].name, "count": count} for key, count in perks["owned"].items()]
