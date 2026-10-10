"""Public projection of a player's look (Skins V3), with the VIP visibility rule applied in one place.

Owners see their own skin always (services.skins_v3.own_look). Everyone else sees it only while the owner has
VIP; without VIP they get the skin's name and tier and nothing to render.
"""
from __future__ import annotations

from core.appearance_v3 import cap_tier, visible_to_others
from core.skins_v3 import CEILING
from core.skins_v3_catalog import SKINS
from infrastructure.repositories import skins_v3 as skins_repo
from services.skins_v3 import collection_summary, crest_for, look_payload
from services.vip import is_vip_active, is_vip_active_batch


async def public_view(db, owner_id: int) -> dict:
    await skins_repo.ensure_tables(db)
    vip = await is_vip_active(db, int(owner_id))
    visible = visible_to_others(vip)
    worn = (await skins_repo.equipped_batch(db, [int(owner_id)])).get(int(owner_id))
    owned = await skins_repo.owned(db, int(owner_id))
    # the collection is counts only (no ids and no pictures), so it is public whatever the VIP state is
    out = {"visible": visible, "hidden_reason": None if visible else "vip_required", "worn": False, "look": None, "collection": collection_summary(owned)}
    if not worn or worn[0] not in SKINS:
        return out
    skin_id, tier = worn
    tier = cap_tier(tier, vip)
    out["worn"] = True
    if visible:
        out["look"] = look_payload(skin_id, tier, crest=crest_for(skin_id, owned))
    else:   # names and tiers are public, anything that can be drawn is not
        out["look"] = {"name": SKINS[skin_id]["name"], "tier": tier, "ceiling": CEILING}
    return out


async def nick_styles(db, user_ids: list[int]) -> dict[int, dict]:
    """Compact looks for list rows (leaderboards). Only VIP owners have a look others can see."""
    ids = [int(u) for u in dict.fromkeys(user_ids or [])]
    if not ids:
        return {}
    await skins_repo.ensure_tables(db)
    vip_ids = await is_vip_active_batch(db, ids)
    worn = await skins_repo.equipped_batch(db, [uid for uid in ids if uid in vip_ids])
    return {uid: look_payload(skin_id, cap_tier(tier, True), compact=True)
            for uid, (skin_id, tier) in worn.items() if skin_id in SKINS}


__all__ = ["public_view", "nick_styles"]
