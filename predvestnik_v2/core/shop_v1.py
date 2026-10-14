"""Shop screen catalogue (ECO-04 PR-B). Pure rules: no clock, no database.

The shop sells nothing it owns except Polish (Шлифовка). Key items are views of
``core.chests_v1.KEY_OFFERS`` and exchange items are views of the Zarniki exchange
policy: their prices and limits are read from there, never copied, so changing a
price stays a one-constant edit and changes the shop digest as well.
Gifts (PR-C) are not part of this catalogue yet.
"""
from __future__ import annotations

from typing import Final

from core.chests_v1 import (
    CATALOG_VERSION as CHEST_CATALOG_VERSION, KEY_OFFERS, canonical_snapshot_fingerprint,
    catalog_digest as chest_catalog_digest,
)
from core.zarniki_exchange_v1 import (
    DAILY_ZARNIKI_CAP, EXCHANGE_ROUTES, POLICY_VERSION as EXCHANGE_POLICY_VERSION,
)


SHOP_VERSION: Final = "shop-v1-2026-10-14"
FLAG: Final = "shop_v1"
POLISH_REASON_CODE: Final = "shop_essence_polish"
CURRENCIES: Final = ("mora", "diamonds", "zarniki", "essence")

# The only new sink: 600 Mora + 1 Diamond -> 60 Essence, twice per ISO week (UTC, from Monday).
POLISH_ITEM: Final = "ess_polish"
POLISH: Final = {"price": {"mora": 600, "diamonds": 1}, "essence": 60, "limit": 2, "window": "week"}

# Shop item id -> chest offer id (core.chests_v1.KEY_OFFERS). Order is the display order.
KEY_ITEMS: Final = {
    "key_t3_mora": "bronze_mora",
    "key_t4_craft": "silver_craft",
    "key_t4_zar": "silver_zarniki",
    "key_t6_dia": "platinum_diamonds",
    "key_t6_zar": "platinum_zarniki",
}
KEY_NAMES: Final = {3: "Ключ Бронза", 4: "Ключ Серебро", 6: "Ключ Платина"}
# Shop item id -> exchange target (core.zarniki_exchange_v1.EXCHANGE_ROUTES).
EXCHANGE_ITEMS: Final = {"exchange_mora": "mora", "exchange_dia": "diamonds"}
EXCHANGE_NAMES: Final = {"mora": ("Зарники → Мора", "🪙"), "diamonds": ("Зарники → Алмазы", "💎")}
# Tiles that open existing screens. ``flag``: shown only while that screen is switched on.
LINKS: Final = {
    "link_pass": {"name": "Сезонный пропуск", "icon": "🏆", "target": "pass", "flag": "season_pass_v1"},
    "link_vip": {"name": "VIP", "icon": "👑", "target": "vip", "flag": None},
    "link_skins": {"name": "Скины", "icon": "🎭", "target": "skins", "flag": None},
}
SECTIONS: Final = (
    ("keys", "Ключи"),
    ("essence", "Эссенция"),
    ("exchange", "Обменник"),
)


class ShopPolicyError(ValueError):
    """The request does not name a sellable shop item."""


def _key_item(item_id: str, offer_id: str) -> dict[str, object]:
    offer = KEY_OFFERS[offer_id]
    tier = int(offer["tier"])
    price = {str(k): int(v) for k, v in dict(offer["price"]).items()}
    return {
        "id": item_id, "section": "keys", "mode": "craft" if "essence" in price else "buy",
        "name": f"{KEY_NAMES[tier]} {tier}★", "icon": "🗝", "tier": tier,
        "group": f"key_t{tier}", "offer_id": offer_id, "cost": price,
        "gives": {"text": f"ключ: сундук от {tier}★", "keys": {str(tier): 1}},
        "limit": {"period": str(offer["window"]), "max": int(offer["limit"]), "unit": "keys"},
    }


def _exchange_item(item_id: str, target: str) -> dict[str, object]:
    name, icon = EXCHANGE_NAMES[target]
    rate = EXCHANGE_ROUTES[target]
    shown = format(rate.normalize(), "f").replace(".", ",")
    text = (f"{shown} Моры за 1✨" if target == "mora"
            else f"{shown} 💎 за 1✨ (1 💎 за {format((1 / rate).normalize(), 'f')}✨)")
    return {
        "id": item_id, "section": "exchange", "mode": "exchange", "name": name, "icon": icon, "tier": None,
        "group": None, "target": target, "cost": {"zarniki": 1}, "rate": str(rate),
        "gives": {"text": text, target: str(rate)},
        "limit": {"period": "day", "max": DAILY_ZARNIKI_CAP, "unit": "zarniki", "shared": True},
    }


def _polish_item() -> dict[str, object]:
    return {
        "id": POLISH_ITEM, "section": "essence", "mode": "craft", "name": "Шлифовка", "icon": "🔮", "tier": None,
        "group": None, "cost": dict(POLISH["price"]),
        "gives": {"text": f"+{POLISH['essence']} Эссенции", "essence": int(POLISH["essence"])},
        "limit": {"period": str(POLISH["window"]), "max": int(POLISH["limit"]), "unit": "items"},
    }


def items() -> list[dict[str, object]]:
    """Every sellable item in display order (keys, essence, exchange)."""
    return ([_key_item(item_id, offer_id) for item_id, offer_id in KEY_ITEMS.items()]
            + [_polish_item()]
            + [_exchange_item(item_id, target) for item_id, target in EXCHANGE_ITEMS.items()])


def item(item_id: object) -> dict[str, object]:
    normalized = str(item_id or "").strip()
    for row in items():
        if row["id"] == normalized:
            return row
    raise ShopPolicyError("Такого товара в магазине нет.")


def links() -> list[dict[str, object]]:
    return [{"id": link_id, "section": "links", "mode": "link", **row} for link_id, row in LINKS.items()]


def catalog_payload() -> dict[str, object]:
    return {
        "shop_version": SHOP_VERSION, "sections": [s for s, _ in SECTIONS], "items": items(),
        "polish": POLISH, "key_offers": {offer_id: KEY_OFFERS[offer_id] for offer_id in KEY_ITEMS.values()},
        "chest_catalog_version": CHEST_CATALOG_VERSION, "chest_catalog_digest": chest_catalog_digest(),
        "exchange_policy_version": EXCHANGE_POLICY_VERSION, "exchange_daily_cap": DAILY_ZARNIKI_CAP,
        "exchange_routes": {target: str(rate) for target, rate in EXCHANGE_ROUTES.items()},
    }


def catalog_digest() -> str:
    return canonical_snapshot_fingerprint(catalog_payload())
