"""Сроки в командах: «5д», «2ч», «30м», «1н», «1д12ч», «5 дней», «навсегда»."""
from __future__ import annotations

import re
from datetime import timedelta

FOREVER = "forever"
MAX_DAYS = 366   # дольше Telegram сам считает вечным, а в базе срок истёк бы: для вечного есть «навсегда»
MAX_SECONDS = MAX_DAYS * 86400


class TooLong(ValueError):
    """Срок дольше года: слишком большие числа ломали запись в базу и чтение варнов."""

_UNITS = {
    "м": 60, "мин": 60, "минута": 60, "минуты": 60, "минут": 60, "m": 60,
    "ч": 3600, "час": 3600, "часа": 3600, "часов": 3600, "h": 3600,
    "д": 86400, "дн": 86400, "день": 86400, "дня": 86400, "дней": 86400, "d": 86400,
    "н": 604800, "нед": 604800, "неделя": 604800, "недели": 604800, "недель": 604800, "w": 604800,
    "мес": 2592000, "месяц": 2592000, "месяца": 2592000, "месяцев": 2592000,
}
_FOREVER_WORDS = {"навсегда", "вечно", "forever", "∞"}
_PART = re.compile(r"(\d+)\s*([a-zа-яё]+)", re.IGNORECASE)
_HEAD = re.compile(r"^\s*((?:\d+\s*[a-zа-яё]+\s*)+)", re.IGNORECASE)
_DECIMAL = re.compile(r"^\s*\d+[.,]\d+\s*[a-zа-яё]+", re.IGNORECASE)   # «1.5ч»: дробные сроки не поддерживаются


def split_duration(text: str) -> tuple[timedelta | str | None, str]:
    """Срок в начале значений -> (срок, остаток). Срок None — не указан.

    Возвращает FOREVER для «навсегда». Неизвестная единица («5х») — ValueError.
    """
    t = text.strip()
    first = t.split(maxsplit=1)
    if first and first[0].lower().strip(",") in _FOREVER_WORDS:
        return FOREVER, first[1].strip(" ,") if len(first) > 1 else ""
    bad = _DECIMAL.match(t)
    if bad:
        raise ValueError(bad.group(0).strip())
    m = _HEAD.match(t)
    if not m:
        return None, t
    total = 0
    consumed_to = 0
    for part in _PART.finditer(m.group(1)):
        unit = part.group(2).lower().replace("ё", "е")
        if unit not in _UNITS:
            if total:
                break   # дальше уже причина: «5д спам»
            raise ValueError(part.group(0))
        total += int(part.group(1)) * _UNITS[unit]
        consumed_to = part.end()
        if total > MAX_SECONDS:
            raise TooLong(m.group(1).strip())
    if not consumed_to:
        return None, t
    if not total:   # «0д», «0м»: срок указан, но нулевой, — не превращаем в вечный
        raise ValueError(t[:consumed_to].strip())
    return timedelta(seconds=total), t[consumed_to:].strip(" ,")


def human(td: timedelta | str | None) -> str:
    if td is None or td == FOREVER:
        return "навсегда"
    s = int(td.total_seconds())
    parts = []
    for size, name in ((604800, "н"), (86400, "д"), (3600, "ч"), (60, "м")):
        if s >= size:
            parts.append(f"{s // size}{name}")
            s %= size
    return " ".join(parts) or "меньше минуты"
