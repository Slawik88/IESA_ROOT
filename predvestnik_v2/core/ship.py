"""«Шипперим»: настройки и чистые функции без зависимости от бота и базы.

Пара выбирается случайно на каждый вызов, но процент совместимости пары
детерминирован (hash двух id в отсортированном порядке): одна и та же пара
всегда получает один процент и один вердикт. Числа здесь — константы продукта:
менять только осознанно (CLEAN_CODE 2.4).
"""
from __future__ import annotations

import hashlib

# Пауза между шиппингами: у игрока и у чата в целом (защита от спама).
COOLDOWN_USER_SECONDS = 90
COOLDOWN_CHAT_SECONDS = 30

# Кого считаем «недавно активным» для случайной пары.
ACTIVE_DAYS = 14

# Если в чате меньше стольких кандидатов, повтор пары допустим (иначе выбор невозможен).
MIN_POOL_FOR_UNIQUE = 4

# Одна и та же пара не выпадает в чате повторно в течение этого срока.
RECENT_PAIR_MINUTES = 30

# Ступени процента совместимости: верхняя граница, нижняя, ключ категории текстов.
# Категории с ключами живут в bot/chat/ship_texts/compat.py.
PERCENT_BUCKETS: tuple[tuple[int, int, str], ...] = (
    (96, 100, "compat_96_100"),
    (86, 95, "compat_86_95"),
    (71, 85, "compat_71_85"),
    (56, 70, "compat_56_70"),
    (41, 55, "compat_41_55"),
    (26, 40, "compat_26_40"),
    (11, 25, "compat_11_25"),
    (0, 10, "compat_0_10"),
)

_PERCENT_SALT = "ship-v1"


def compatibility_percent(user_a: int, user_b: int) -> int:
    """Стабильный процент пары: одинаковые два игрока — всегда одно число 0–100."""
    low, high = sorted((int(user_a), int(user_b)))
    digest = hashlib.sha256(f"{_PERCENT_SALT}:{low}:{high}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % 101


def percent_bucket_key(percent: int) -> str:
    """Ключ категории текстов для процента; вне 0–100 — ошибка значения."""
    if not 0 <= percent <= 100:
        raise ValueError(f"percent out of range: {percent}")
    for low, high, key in PERCENT_BUCKETS:
        if low <= percent <= high:
            return key
    raise ValueError(f"percent has no bucket: {percent}")
