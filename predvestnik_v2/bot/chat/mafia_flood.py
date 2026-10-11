"""Сколько секунд Telegram просит подождать после лимита запросов: планировщик Мафии учитывает это при повторе."""
from __future__ import annotations

_wait = 0.0


def note(exc: Exception) -> None:
    """Запомнить паузу из ошибки лимита (у остальных ошибок её нет)."""
    global _wait
    _wait = max(_wait, float(getattr(exc, "retry_after", 0) or 0))


def take() -> float:
    """Забрать запомненную паузу и обнулить."""
    global _wait
    value, _wait = _wait, 0.0
    return value
