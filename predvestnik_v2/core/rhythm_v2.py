"""Authoritative, dependency-free rules for the approved endless Rune Rhythm.

Rune gifts ("рун-дары") replace the old pre-run augmentations: at the end of
every chunk (20 signals) the run pauses and offers three gifts, the player takes one, and
the effect lives inside the run only.  Everyone plays the same ranked mode.

This module deliberately knows nothing about the legacy Reconstruction campaign,
rewards, pets or client-side animation.  Its output is stored and enforced by
the service layer; a browser only renders it and submits a rune tap.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from typing import Final, Literal


RULESET_VERSION: Final = "rhythm-v2-rules-4"
Mode = Literal["normal", "augments"]  # "augments" is only a legacy alias of "normal"
PerkKind = Literal["safe", "boost", "risk"]
RUNES: Final = ("left", "center", "right")
CHUNK_SIZE: Final = 20
SPEED_STEP_PERCENT: Final = 6   # extra speed per finished chunk
BASE_HEALTH: Final = 5
MAX_HEALTH: Final = 7
MIN_WINDOW_MS: Final = 180
BASE_WINDOW_MS: Final = 1_800


@dataclass(frozen=True)
class Perk:
    id: str
    kind: PerkKind
    name: str
    text: str


# Every gift changes an authoritative field of the run; no cosmetic entries.
PERKS: Final[tuple[Perk, ...]] = (
    Perk("second_wind", "safe", "Второе дыхание", "+1 сердце сразу (не больше 7)."),
    Perk("shield", "safe", "Щит", "Полностью гасит следующую ошибку. Можно держать до двух щитов."),
    Perk("slow_tide", "safe", "Отлив", "Следующие 10 тактов окно нажатия шире на 50%."),
    Perk("echo", "boost", "Эхо серии", "Следующая ошибка не обнуляет серию."),
    Perk("golden_streak", "boost", "Золотая серия", "Следующие 12 верных нажатий дают двойные очки."),
    Perk("blood_price", "risk", "Цена крови", "Теряешь 1 сердце, зато следующие 20 верных нажатий дают тройные очки."),
    Perk("gambit", "risk", "Ставка", "До конца забега окно уже на 12%, но все очки на 30% выше."),
)
_PERK_BY_ID: Final = {item.id: item for item in PERKS}
assert len(_PERK_BY_ID) == len(PERKS) == 7

GOLDEN_TAPS: Final = 12
BLOODY_TAPS: Final = 20
SLOW_SIGNALS: Final = 10
MAX_SHIELDS: Final = 2


class RhythmRuleError(ValueError):
    pass


def perk(perk_id: str) -> Perk:
    try:
        return _PERK_BY_ID[perk_id]
    except KeyError as exc:
        raise RhythmRuleError("unknown rune gift") from exc


def new_perks() -> dict[str, int]:
    """Live effect counters of one run; persisted next to the run row."""
    return {"shield": 0, "golden": 0, "bloody": 0, "slow": 0, "echo": 0, "gambit": 0}


def normalize_perks(value) -> dict[str, int]:
    result = new_perks()
    for key in result:
        result[key] = max(0, int((value or {}).get(key, 0)))
    return result


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


def _eligible(perk_id: str, *, health: int, perks: dict[str, int]) -> bool:
    if perk_id == "second_wind":
        return health < MAX_HEALTH
    if perk_id == "shield":
        return perks["shield"] < MAX_SHIELDS
    if perk_id == "echo":
        return perks["echo"] == 0
    if perk_id == "blood_price":
        return health >= 3
    if perk_id == "gambit":
        return perks["gambit"] == 0
    return True


def perk_offers(seed: bytes, draft_no: int, *, health: int, perks: dict[str, int]) -> tuple[str, ...]:
    """Three repeatable offers for one draft, always including a safe gift."""
    if draft_no < 1:
        raise RhythmRuleError("draft number must be positive")
    ranked = sorted(
        (item for item in PERKS if _eligible(item.id, health=health, perks=perks)),
        key=lambda item: hmac.new(seed, f"perk:{draft_no}:{item.id}".encode(), hashlib.sha256).digest(),
    )
    chosen = ranked[:3]
    if not any(item.kind == "safe" for item in chosen):
        chosen[-1] = next(item for item in ranked if item.kind == "safe")
    return tuple(item.id for item in chosen)


def apply_perk(perk_id: str, *, health: int, perks: dict[str, int]) -> tuple[int, dict[str, int]]:
    item = perk(perk_id)
    if not _eligible(item.id, health=health, perks=perks):
        raise RhythmRuleError("this rune gift cannot be taken now")
    perks = dict(perks)
    if item.id == "second_wind":
        health = min(MAX_HEALTH, health + 1)
    elif item.id == "shield":
        perks["shield"] += 1
    elif item.id == "slow_tide":
        perks["slow"] = SLOW_SIGNALS
    elif item.id == "echo":
        perks["echo"] = 1
    elif item.id == "golden_streak":
        perks["golden"] = GOLDEN_TAPS
    elif item.id == "blood_price":
        health -= 1
        perks["bloody"] = BLOODY_TAPS
    elif item.id == "gambit":
        perks["gambit"] = 1
    return health, perks


def speed_percent(signal_no: int) -> int:
    # Linear, visible acceleration.  A human will eventually reach their limit;
    # the run itself has no artificial final wave.
    # Short chunks keep a run from dragging on: every 20 taps the pace is
    # visibly faster, yet the curve never jolts inside a chunk.
    return 100 + chunk_for_signal(signal_no) * SPEED_STEP_PERCENT


def window_ms(signal_no: int, perks: dict[str, int] | None = None) -> int:
    perks = perks or new_perks()
    raw = BASE_WINDOW_MS * 100 // speed_percent(signal_no)
    percent = (50 if perks["slow"] > 0 else 0) - (12 if perks["gambit"] else 0)
    return max(MIN_WINDOW_MS, raw * (100 + percent) // 100)


def initial_health() -> int:
    return BASE_HEALTH


def score_for_correct(*, elapsed_ms: int, allowed_window_ms: int, combo_before: int,
                      perks: dict[str, int] | None = None) -> int:
    perks = perks or new_perks()
    if elapsed_ms < 0 or elapsed_ms > allowed_window_ms:
        raise RhythmRuleError("correct score requires an in-window tap")
    # Exact taps are worth more, but combo growth is bounded rather than
    # exponentially exploding the leaderboard.
    timing = 100 if elapsed_ms * 3 <= allowed_window_ms else 70 if elapsed_ms * 3 <= allowed_window_ms * 2 else 45
    raw = (timing + min(80, combo_before * 4)) * (3 if perks["bloody"] > 0 else 2 if perks["golden"] > 0 else 1)
    return max(1, raw * (130 if perks["gambit"] else 100) // 100)


def after_correct(perks: dict[str, int]) -> dict[str, int]:
    perks = dict(perks)
    perks["golden"] = max(0, perks["golden"] - 1)
    perks["bloody"] = max(0, perks["bloody"] - 1)
    perks["slow"] = max(0, perks["slow"] - 1)
    return perks


def after_error(*, health: int, combo: int, perks: dict[str, int]) -> tuple[int, int, dict[str, int]]:
    """A shield eats the damage, an echo keeps the combo; each is consumed once."""
    perks = dict(perks)
    perks["slow"] = max(0, perks["slow"] - 1)
    if perks["shield"] > 0:
        perks["shield"] -= 1
    else:
        health = max(0, health - 1)
    if perks["echo"] > 0:
        perks["echo"] -= 1
    else:
        combo = 0
    return health, combo, perks
