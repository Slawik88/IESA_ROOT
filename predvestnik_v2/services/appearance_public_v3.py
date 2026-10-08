"""Public projection of a player's look, with the VIP visibility rule applied in one place.

Owners see everything they equipped (services.cosmetics.get_active_cosmetics). Everyone else sees the
look only while the owner has VIP; otherwise they get the names of equipped items and no render data.
"""
from __future__ import annotations

from core.appearance_v3 import TIERS, tier_of_cosmetic, visible_to_others
from core.cosmetics import COSMETICS
from core.global_skins_v1 import DEFAULT_SKIN_ID, SKINS
from infrastructure.repositories import global_skins_v1 as skins_repo
from services.cosmetics import _loadout
from services.vip import is_vip_active, is_vip_active_batch

_SLOT_ORDER = ("name_glow", "title", "avatar_frame", "avatar_halo", "profile_bg", "card_fx")


def _item(slot: str, cosmetic: dict) -> dict:
    return {
        "slot": slot, "name": cosmetic["name"], "lineup": cosmetic.get("lineup"),
        "tier": tier_of_cosmetic(cosmetic), "css": cosmetic.get("css"), "text": cosmetic.get("text"),
    }


async def skin_info(db, owner_id: int, *, visible: bool) -> dict:
    """Which app skin the owner wears; the palette key is returned only when others may see it."""
    await skins_repo.ensure_tables(db)
    saved = await skins_repo.saved_selection(db, int(owner_id)) or DEFAULT_SKIN_ID
    if saved not in SKINS:
        saved = DEFAULT_SKIN_ID
    definition = SKINS[saved]
    return {
        "id": saved, "name": definition["name"], "tier": definition.get("tier") or "D",
        "css_class": definition["css_class"] if visible and definition["css_class"] else None,
        "worn": saved != DEFAULT_SKIN_ID,
    }


async def public_view(db, owner_id: int) -> dict:
    loadout = await _loadout(db, int(owner_id))
    equipped = [
        _item(slot, COSMETICS[cid]) for slot in _SLOT_ORDER
        if (cid := loadout.get(slot)) and cid in COSMETICS
    ]
    vip = await is_vip_active(db, int(owner_id))
    visible = visible_to_others(vip)
    return {
        "visible": visible,
        "hidden_reason": None if visible else "vip_required",
        # names and tiers are always shown; render data (css, text) only when visible
        "equipped": [{"slot": i["slot"], "name": i["name"], "tier": i["tier"]} for i in equipped],
        "items": {i["slot"]: i for i in equipped} if visible else {},
        "skin": await skin_info(db, owner_id, visible=visible),
    }


async def nick_styles(db, user_ids: list[int]) -> dict[int, dict]:
    """Name glow + title for list rows (leaderboards). Only VIP owners have a style others can see."""
    ids = [int(u) for u in dict.fromkeys(user_ids or [])]
    if not ids:
        return {}
    vip_ids = await is_vip_active_batch(db, ids)
    wanted = [uid for uid in ids if uid in vip_ids]
    if not wanted:
        return {}
    marks = ",".join("?" for _ in wanted)
    async with db.execute(
        f"SELECT user_id, slot, cosmetic_id FROM user_cosmetic_loadout WHERE user_id IN ({marks}) "
        "AND slot IN ('name_glow','title')", tuple(wanted),
    ) as cursor:
        rows = await cursor.fetchall()
    out: dict[int, dict] = {}
    for row in rows:
        cosmetic = COSMETICS.get(row[2])
        if not cosmetic:
            continue
        out.setdefault(int(row[0]), {})["glow" if row[1] == "name_glow" else "title"] = {
            "lineup": cosmetic.get("lineup"), "tier": tier_of_cosmetic(cosmetic),
            "text": cosmetic.get("text") or cosmetic["name"],
        }
    return out


__all__ = ["TIERS", "public_view", "nick_styles", "skin_info"]
