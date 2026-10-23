"""Chunk weather of the endless Rhythm: fair variety for everybody.

Every second chunk of 20 signals has a character (Calm, Golden beat, Storm, Spring), taken from a
fixed cycle by the chunk number, never from a seed: every player meets the same weather at the
same depth, and the screen announces it one chunk ahead. Weather only shifts the numbers the rules
already have (window, score, damage, regeneration); the gift engine clamps the totals as before.

Mirrored in FastAPI/static/local-games-v1.js (local play); tools/test_local_games_rules.py keeps
both in step.
"""
from __future__ import annotations

from typing import Final

# Runs of these rules carry weather; earlier rulesets never change their meaning.
FIRST_VERSION_NUMBER: Final = 7
SPRING_EVERY: Final = 8

EVENTS: Final = {
    "calm": {"name": "Затишье", "icon": "🌙", "effect": "окно шире на 25%, очки ниже на 20%",
             "window_pct": 25, "score_pct": -20},
    "gold": {"name": "Золотой такт", "icon": "✨", "effect": "очки выше на 50%, ошибка стоит на сердце больше",
             "score_pct": 50, "damage_extra": 1},
    "storm": {"name": "Буря", "icon": "⛈", "effect": "окно уже на 15%, очки выше на 30%",
              "window_pct": -15, "score_pct": 30},
    "spring": {"name": "Родник", "icon": "💧", "effect": f"каждые {SPRING_EVERY} верных подряд — +1 сердце",
               "regen_every": SPRING_EVERY},
}
CYCLE: Final = ("calm", "gold", "storm", "spring")


def has_weather(ruleset_version: str | None) -> bool:
    try:
        return int(str(ruleset_version).rsplit("-", 1)[1]) >= FIRST_VERSION_NUMBER
    except (IndexError, ValueError):
        return False


def event_for_chunk(chunk: int) -> str | None:
    """Odd chunks carry weather (the first gift is taken in calm air); even chunks are plain."""
    if chunk < 1 or chunk % 2 == 0:
        return None
    return CYCLE[(chunk // 2) % len(CYCLE)]


def _event(signal_no: int | None, perks: dict | None) -> dict:
    if not signal_no or signal_no < 1 or not perks or not perks.get("weather"):
        return {}
    key = event_for_chunk((signal_no - 1) // 20)
    return EVENTS[key] if key else {}


def window_pct(signal_no: int | None, perks: dict | None) -> int:
    return int(_event(signal_no, perks).get("window_pct", 0))


def score_pct(signal_no: int | None, perks: dict | None) -> int:
    return int(_event(signal_no, perks).get("score_pct", 0))


def damage_extra(signal_no: int | None, perks: dict | None) -> int:
    return int(_event(signal_no, perks).get("damage_extra", 0))


def regen_every(signal_no: int | None, perks: dict | None) -> int:
    return int(_event(signal_no, perks).get("regen_every", 0))


def describe(chunk: int) -> dict | None:
    key = event_for_chunk(chunk)
    if not key:
        return None
    event = EVENTS[key]
    return {"id": key, "name": event["name"], "icon": event["icon"], "effect": event["effect"]}
