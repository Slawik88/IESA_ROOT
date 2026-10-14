#!/usr/bin/env python3
"""Pure rules for ECO-04 PR-B shop: the catalogue is a view of KEY_OFFERS and the exchange policy, Polish is one constant."""
from __future__ import annotations

import json
import pathlib
import sys
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import shop_v1 as shop
from core.chests_v1 import KEY_OFFERS, tier_star_odds
from core.zarniki_exchange_v1 import DAILY_ZARNIKI_CAP, EXCHANGE_ROUTES
from services.shop_v1 import missing, missing_text


def run() -> None:
    items = {row["id"]: row for row in shop.items()}

    # Ids follow the owner's catalogue; gifts (PR-C) and link tiles are not sellable items.
    owner = json.loads((ROOT / "pipeline/tasks/ECO-04-PR-B-shop/shop_catalog.json").read_text(encoding="utf-8"))
    sellable = [row for row in owner["items"] if row["section"] not in {"gifts", "links"}]
    assert set(items) == {row["id"] for row in sellable} and len(items) == len(sellable), list(items)
    for row in sellable:
        assert items[row["id"]]["section"] == row["section"] and items[row["id"]]["mode"] == row["mode"], row["id"]
    assert {link["id"] for link in shop.links()} == {row["id"] for row in owner["items"] if row["section"] == "links"}
    assert not any(row["section"] == "gifts" for row in shop.items()) and "gifts" not in dict(shop.SECTIONS)
    assert [s for s, _ in shop.SECTIONS] == ["keys", "essence", "exchange"]

    # Keys: every price, limit and window is the KEY_OFFERS row, nothing copied.
    assert set(shop.KEY_ITEMS.values()) == set(KEY_OFFERS)
    for item_id, offer_id in shop.KEY_ITEMS.items():
        offer, row = KEY_OFFERS[offer_id], items[item_id]
        assert row["cost"] == offer["price"] and row["tier"] == offer["tier"], item_id
        assert row["limit"]["max"] == offer["limit"] and row["limit"]["period"] == offer["window"], item_id
        assert row["gives"]["keys"] == {str(offer["tier"]): 1}
    # The owner's catalogue says the same in its own units (dia/zar/ess).
    units = {"mora": "mora", "dia": "diamonds", "zar": "zarniki", "ess": "essence"}
    for row in sellable:
        if row["section"] == "keys":
            assert {units[k]: v for k, v in row["cost"].items()} == items[row["id"]]["cost"], row["id"]
    assert tier_star_odds(4)[0]["percent"] == 89.0 and tier_star_odds(6)[0]["percent"] == 97.0

    # Exchange: rates and the shared daily cap come from the exchange policy.
    for item_id, target in shop.EXCHANGE_ITEMS.items():
        row = items[item_id]
        assert row["rate"] == str(EXCHANGE_ROUTES[target]) and row["limit"]["max"] == DAILY_ZARNIKI_CAP
        assert row["cost"] == {"zarniki": 1} and row["limit"]["shared"] is True
    assert items["exchange_mora"]["gives"]["text"] == "10 Моры за 1✨"
    assert items["exchange_dia"]["gives"]["text"] == "0,01 💎 за 1✨ (1 💎 за 100✨)"

    # Polish: one constant, owner's numbers.
    assert shop.POLISH == {"price": {"mora": 600, "diamonds": 1}, "essence": 60, "limit": 2, "window": "week"}
    polish = items["ess_polish"]
    assert polish["cost"] == shop.POLISH["price"] and polish["gives"]["essence"] == 60 and polish["limit"]["max"] == 2

    # Digest: stable, and any price change (shop, key or exchange) changes it.
    digest = shop.catalog_digest()
    assert digest == shop.catalog_digest() and len(digest) == 64
    with mock.patch.dict(shop.POLISH, {"price": {"mora": 650, "diamonds": 1}}):
        assert shop.catalog_digest() != digest and shop.item("ess_polish")["cost"]["mora"] == 650
    with mock.patch.dict(KEY_OFFERS["bronze_mora"], {"price": {"mora": 900}}):
        assert shop.catalog_digest() != digest and shop.item("key_t3_mora")["cost"] == {"mora": 900}
    with mock.patch.dict(EXCHANGE_ROUTES, {"mora": EXCHANGE_ROUTES["mora"] * 2}):
        assert shop.catalog_digest() != digest
    assert shop.catalog_digest() == digest

    # Shortages round up and name every currency.
    have = {"mora": 599.5, "diamonds": 0.4, "zarniki": 0, "essence": 0}
    assert missing(shop.POLISH["price"], have) == {"mora": 1, "diamonds": 1}
    assert missing_text({"mora": 120}) == "Не хватает: 120 🪙."
    assert missing(shop.POLISH["price"], {**have, "mora": 600, "diamonds": 1}) == {}
    try:
        shop.item("gift_rose")
    except shop.ShopPolicyError:
        pass
    else:
        raise AssertionError("gifts are not on sale")
    print("OK: shop catalogue = KEY_OFFERS + exchange policy + one Polish constant; digest follows prices; ids match the owner's catalogue")


if __name__ == "__main__":
    run()
