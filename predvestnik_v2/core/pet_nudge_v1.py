"""Gentle pet reminder: rules and copy. Pure, no SQL or clock.

A player who opens the Mini App several days in a row without looking at the
pets gets one soft card about them, with a direct button. It is rare by design:
at most MAX_SHOWS times per account, never twice within COOLDOWN_DAYS, and any
visit to the pets screen resets the count.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta

STREAK_DAYS = 4        # app days in a row without the pets screen, today included
COOLDOWN_DAYS = 14
MAX_SHOWS = 3


@dataclass(frozen=True)
class NudgeState:
    last_day: date | None = None
    last_day_pets: bool = False
    streak: int = 0
    shown_on: date | None = None
    shows: int = 0


def visit(state: NudgeState, day: date, pets: bool) -> NudgeState:
    """One app visit. `pets` means the visit opened the pets screen.

    Mirrors the upsert in infrastructure/repositories/pet_nudge_v1.py.
    """
    last = state.last_day
    if pets:
        streak = 0
    elif last == day or (last is not None and last > day):
        streak = state.streak
    elif last == day - timedelta(days=1):
        streak = state.streak + 1
    else:
        streak = 1
    same = last is not None and last >= day
    return replace(state, streak=streak,
                   last_day_pets=(state.last_day_pets or pets) if same else pets,
                   last_day=max(last, day) if last is not None else day)


def due(state: NudgeState, day: date) -> bool:
    return (state.streak >= STREAK_DAYS and not state.last_day_pets and state.shows < MAX_SHOWS
            and (state.shown_on is None or state.shown_on <= day - timedelta(days=COOLDOWN_DAYS)))


TILES_TRAIL = (
    {"icon": "🎒", "title": "Походы", "text": "пока вы заняты, питомец гуляет сам и приносит находки"},
    {"icon": "🧭", "title": "Вылазка", "text": "семь развилок — вы решаете, куда свернуть"},
    {"icon": "🛡️", "title": "Экипировка", "text": "пять слотов, чтобы собрать своего героя"},
)
TILES_CLASSIC = (
    {"icon": "🎒", "title": "Занятия", "text": "пока вы заняты, питомец гуляет сам и приносит награды"},
    {"icon": "📈", "title": "Рост", "text": "с каждым днём питомец сильнее и ближе к вам"},
    {"icon": "📖", "title": "Бестиарий", "text": "соберите всех — у каждого свой нрав"},
)


def card(pet: dict | None, trail: bool) -> dict:
    """What the sheet says. `pet` is the player's oldest companion or None."""
    tiles = list(TILES_TRAIL if trail else TILES_CLASSIC)
    if not pet:
        return {"icon": "🐾", "title": "Здесь живут питомцы",
                "lead": "Маленькие спутники, которые ходят в путь вместо вас. Первого можно найти в сундуке.",
                "tiles": tiles, "action": "Посмотреть питомцев"}
    name = pet["name"]
    return {"icon": pet["icon"], "title": f"{name} скучает по вам",
            "lead": f"Пара минут — и {name} снова в пути. Загляните, когда будет настроение.",
            "tiles": tiles, "action": "Проведать питомца"}
