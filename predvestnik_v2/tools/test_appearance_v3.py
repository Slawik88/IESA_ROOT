#!/usr/bin/env python3
"""Appearance V3: tiers for every cosmetic, VIP visibility rule, and a leak-proof public card."""
import asyncio
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    import aiosqlite  # noqa: F401
except ImportError:
    stub = types.ModuleType("aiosqlite")
    stub.Connection = object
    sys.modules["aiosqlite"] = stub

from core import appearance_v3 as policy  # noqa: E402
from core.cosmetics import COSMETICS, is_vip_locked  # noqa: E402
from services import appearance_public_v3 as look  # noqa: E402
from services import public_profile_v3  # noqa: E402

# Every one of the 134 items has a tier from D to SS, following its collection rarity.
tiers = {cid: policy.tier_of_cosmetic(item) for cid, item in COSMETICS.items()}
assert all(tier in policy.USABLE_WITHOUT_VIP for tier in tiers.values()), "unmapped cosmetic"
assert set(tiers.values()) == {"D", "C", "B", "A", "S", "SS"}
assert policy.tier_of_lineup("forest") == "D" and policy.tier_of_lineup("ryujin_tide") == "SS"
assert policy.usable_without_vip("SS") and not policy.usable_without_vip("SSS")
assert policy.visible_to_others(True) and not policy.visible_to_others(False)
# No tiered item sleeps without VIP any more; an untiered service entitlement still does.
assert not [cid for cid, item in COSMETICS.items() if is_vip_locked(item)]
assert is_vip_locked({"vip_required": True, "price": None}) is True


class Db:
    pass


LOADOUT = {"name_glow": "cos_name_glow_moon", "avatar_frame": "cos_avatar_frame_moon_lotus", "welcome": "scanner"}


def run(vip: bool) -> dict:
    async def loadout(db, uid): return dict(LOADOUT)
    async def is_vip(db, uid): return vip
    async def saved(db, uid): return "void_atlas"
    async def ensure(db): return None
    look._loadout, look.is_vip_active = loadout, is_vip
    look.skins_repo.saved_selection, look.skins_repo.ensure_tables = saved, ensure
    return asyncio.run(look.public_view(Db(), 5))


with_vip, without_vip = run(True), run(False)
assert with_vip["visible"] and set(with_vip["items"]) == {"name_glow", "avatar_frame"}
assert with_vip["items"]["avatar_frame"]["tier"] == "SS" and with_vip["items"]["name_glow"]["css"] == "glow-moon"
assert with_vip["skin"]["css_class"] == "skin-void-atlas" and with_vip["skin"]["tier"] == "A"
assert not without_vip["visible"] and without_vip["items"] == {} and without_vip["hidden_reason"] == "vip_required"
assert [i["slot"] for i in without_vip["equipped"]] == ["name_glow", "avatar_frame"], "names stay visible"
assert all(set(i) == {"slot", "name", "tier"} for i in without_vip["equipped"]), "no render data without VIP"
assert without_vip["skin"]["css_class"] is None and without_vip["skin"]["worn"] and without_vip["skin"]["name"]

base = {
    "profile_ref": "ref123", "display_name": "Игорь", "rank": "Хранитель", "account_level": 14, "xp_into": 3, "xp_to_next": 9,
    "messages_all_time": 100, "streak": 4, "achievements": 2, "joined_date": "2026-01-01", "partner": "Есть",
    "balances": {"mora": 1e9, "zarniki": 5}, "sanctions": {"active_global": {"type": "ban"}}, "game_results": {"rhythm": {}},
    "achievement_paths": {}, "pets": [{"name": "Лис", "active": True, "level": 3, "rarity": "rare"}],
    "vip": {"label": "Gold", "days_left": 5, "badge": "✦", "badge_position": "left", "tier": "gold"}, "avatar": "data:image/png;base64,AA==",
}
card = public_profile_v3.shape(base, with_vip, is_self=False)
flat = repr(card)
assert "balances" not in card and "sanctions" not in card and "1000000000" not in flat and "ban" not in flat
assert card["stats"]["active_pet"]["name"] == "Лис" and card["stats"]["has_partner"] is True
assert public_profile_v3.shape({**base, "vip": None}, without_vip, is_self=False)["avatar"] is None
print("OK: appearance tiers, VIP visibility rule and public card allow-list")
