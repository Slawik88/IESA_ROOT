"""Authoritative, dependency-free rules for the approved endless Rune Rhythm.

This module deliberately knows nothing about the legacy Reconstruction campaign,
rewards, pets or client-side animation.  Its output is stored and enforced by
the service layer; a browser only renders it and submits a rune tap.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from typing import Final, Iterable, Literal


RULESET_VERSION: Final = "rhythm-v2-rules-3"
Mode = Literal["normal", "augments"]
Polarity = Literal["positive", "negative"]
RUNES: Final = ("left", "center", "right")
CHUNK_SIZE: Final = 30
BASE_HEALTH: Final = 5
MIN_WINDOW_MS: Final = 180
BASE_WINDOW_MS: Final = 2_000


@dataclass(frozen=True)
class Augmentation:
    id: str
    polarity: Polarity
    name: str
    # A compact, machine-readable modifier set.  Every catalogue entry must
    # change at least one authoritative field; no cosmetic placeholder entries.
    window_pct: int = 0
    health_delta: int = 0
    score_pct: int = 0
    speed_pct: int = 0
    error_damage_delta: int = 0
    grace_every: int = 0


# The full v1 catalogue is available from the first augmentation run.  Values
# are intentionally local to this ruleset version so a future balance update
# cannot rewrite the meaning of an already recorded result.
AUGMENTATIONS: Final[tuple[Augmentation, ...]] = (
    Augmentation("calm_pulse", "positive", "Спокойный пульс", window_pct=14),
    Augmentation("clear_mark", "positive", "Ясная метка", window_pct=10, score_pct=3),
    Augmentation("fourth_chance", "positive", "Четвёртый шанс", grace_every=4),
    Augmentation("spare_heart", "positive", "Запасное сердце", health_delta=1),
    Augmentation("quiet_start", "positive", "Тихий старт", window_pct=8, speed_pct=-4),
    Augmentation("steady_echo", "positive", "Ровное эхо", score_pct=8),
    Augmentation("soft_step", "positive", "Мягкий шаг", window_pct=12, score_pct=-2),
    Augmentation("patient_current", "positive", "Терпеливое течение", speed_pct=-7),
    Augmentation("bright_trace", "positive", "Яркий след", score_pct=11),
    Augmentation("guarded_beat", "positive", "Охранный такт", error_damage_delta=-1),
    Augmentation("long_breath", "positive", "Длинный вдох", window_pct=7, health_delta=1),
    Augmentation("true_tempo", "positive", "Верный темп", score_pct=6, speed_pct=-2),
    Augmentation("silent_guard", "positive", "Тихая защита", grace_every=6),
    Augmentation("resonant_step", "positive", "Резонансный шаг", score_pct=9),
    Augmentation("open_window", "positive", "Открытое окно", window_pct=16, score_pct=-5),
    Augmentation("first_light", "positive", "Первый свет", health_delta=1, score_pct=-3),
    Augmentation("measured_flow", "positive", "Размеренный поток", window_pct=6, speed_pct=-5),
    Augmentation("sure_hand", "positive", "Верная рука", score_pct=5, grace_every=8),
    Augmentation("gentle_rhythm", "positive", "Мягкий ритм", window_pct=9),
    Augmentation("held_line", "positive", "Удержанная линия", error_damage_delta=-1, score_pct=-4),
    Augmentation("narrow_gate", "negative", "Узкие врата", window_pct=-15),
    Augmentation("fragile_heart", "negative", "Хрупкое сердце", health_delta=-1),
    Augmentation("hasty_current", "negative", "Спешное течение", speed_pct=9),
    Augmentation("heavy_mistake", "negative", "Тяжёлая ошибка", error_damage_delta=1),
    Augmentation("dim_trace", "negative", "Тусклый след", score_pct=-12),
    Augmentation("restless_pulse", "negative", "Беспокойный пульс", speed_pct=6, window_pct=-4),
    Augmentation("brittle_combo", "negative", "Хрупкая серия", score_pct=-8),
    Augmentation("short_breath", "negative", "Короткий вдох", window_pct=-9, health_delta=-1),
    Augmentation("cold_mark", "negative", "Холодная метка", window_pct=-11),
    Augmentation("rushing_echo", "negative", "Спешащее эхо", speed_pct=12, score_pct=3),
    Augmentation("sharp_cost", "negative", "Острая цена", error_damage_delta=1, score_pct=4),
    Augmentation("fading_line", "negative", "Гаснущая линия", score_pct=-9),
    Augmentation("broken_guard", "negative", "Сломанная защита", error_damage_delta=1),
    Augmentation("quickened_step", "negative", "Ускоренный шаг", speed_pct=7),
    Augmentation("tight_turn", "negative", "Тесный поворот", window_pct=-12, score_pct=2),
    Augmentation("thin_current", "negative", "Тонкое течение", health_delta=-1, speed_pct=4),
    Augmentation("hollow_beat", "negative", "Пустой такт", score_pct=-10),
    Augmentation("risky_trace", "negative", "Рискованный след", score_pct=5, error_damage_delta=1),
    Augmentation("rapid_fall", "negative", "Быстрый спад", speed_pct=10),
    Augmentation("unforgiving_gate", "negative", "Непрощающие врата", window_pct=-8, error_damage_delta=1),
)

_BY_ID: Final = {item.id: item for item in AUGMENTATIONS}
assert len(_BY_ID) == 40
assert sum(item.polarity == "positive" for item in AUGMENTATIONS) == 20
assert sum(item.polarity == "negative" for item in AUGMENTATIONS) == 20


class RhythmRuleError(ValueError):
    pass


def expected_rune(seed: bytes, signal_no: int) -> str:
    """A deterministic server-side sequence; seed never goes to the client."""
    if signal_no < 1:
        raise RhythmRuleError("signal number must be positive")
    digest = hmac.new(seed, f"rune:{signal_no}".encode(), hashlib.sha256).digest()
    return RUNES[digest[0] % len(RUNES)]


def offers_for_seed(seed: bytes) -> dict[str, tuple[str, ...]]:
    """Choose repeatable 3+3 offers without trusting a client-side random roll."""
    result: dict[str, tuple[str, ...]] = {}
    for polarity in ("positive", "negative"):
        candidates = [item for item in AUGMENTATIONS if item.polarity == polarity]
        ranked = sorted(
            candidates,
            key=lambda item: hmac.new(seed, f"offer:{polarity}:{item.id}".encode(), hashlib.sha256).digest(),
        )
        result[polarity] = tuple(item.id for item in ranked[:3])
    return result


def validate_selection(
    offers: dict[str, Iterable[str]], *, positive: Iterable[str], negative: Iterable[str]
) -> tuple[str, ...]:
    positive_ids, negative_ids = tuple(positive), tuple(negative)
    if len(positive_ids) != 2 or len(set(positive_ids)) != 2:
        raise RhythmRuleError("choose exactly two distinct positive augmentations")
    if len(negative_ids) != 2 or len(set(negative_ids)) != 2:
        raise RhythmRuleError("choose exactly two distinct negative augmentations")
    if set(positive_ids) - set(offers.get("positive", ())):
        raise RhythmRuleError("positive augmentation was not offered for this run")
    if set(negative_ids) - set(offers.get("negative", ())):
        raise RhythmRuleError("negative augmentation was not offered for this run")
    return positive_ids + negative_ids


def modifiers(selected_ids: Iterable[str]) -> dict[str, int]:
    selected = tuple(selected_ids)
    if len(selected) != len(set(selected)) or any(item not in _BY_ID for item in selected):
        raise RhythmRuleError("unknown or duplicated augmentation")
    return {
        field: sum(getattr(_BY_ID[item], field) for item in selected)
        for field in ("window_pct", "health_delta", "score_pct", "speed_pct", "error_damage_delta", "grace_every")
    }


def chunk_for_signal(signal_no: int) -> int:
    if signal_no < 1:
        raise RhythmRuleError("signal number must be positive")
    return (signal_no - 1) // CHUNK_SIZE


def speed_percent(signal_no: int, selected_ids: Iterable[str] = ()) -> int:
    # Linear, visible acceleration.  A human will eventually reach their limit;
    # the run itself has no artificial final wave.
    # Long chunks make the first minute readable; each new chunk is still
    # visibly faster, but the curve no longer jolts after a handful of taps.
    return max(100, 100 + chunk_for_signal(signal_no) * 5 + modifiers(selected_ids)["speed_pct"])


def window_ms(signal_no: int, selected_ids: Iterable[str] = ()) -> int:
    mod = modifiers(selected_ids)
    raw = BASE_WINDOW_MS * 100 // speed_percent(signal_no, selected_ids)
    calculated = max(MIN_WINDOW_MS, raw * (100 + mod["window_pct"]) // 100)
    return calculated


def initial_health(selected_ids: Iterable[str] = ()) -> int:
    return max(1, BASE_HEALTH + modifiers(selected_ids)["health_delta"])


def score_for_correct(*, elapsed_ms: int, allowed_window_ms: int, combo_before: int,
                      selected_ids: Iterable[str] = ()) -> int:
    if elapsed_ms < 0 or elapsed_ms > allowed_window_ms:
        raise RhythmRuleError("correct score requires an in-window tap")
    # Exact taps are worth more, but combo growth is bounded rather than
    # exponentially exploding the leaderboard.
    timing = 100 if elapsed_ms * 3 <= allowed_window_ms else 70 if elapsed_ms * 3 <= allowed_window_ms * 2 else 45
    combo_bonus = min(80, combo_before * 4)
    raw = timing + combo_bonus
    return max(1, raw * (100 + modifiers(selected_ids)["score_pct"]) // 100)


def error_damage(*, correct_streak: int, selected_ids: Iterable[str] = ()) -> int:
    mod = modifiers(selected_ids)
    # A grace is earned only by server-confirmed correct taps, never by a
    # counter submitted by the client.
    if mod["grace_every"] and correct_streak and correct_streak % mod["grace_every"] == 0:
        return 0
    return max(1, 1 + mod["error_damage_delta"])
