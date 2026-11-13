"""Бот в личных переписках игрока (Telegram Business, S24): чистые правила без базы и Telegram.

Игрок с Telegram Premium подключает бота в «Настройки → Telegram для бизнеса → Чат-боты». После этого бот получает
сообщения из его личных переписок. Бот действует только по команде самого игрока («бот …» его же сообщением) и только
в переписке, где игрок сам включил его командой «бот вкл». Сообщения собеседника бот не читает и не хранит.
"""
from __future__ import annotations

import re

SWITCH = "group:business"        # выключатель «Бизнес-режим» в «Функции» (строка = выключено везде)
PREFIX = "бот"
HANDLED_KEEP_HOURS = 48          # сколько помнить номера уже выполненных команд (повтор обновления Telegram не повторяет действие)
CHOICE_MAX = 6                   # «бот выбери чай или кофе или сок»: не больше вариантов
CHOICE_LEN = 60
ALWAYS = frozenset({"on", "help", "remote"})   # работают и в переписке, где бот выключен (ответ уходит игроку в личку)

# Слова команды → действие. Совпало несколько — берётся самое длинное («кинь кубик», а не «кинь»).
COMMANDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("on", ("вкл", "включить", "включи", "включен")),
    ("off", ("выкл", "выключить", "выключи", "выключен")),
    ("help", ("помощь", "команды", "что умеешь")),
    ("remote", ("пульт", "меню")),
    ("games", ("сыграть", "игра", "игры", "дуэль")),
    ("dice", ("кубик", "кости", "кинь кубик", "брось кубик")),
    ("choose", ("выбери",)),
    ("compat", ("совместимость", "шипирить")),
    ("card", ("визитка", "карточка")),
    ("invite", ("пригласить", "приглашение", "позвать")),
    ("transfer", ("перевод", "перевести", "передать")),
)


def parse(text: str | None) -> tuple[str, str] | None:
    """«бот кубик» → ("dice", ""); «бот выбери чай или кофе» → ("choose", "чай или кофе"). Не команда — None."""
    clean = " ".join(str(text or "").split())
    low = clean.lower().replace("ё", "е")
    if low.rstrip("!?. ") == PREFIX:   # просто «бот» — пульт в личке, но только там, где бот включён («бот пульт» — везде)
        return ("remote_here", "")
    if not low.startswith(PREFIX + " "):
        return None
    rest, rest_raw = low[len(PREFIX) + 1:].lstrip(" ,"), clean[len(PREFIX) + 1:].lstrip(" ,")
    best: tuple[str, str, int] | None = None
    for action, words in COMMANDS:
        for word in words:
            if rest == word or rest.startswith(word + " ") or rest.startswith(word + ","):
                if best is None or len(word) > best[2]:
                    best = (action, rest_raw[len(word):].strip(" ,"), len(word))
    return (best[0], best[1]) if best else None


def choices(args: str) -> list[str]:
    """«чай или кофе, сок» → ["чай", "кофе", "сок"]; меньше двух вариантов — пустой список."""
    parts = [p.strip(" ?!.") for p in re.split(r"\s+или\s+|,|/", str(args or ""), flags=re.IGNORECASE)]
    found = [p[:CHOICE_LEN] for p in parts if p]
    return found[:CHOICE_MAX] if len(found) >= 2 else []
