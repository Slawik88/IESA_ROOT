"""
items/registry.py — единый реестр предметов PredvestnikBot.

Цель: заменить dict-литерал ITEM_METADATA в shared_prices.py
на типизированные объекты ItemDef с валидацией при старте.

Миграция постепенная:
  • На первом этапе items/equipment.py регистрирует только 5 образцов.
  • shared_prices.ITEM_METADATA продолжает работать для остальных предметов.
  • Итог: get_item_display_info() в конечном счёте заглянет сначала в реестр.

Использование:
    from items.registry import get, register, all_items, by_rarity, gacha_pool
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ─── Перечисления ─────────────────────────────────────────────────────────────

class ItemSlot(str, Enum):
    """Слот экипировки.  None-like → не экипируемый (cosmetic / consumable)."""
    WEAPON   = "weapon"    # оружие — влияет на ATK
    ARMOR    = "armor"     # броня  — влияет на DEF
    ARTIFACT = "artifact"  # артефакт — смешанные бонусы
    FRAME    = "frame"     # рамка профиля (косметика)
    FLAIR    = "flair"     # тема оформления (косметика)
    NONE     = "none"      # нет слота (расходники, жетоны и т.д.)


class ItemRarity(str, Enum):
    """Редкость предмета — соответствует системе молитв (гача)."""
    COMMON    = "common"     # ⚪ серый   — 4★
    RARE      = "rare"       # 🔵 синий   — 4★ (устаревш.; заменить на UNCOMMON?)
    EPIC      = "epic"       # 🟣 фиолет  — 5★
    LEGENDARY = "legendary"  # 🟡 золотой — 6★ (лего)
    SPECIAL   = "special"    # 🔴 красный — ивентовые


# ─── Датакласс предмета ───────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class ItemDef:
    """Определение одного предмета в реестре.

    Все поля неизменяемы после создания (frozen=True).
    Используйте register() для добавления предметов в реестр.
    """
    key: str                         # уникальный строковый ключ (совпадает с БД)
    name: str                        # локализованное название
    rarity: ItemRarity               # редкость
    slot: ItemSlot = ItemSlot.NONE   # слот экипировки

    # Боевые характеристики
    atk:       int   = 0
    def_val:   int   = 0
    hp:        int   = 0
    crit_rate: float = 0.0           # дополнение к крит. шансу (0.0–1.0)

    # Мета-данные
    emoji: str = "🗡️"
    desc:  str = ""
    sell_price: int = 0              # цена продажи в Море (0 = нельзя продать)
    in_gacha: bool = True            # появляется в молитвах
    category: str = ""               # машино-читаемая категория (weapon/armor/…)
    readable_category: str = ""      # «Оружие», «Броня» …

    # Опциональные поля для специализированных предметов
    price: int = 0                   # цена в лавке (для косметики, еды и т.д., 0 = не продаётся)
    fatigue: int = 0                 # переполнение усталости питомца (для еды)
    buff_type: str = ""              # тип баффа: atk/def/hp (для зелий)
    buff_amount: int = 0             # размер баффа (для зелий)
    duration_minutes: int = 0        # продолжительность баффа (для зелий)
    boost_minutes: int = 0           # минуты ускорения (для купонов)
    boost_pct: float = 0.0           # процент ускорения (для купонов)
    craft_into: Optional[str] = None # item_key для крафта (для шардов)
    craft_frame: Optional[str] = None # frame_key для крафта (для шардов)
    craft_amount: int = 0            # сколько нужно шардов для крафта
    stars: int = 0                   # количество звёзд (для кристаль-паков)
    crystals: int = 0                # кристаллов в паке
    bonus_pct: int = 0               # бонус % при покупке (для кристаль-паков)
    base_price: int = 0              # базовая цена акции (для облигаций)
    volatility: float = 0.0          # волатильность акции (для облигаций)
    cap_mult: int = 0                # множитель капитализации (для облигаций)


# ─── Внутренний реестр ────────────────────────────────────────────────────────

_registry: dict[str, ItemDef] = {}


# ─── Публичный API ────────────────────────────────────────────────────────────

def register(item: ItemDef) -> ItemDef:
    """Добавить предмет в реестр. Повторная регистрация с тем же ключом вызовет ValueError."""
    if item.key in _registry:
        raise ValueError(f"ItemDef с ключом '{item.key}' уже зарегистрирован.")
    _registry[item.key] = item
    return item


def get(key: str) -> Optional[ItemDef]:
    """Вернуть ItemDef по ключу или None."""
    return _registry.get(key)


def all_items() -> list[ItemDef]:
    """Все зарегистрированные предметы."""
    return list(_registry.values())


def by_rarity(rarity: ItemRarity) -> list[ItemDef]:
    """Предметы указанной редкости."""
    return [i for i in _registry.values() if i.rarity == rarity]


def gacha_pool() -> list[ItemDef]:
    """Предметы, доступные в молитвах (гача)."""
    return [i for i in _registry.values() if i.in_gacha]


__all__ = [
    "ItemDef",
    "ItemSlot",
    "ItemRarity",
    "register",
    "get",
    "all_items",
    "by_rarity",
    "gacha_pool",
]
