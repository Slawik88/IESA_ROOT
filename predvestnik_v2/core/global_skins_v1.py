"""Versioned visual-only skins for the current Mini App surfaces."""
from __future__ import annotations

VERSION = "global-skins-v1-2026-09-09"
DEFAULT_SKIN_ID = "default"

SKINS = {
    DEFAULT_SKIN_ID: {
        "name": "Базовый Предвестник",
        "description": "Стандартная спокойная палитра приложения.",
        "css_class": "",
        "asset": None,
        "lineup": None,
        "price_zarniki": None,
        "vip_required": False,
    },
    "lunar_archive": {
        "name": "Лунный архив",
        "description": "Ночная индиго-палитра с тихой картой небес.",
        "css_class": "skin-lunar-archive",
        "asset": "static/skins/lunar-archive-v1.webp",
        "lineup": "moon_lotus",
        "price_zarniki": None,
        "vip_required": True,
    },
    "void_atlas": {
        "name": "Атлас Бездны",
        "description": "Космическая карта с планетами и тонкими орбитами на всём фоне приложения.",
        "css_class": "skin-void-atlas",
        "asset": "static/skins/void-atlas-v1.webp",
        "lineup": "void",
        "price_zarniki": 1600,
        "vip_required": False,
    },
}


def is_known(skin_id: object) -> bool:
    return isinstance(skin_id, str) and skin_id in SKINS


def shop_items_for_lineup(lineup_id: str) -> dict[str, dict]:
    return {
        skin_id: definition
        for skin_id, definition in SKINS.items()
        if definition.get("lineup") == lineup_id and definition.get("price_zarniki")
    }
