#!/usr/bin/env python3
"""Appearance V3 on Skins V3: tier cap, VIP visibility rule, compact list looks and a leak-proof public card."""
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
from core.skins_v3_catalog import SKINS  # noqa: E402
from services import appearance_public_v3 as look  # noqa: E402
from services import public_profile_v3  # noqa: E402

# Tiers D … SS are usable without VIP, SSS needs it; a non-VIP owner is shown at SS at most.
assert policy.usable_without_vip("SS") and not policy.usable_without_vip("SSS")
assert policy.visible_to_others(True) and not policy.visible_to_others(False)
assert policy.cap_tier("SSS", False) == "SS" and policy.cap_tier("SSS", True) == "SSS" and policy.cap_tier("C", False) == "C"
assert policy.cap_tier("nonsense", False) == "D"
assert {skin["tier"] for skin in SKINS.values()} == set(policy.TIERS), "every ceiling tier is represented"


class Db:
    pass


def run(vip: bool, worn=("void", "SSS")) -> dict:
    async def is_vip(db, uid): return vip
    async def ensure(db): return None
    async def equipped(db, ids): return {int(ids[0]): worn} if worn else {}
    look.is_vip_active = is_vip
    look.skins_repo.equipped_batch, look.skins_repo.ensure_tables = equipped, ensure
    return asyncio.run(look.public_view(Db(), 5))


with_vip, without_vip = run(True), run(False)
assert with_vip["visible"] and with_vip["look"]["id"] == "void" and with_vip["look"]["tier"] == "SSS"
assert with_vip["look"]["pal"] and with_vip["look"]["kinds"] and with_vip["look"]["tokens"] and with_vip["look"]["items"]
assert not without_vip["visible"] and without_vip["hidden_reason"] == "vip_required" and without_vip["worn"]
assert set(without_vip["look"]) == {"name", "tier", "ceiling"}, "names and tiers only, nothing to render without VIP"
assert without_vip["look"]["tier"] == "SS", "SSS is shown capped without VIP"
assert run(True, worn=None)["look"] is None and run(True, worn=("gone", "D"))["look"] is None

rows = {}


def row_looks(vip_ids):
    async def vip_batch(db, ids): return {i for i in ids if i in vip_ids}
    async def equipped(db, ids): return {i: ("forest", "C") for i in ids}
    look.is_vip_active_batch = vip_batch
    look.skins_repo.equipped_batch = equipped
    return asyncio.run(look.nick_styles(Db(), [1, 2]))


rows = row_looks({1})
assert set(rows) == {1} and rows[1]["tier"] == "C" and "tokens" not in rows[1] and "items" not in rows[1], "list rows carry the compact look, VIP owners only"

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
assert card["appearance"]["look"]["id"] == "void"
print("OK: appearance tiers, VIP visibility rule and public card allow-list")
