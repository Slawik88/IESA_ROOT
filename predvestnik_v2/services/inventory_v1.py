"""Inventory («Инвентарь»): one read-only view of what a player keeps that the skins, marks and wallet screens do not show.

Live stock, what chests give: keys, pet food, pet cards, jokers and the pets found so far. Old stock: the `inventory` table, items of the previous game (materials, boosters,
chests of the old catalogue, tokens) that no screen shows any more but the player still owns, listed with the quantities kept. Nothing is written or spent here.
Skins come from services/skins_v3.py (the client draws them from /skins-v3/me), marks from services/marks_v1.py, balances from the wallet.
"""
from __future__ import annotations

import re

from core.chests_v1 import FOODS, JOKER_RARITIES, PET_SPECIES
from core.pets_v2 import SPECIES as TRAIL_SPECIES
from core.registry import ITEMS_REGISTRY
from infrastructure.repositories import chests_v1 as chests_repo
from infrastructure.repositories import pets_v1 as pets_repo
from infrastructure.repositories import pets_v2 as trail_repo
from infrastructure.repositories.economy import get_inventory
from services.inventory_resolve import resolve_item_id

# Old items by category: the title and icon of the group, in the order a player reads them. A category that is not listed lands in the last group.
ARCHIVE_GROUPS = (
    ("donate", "Предметы за Зарники", "✨"),
    ("material", "Материалы", "💠"),
    ("chest", "Сундуки прежнего каталога", "🎁"),
    ("spin_token", "Жетоны", "🎟"),
    ("booster", "Усилители", "⚡"),
    ("food", "Прежний корм питомцев", "🥩"),
    ("utility", "Прочее", "📚"),
)
_FALLBACK_GROUP = ARCHIVE_GROUPS[-1][0]

# The registry text of these items sends the player to a «Зоопарк» that is gone; the quantity is kept and nothing consumes it. The nickname token is live and keeps its own text.
_FOOD_NOTE = "Прежний корм питомцев: количество сохранено. Еда новых питомцев лежит в разделе «Питомцы»."
_PET_ITEM_NOTE = "Прежний предмет для питомцев: количество сохранено и сейчас не расходуется."
_STALE_NOTES = {
    **{item_id: _FOOD_NOTE for item_id, meta in ITEMS_REGISTRY.items() if meta.get("category") == "food"},
    "zarniki_fatigue_reset": _PET_ITEM_NOTE,
    "zarniki_cooldown_skip": _PET_ITEM_NOTE,
}
_LOST_NOTE = "Название этого предмета потеряно, количество сохранено."
_ICON_PREFIX = re.compile(r"^([^\w\s«»\"'(]+)\s*(.*)$", re.UNICODE)
_ORDER = {item_id: n for n, item_id in enumerate(ITEMS_REGISTRY)}


def split_icon(title: str) -> tuple[str, str]:
    """«💠 Осколок Души» → («💠», «Осколок Души»): the registry keeps the icon inside the name, the client wants them apart."""
    found = _ICON_PREFIX.match(title.strip())
    return (found.group(1), found.group(2)) if found and found.group(2) else ("", title.strip())


async def archive(db, user_id: int) -> dict:
    """Items of the old `inventory` table, grouped; numeric legacy ids are resolved to the real item (read-only, the stored row is left as it is)."""
    owned: dict[str, int] = {}
    for row in await get_inventory(db, int(user_id)):
        item_id = await resolve_item_id(db, str(row["item_id"]))
        owned[item_id] = owned.get(item_id, 0) + int(row["quantity"])
    groups: dict[str, list[dict]] = {key: [] for key, _, _ in ARCHIVE_GROUPS}
    for item_id in sorted(owned, key=lambda value: (_ORDER.get(value, len(_ORDER)), value)):
        meta = ITEMS_REGISTRY.get(item_id)
        if meta:
            icon, name = split_icon(str(meta.get("name") or item_id))
            category = meta.get("category") if meta.get("category") in groups else _FALLBACK_GROUP
            note = _STALE_NOTES.get(item_id) or str(meta.get("description") or "")
        else:
            icon, name, category, note = "❓", f"Предмет #{item_id}", _FALLBACK_GROUP, _LOST_NOTE
        groups[category].append({"id": item_id, "name": name, "icon": icon, "quantity": owned[item_id], "note": note})
    shown = [{"id": key, "title": title, "icon": icon, "items": groups[key], "pieces": sum(item["quantity"] for item in groups[key])}
             for key, title, icon in ARCHIVE_GROUPS if groups[key]]
    return {"groups": shown, "kinds": sum(len(group["items"]) for group in shown), "pieces": sum(group["pieces"] for group in shown)}


async def stock(db, user_id: int, *, trail: bool = False) -> dict:
    """What chests gave and what is in use now: keys, pet food, pet cards, jokers, pets found. Read-only: it never settles a pet run or touches endurance."""
    kept = await chests_repo.inventory_summary(db, user_id=int(user_id))
    foods = [{"id": food_id, "name": FOODS[food_id]["name"], "icon": FOODS[food_id]["icon"], "restore": int(FOODS[food_id]["restore"]), "quantity": int(kept["foods"][food_id])}
             for food_id in FOODS if int(kept["foods"].get(food_id, 0)) > 0]
    cards = [{"species_id": species_id, "name": meta["name"], "icon": meta["icon"], "rarity": meta["rarity"], "quantity": int(kept["pet_cards"][species_id])}
             for species_id, meta in PET_SPECIES.items() if int(kept["pet_cards"].get(species_id, 0)) > 0]   # in the order of the catalogue: from common to legendary
    jokers = [{"rarity": rarity, "quantity": int(kept["jokers"][rarity])} for rarity in JOKER_RARITIES if int(kept["jokers"].get(rarity, 0)) > 0]
    profile = None if trail else await pets_repo.get_profile(db, int(user_id))
    active = int(profile["active_pet_id"]) if profile and profile.get("active_pet_id") else None
    pets = [{"id": int(pet["id"]), "name": pet.get("name") or "Питомец", "species_id": pet.get("species_id"), "rarity": pet.get("rarity"),
             "icon": (PET_SPECIES.get(str(pet.get("species_id") or "")) or {}).get("icon", "🐾"), "level": int(pet["level"] if pet["level"] is not None else 1), "active": int(pet["id"]) == active}
            for pet in await (trail_repo if trail else pets_repo).list_owned_pets(db, int(user_id))
            if not trail or pet.get("species_id") in TRAIL_SPECIES]
    result = {"keys": await chests_repo.get_balance(db, int(user_id)), "foods": foods, "pet_cards": cards, "jokers": jokers, "pets": pets, "species_total": len(PET_SPECIES)}
    if trail:
        result["pets_version"] = 2
        result["talismans"] = await trail_repo.list_talismans(db, int(user_id))
    return result


async def overview(db, user_id: int, *, chests: bool, trail: bool = False) -> dict:
    """Everything the screen needs besides skins. `chests` is the global switch of the chest catalogue: off, the live stock is not shown at all (null)."""
    return {"stock": await stock(db, user_id, trail=trail) if chests else None, "archive": await archive(db, user_id)}
