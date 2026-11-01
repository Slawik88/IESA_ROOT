"""«Моя статья»: настройки и чистые функции без зависимости от бота и базы (S22).

Статья игрока стабильна на сутки: hash от (user_id, дата) выбирает описание из
банка, поэтому «крутить до красивой» нельзя; повторный вызов в тот же день
показывает ту же статью с новой подводкой и приговором (образец стабильности —
core/retention_v3.py). Числа здесь — константы продукта (CLEAN_CODE 2.4).
"""
from __future__ import annotations

import hashlib
from datetime import date

# Пауза между вызовами: у игрока и у чата (защита от спама).
COOLDOWN_USER_SECONDS = 60
COOLDOWN_CHAT_SECONDS = 30

_SALT = "article-v1"


def daily_description_index(user_id: int, day: date | str, modulo: int) -> int:
    """Стабильный на сутки индекс описания: один игрок в один день — одна статья."""
    if modulo <= 0:
        raise ValueError("modulo must be positive")
    day_key = day.isoformat() if isinstance(day, date) else str(day)
    digest = hashlib.sha256(f"{_SALT}:{int(user_id)}:{day_key}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % modulo
