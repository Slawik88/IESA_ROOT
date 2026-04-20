"""
items/__init__.py — инициализация системы предметов.

Импортирует все модули предметов и инициализирует реестр.
"""

# Импортируем реестр первым
from items.registry import get_item_by_key, get_items_by_category, list_all_items

# Импортируем все модули предметов (регистрация происходит при импорте)
from items import (
    crystals,
    shards,
    weapons,
    armors,
    potions,
    coupons,
    frames,
    collectibles,
    quest_rewards,
)

__all__ = [
    "get_item_by_key",
    "get_items_by_category",
    "list_all_items",
]
