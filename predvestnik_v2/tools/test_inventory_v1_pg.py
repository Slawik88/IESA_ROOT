#!/usr/bin/env python3
"""PostgreSQL proof for the inventory view: old items grouped with the registry names and notes, unknown ids kept, empty rows hidden, live stock named and ordered, chests switched off = no stock, nothing written."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.chests_v1 import FOODS, PET_SPECIES  # noqa: E402
from core.registry import ITEMS_REGISTRY  # noqa: E402
from infrastructure.pg_adapter import PGAdapter  # noqa: E402
from infrastructure.repositories import chests_v1 as chests_repo  # noqa: E402
from infrastructure.repositories import pets_v1 as pets_repo  # noqa: E402
from infrastructure.repositories import pets_v2 as trail_repo  # noqa: E402
from services import inventory_v1 as inventory  # noqa: E402


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def count(db, user_id: int) -> int:
    async with db.execute("SELECT COUNT(*), COALESCE(SUM(quantity), 0) FROM inventory WHERE user_id = ?", (user_id,)) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) * 1_000_000 + int(row[1])


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    db = PGAdapter(connection)
    await chests_repo.ensure_tables(db)
    await pets_repo.ensure_tables(db)
    await trail_repo.ensure_tables(db)
    outer = connection.transaction()
    await outer.start()
    try:
        player, newcomer, keeper = 984001, 984002, 984003
        for item_id, quantity in (("soul_shard", 12), ("star_dust_s", 3), ("chest_style", 1), ("spin_token", 2), ("food_basic", 5), ("zarniki_fatigue_reset", 1),
                                  ("lucky_charm", 0), ("no_such_item", 4)):
            await db.execute("INSERT INTO inventory(user_id, item_id, quantity) VALUES (?, ?, ?)", (player, item_id, quantity))
        await db.execute("INSERT INTO chest_key_accounts_v1(user_id, balance) VALUES (?, 3) ON CONFLICT (user_id) DO UPDATE SET balance = 3", (player,))
        for food_id, quantity in (("food_stew", 1), ("food_basic", 2), ("food_unknown", 9)):
            await db.execute("INSERT INTO chest_food_balances_v1(user_id, food_id, quantity) VALUES (?, ?, ?)", (player, food_id, quantity))
        for species_id, quantity in (("moss_cat", 5), ("void_lynx", 1), ("not_a_species", 7)):
            await db.execute("INSERT INTO chest_pet_card_balances_v1(user_id, species_id, quantity) VALUES (?, ?, ?)", (player, species_id, quantity))
        for rarity, quantity in (("rare", 2), ("common", 4), ("epic", 0)):
            await db.execute("INSERT INTO chest_joker_balances_v1(user_id, rarity, quantity) VALUES (?, ?, ?)", (player, rarity, quantity))
        before = await count(db, player)

        data = await inventory.overview(db, player, chests=True)
        archive = data["archive"]
        groups = {group["id"]: group for group in archive["groups"]}
        # groups come in the order of the screen and only when they hold something
        assert [group["id"] for group in archive["groups"]] == ["donate", "material", "chest", "spin_token", "food", "utility"], archive["groups"]
        assert archive["kinds"] == 7 and archive["pieces"] == 12 + 3 + 1 + 2 + 5 + 1 + 4, archive
        shard = groups["material"]["items"][0]
        assert (shard["id"], shard["icon"], shard["name"], shard["quantity"]) == ("soul_shard", "💠", "Осколок Души", 12), shard
        assert all("lucky_charm" != item["id"] for group in archive["groups"] for item in group["items"]), "an empty row is not an item"
        # the old text of a food that sent the player to a Zoo that is gone is replaced
        food = groups["food"]["items"][0]
        assert food["id"] == "food_basic" and "Зоопарк" not in food["note"] and "«Питомцы»" in food["note"], food
        donate = {item["id"]: item for item in groups["donate"]["items"]}
        assert "не расходуется" in donate["zarniki_fatigue_reset"]["note"], donate
        lost = groups["utility"]["items"][0]
        assert (lost["id"], lost["icon"], lost["name"], lost["quantity"]) == ("no_such_item", "❓", "Предмет #no_such_item", 4), lost

        # the live stock: names from the catalogue, only what is known and positive, food in the order of its strength, jokers by rarity
        stock = data["stock"]
        assert stock["keys"] == 3 and stock["species_total"] == len(PET_SPECIES) == 12, stock
        assert [(food["id"], food["quantity"]) for food in stock["foods"]] == [("food_basic", 2), ("food_stew", 1)], stock["foods"]
        assert stock["foods"][0]["name"] == FOODS["food_basic"]["name"] and stock["foods"][0]["restore"] == 15, stock["foods"][0]
        assert [(card["species_id"], card["quantity"]) for card in stock["pet_cards"]] == [("moss_cat", 5), ("void_lynx", 1)], stock["pet_cards"]   # catalogue order, unknown species dropped
        assert stock["pet_cards"][0]["name"] and stock["pet_cards"][0]["icon"] and stock["pet_cards"][0]["rarity"], stock["pet_cards"]
        assert stock["jokers"] == [{"rarity": "common", "quantity": 4}, {"rarity": "rare", "quantity": 2}], stock["jokers"]
        assert stock["pets"] == [], stock["pets"]

        # a player who keeps every kind of old item: all of them are listed and none sends to the «Зоопарк» that is gone
        for item_id in ITEMS_REGISTRY:
            await db.execute("INSERT INTO inventory(user_id, item_id, quantity) VALUES (?, ?, 1)", (keeper, item_id))
        everything = await inventory.archive(db, keeper)
        assert everything["kinds"] == len(ITEMS_REGISTRY) and everything["pieces"] == len(ITEMS_REGISTRY), everything["kinds"]
        notes = [item["note"] for group in everything["groups"] for item in group["items"]]
        assert all(notes) and not any("Зоопарк" in note for note in notes), "every item has a note and none points to a screen that is gone"

        # the chest switch is off: the live stock is not shown at all, the old items still are
        off = await inventory.overview(db, player, chests=False)
        assert off["stock"] is None and off["archive"] == archive

        # a newcomer has an empty but well-formed view, and viewing never writes
        empty = await inventory.overview(db, newcomer, chests=True)
        assert empty["archive"] == {"groups": [], "kinds": 0, "pieces": 0}, empty
        assert empty["stock"] == {"keys": 0, "foods": [], "pet_cards": [], "jokers": [], "pets": [], "species_total": 12}, empty["stock"]
        assert await count(db, player) == before and await count(db, newcomer) == 0, "reading the inventory changes nothing"

        # A legacy active pet and the Trail intentionally disagree. The flag selects
        # the current read model, never migrates progress or creates missing state.
        async with db.execute(
            "INSERT INTO pets(owner_id,name,species_id,rarity) VALUES (?,?,?,?) RETURNING id",
            (player, "Мотылёк", "ash_moth", "common"),
        ) as cursor:
            pet_id = int((await cursor.fetchone())[0])
        await db.execute("INSERT INTO pet_v1_state(user_id,pet_id,level) VALUES (?,?,9)", (player, pet_id))
        await db.execute("INSERT INTO pet_v1_profiles(user_id,active_pet_id) VALUES (?,?)", (player, pet_id))
        await db.execute("INSERT INTO pet_v2_state(user_id,pet_id,level,xp,energy) VALUES (?,?,3,17,50)", (player, pet_id))
        async with db.execute(
            "INSERT INTO pets(owner_id,name,species_id,rarity) VALUES (?,?,?,?) RETURNING id",
            (player, "Кот без состояния", "moss_cat", "common"),
        ) as cursor:
            fresh_id = int((await cursor.fetchone())[0])
        await db.execute("INSERT INTO pet_v2_talismans(id,user_id,kind,tier,pet_id) VALUES (?,?,?,2,?)",
                         ("inventory-test-talisman", player, "forest_fang", pet_id))
        legacy = (await inventory.overview(db, player, chests=True))["stock"]
        trail = (await inventory.overview(db, player, chests=True, trail=True))["stock"]
        assert next(p for p in legacy["pets"] if p["id"] == pet_id)["level"] == 9
        assert next(p for p in legacy["pets"] if p["id"] == pet_id)["active"] is True
        assert next(p for p in trail["pets"] if p["id"] == pet_id)["level"] == 3
        assert next(p for p in trail["pets"] if p["id"] == fresh_id)["level"] == 1
        assert all(p["active"] is False for p in trail["pets"])
        assert trail["pets_version"] == 2 and len(trail["talismans"]) == 1
        assert trail["talismans"][0]["effects"] == {"route": "forest", "opposite": "swamp", "plus_percent": 15, "minus_percent": 10, "set_percent": 5}, "inventory must explain the actual talisman effects without loading the Trail first"
        assert (await inventory.overview(db, newcomer, chests=True, trail=True))["stock"]["pets"] == []
        assert (await inventory.overview(db, player, chests=False, trail=True))["stock"] is None
        async with db.execute("SELECT level,xp FROM pet_v2_state WHERE user_id=? AND pet_id=?", (player, pet_id)) as cursor:
            assert tuple(await cursor.fetchone()) == (3, 17)
        async with db.execute("SELECT COUNT(*) FROM pet_v2_state WHERE user_id=? AND pet_id=?", (player, fresh_id)) as cursor:
            assert (await cursor.fetchone())[0] == 0, "viewing must not create missing state"
        assert inventory.split_icon("⚡️ Энергетик") == ("⚡️", "Энергетик") and inventory.split_icon("Без значка") == ("", "Без значка")
        print("OK: inventory v1 groups, names, notes, lost items, live stock, chest switch, read-only")
    finally:
        await outer.rollback()
        await connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", type=local_dsn, default=os.getenv("DATABASE_URL", "postgresql://predvestnik_preprod@127.0.0.1:5433/predvestnik_preprod"))
    asyncio.run(run(parser.parse_args().dsn))
