#!/usr/bin/env python3
"""Pure rules for ECO-04 PR-C gifts: the catalogue is the owner's, notes are short plain text, the hash ignores prices."""
from __future__ import annotations

import json
import pathlib
import sys
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import gifts_v2 as gifts
from core import shop_v1
from infrastructure.repositories import system_flags
from services.gifts_v2 import missing, missing_text


def refused(fn, *args) -> str:
    try:
        fn(*args)
    except gifts.GiftPolicyError as exc:
        return str(exc)
    raise AssertionError(f"expected a refusal for {args!r}")


def run() -> None:
    # Catalogue = the owner's gifts section: ids, names, icons, tiers and prices (dia/zar -> diamonds/zarniki).
    owner = json.loads((ROOT / "pipeline/tasks/ECO-04-PR-B-shop/shop_catalog.json").read_text(encoding="utf-8"))
    assert {int(k): v for k, v in owner["tiers"].items()} == gifts.TIERS == {1: "Знак", 2: "Тёплый", 3: "Редкий", 4: "Легендарный"}
    rows = [row for row in owner["items"] if row["section"] == "gifts"]
    assert [row["id"] for row in rows] == list(gifts.GIFTS) and len(rows) == 12
    units = {"mora": "mora", "dia": "diamonds", "zar": "zarniki"}
    for row in rows:
        item = gifts.gift(row["id"])
        assert item["name"] == row["name"] and item["icon"] == row["icon"], row["id"]
        assert item["cost"] == {units[k]: v for k, v in row["cost"].items()}, row["id"]
        assert f"тира {item['tier']}" in row["gives"], row["id"]
    per_tier = {t: [g["id"] for g in gifts.gifts() if g["tier"] == t] for t in gifts.TIERS}
    assert all(len(ids) == 3 for ids in per_tier.values())
    # Tier currency: 1–2 Mora, 3 Diamonds, 4 Zarniki; ✨/💎 tiers are irreversible in the confirm sheet.
    assert {t: {c for g in gifts.gifts() if g["tier"] == t for c in g["cost"]} for t in gifts.TIERS} == {
        1: {"mora"}, 2: {"mora"}, 3: {"diamonds"}, 4: {"zarniki"}}
    assert [gifts.irreversible(g["cost"]) for g in gifts.gifts()] == [False] * 6 + [True] * 6
    assert (gifts.DAILY_SEND_LIMIT, gifts.DAILY_PER_RECIPIENT_LIMIT, gifts.NOTE_MAX, gifts.PIN_MAX) == (5, 3, 60, 3)
    assert refused(gifts.gift, "ess_polish") and refused(gifts.gift, "")

    # The shop still does not sell gifts: they have their own store and receipts.
    try:
        shop_v1.item("gift_rose")
    except shop_v1.ShopPolicyError:
        pass
    else:
        raise AssertionError("gifts are not shop items")

    # Flag: known, default off, fail-closed before the table exists.
    assert system_flags._DEFAULT_ENABLED[gifts.FLAG] is False and gifts.FLAG == "gifts_v2"

    # Notes: strip, empty -> None, ≤60 characters, emoji (with ZWJ) fine, control/bidi/line separators refused.
    assert gifts.normalize_note(None) is None and gifts.normalize_note("   ") is None
    assert gifts.normalize_note("  С днём рождения!  ") == "С днём рождения!"
    assert gifts.normalize_note("x" * 60) == "x" * 60
    assert "60" in refused(gifts.normalize_note, "x" * 61)
    assert gifts.normalize_note("👩‍❤️‍👨 <b>&") == "👩‍❤️‍👨 <b>&"   # stored as typed; the UI escapes it
    for bad in ("a\nb", "a\tb", "a\x00b", "a‮b", "a b", "a\x7fb", "a⁦b"):
        assert refused(gifts.normalize_note, bad), repr(bad)
    assert refused(gifts.normalize_note, 42)

    # Hash: gift + note only. A price or catalogue change keeps the same request identity.
    h = gifts.request_hash("gift_rose", "hi")
    assert h == gifts.request_hash("gift_rose", "hi") and len(h) == 64
    assert h != gifts.request_hash("gift_rose", None) and h != gifts.request_hash("gift_card", "hi")
    assert gifts.request_hash("gift_rose", None) == gifts.request_hash("gift_rose", "")
    digest = gifts.catalog_digest()
    with mock.patch.dict(gifts.GIFTS, {"gift_rose": {**gifts.GIFTS["gift_rose"], "price": {"mora": 350}}}):
        assert gifts.catalog_digest() != digest and gifts.gift("gift_rose")["cost"] == {"mora": 350}
        assert gifts.request_hash("gift_rose", "hi") == h
    assert gifts.catalog_digest() == digest

    # Shortages round up and name the currency.
    assert missing({"diamonds": 2}, {"mora": 0, "diamonds": 0.5, "zarniki": 0}) == {"diamonds": 2}
    assert missing_text({"zarniki": 800}) == "Не хватает: 800 ✨."
    print("OK: gifts catalogue = owner's 4 tiers × 3 gifts, flag off by default, notes ≤60 plain text, hash = gift + note")


if __name__ == "__main__":
    run()
