"""COS-N1: per-item VIP filter and owner-only fitting projection."""
import asyncio
import pathlib
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from services.cosmetics import (
    get_active_cosmetics,
    get_fitting_cosmetics,
    get_fitting_inventory,
    get_flex_cosmetics_batch,
)
from core.cosmetics import COSMETICS, LINEUPS, is_vip_locked


async def _active(loadout: dict[str, str], *, vip: bool) -> dict:
    with (
        patch("services.cosmetics._loadout", new=AsyncMock(return_value=loadout)),
        patch("services.cosmetics.is_vip_active", new=AsyncMock(return_value=vip)),
    ):
        return await get_active_cosmetics(object(), 42)


async def _fitting(loadout: dict[str, str], *, vip: bool) -> dict:
    with (
        patch("services.cosmetics._loadout", new=AsyncMock(return_value=loadout)),
        patch("services.cosmetics.is_vip_active", new=AsyncMock(return_value=vip)),
    ):
        return await get_fitting_cosmetics(object(), 42)


class _RowsCursor:
    def __init__(self, rows):
        self.rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def fetchall(self):
        return self.rows


class _RowsDb:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, *_args):
        return _RowsCursor(self.rows)


async def main() -> None:
    mixed = await _active({
        "avatar_frame": "cos_avatar_frame_hanami_branches",
        "avatar_halo": "cos_avatar_halo_moon_ripple",
        "card_fx": "cos_card_fx_ryujin_current",
        "profile_bg": "cos_profile_bg_forest",
    }, vip=True)
    assert mixed["lineage"] == {"id": "hanami", "source_slot": "avatar_frame"}
    assert mixed["avatar_frame"]["lineup"] == "hanami"
    assert mixed["avatar_halo"]["lineup"] == "moon_lotus"
    # Whole-card palette follows the background when a player freely mixes
    # items; only the frame leads the single avatar accent.
    assert mixed["composition"] == {
        "dominant_lineup": "forest", "dominant_slot": "profile_bg",
        "identity": {"lead_slot": "avatar_frame", "ambient_slot": "avatar_halo"},
        "layer_count": 4,
    }

    without_frame = await _active({
        "avatar_halo": "cos_avatar_halo_moon_ripple",
        "card_fx": "cos_card_fx_ryujin_current",
        "profile_bg": "cos_profile_bg_forest",
    }, vip=True)
    assert without_frame["lineage"] == {"id": "moon_lotus", "source_slot": "avatar_halo"}
    assert without_frame["composition"]["dominant_lineup"] == "forest"
    assert without_frame["composition"]["identity"] == {"lead_slot": "avatar_halo", "ambient_slot": None}

    # Owner view: paid shop cosmetics are usable without VIP (others' view is gated in appearance_public_v3).
    inactive_public = await _active({
        "avatar_frame": "cos_avatar_frame_moon_lotus",
        "profile_bg": "cos_profile_bg_forest",
    }, vip=False)
    assert inactive_public["avatar_frame"]["lineup"] == "moon_lotus"
    assert inactive_public["profile_bg"]["lineup"] == "forest"
    assert inactive_public["composition"]["layer_count"] == 2
    assert not [cid for cid, item in COSMETICS.items() if item.get("price") and item.get("vip_required")]
    assert not [lid for lid, lineup in LINEUPS.items() if lineup.get("price") and lineup.get("vip_required")]
    assert is_vip_locked({"vip_required": True, "price": None}) is True
    assert is_vip_locked({"vip_required": True, "price": [{"zarniki": 1}]}) is False

    # Ownership/loadout are preserved privately and return intact after renewal.
    inactive_fitting = await _fitting({
        "avatar_frame": "cos_avatar_frame_moon_lotus",
        "profile_bg": "cos_profile_bg_forest",
    }, vip=False)
    assert inactive_fitting["vip_inactive"] is False
    assert inactive_fitting["cosmetics"]["avatar_frame"]["id"] == "cos_avatar_frame_moon_lotus"
    renewed = await _active({
        "avatar_frame": "cos_avatar_frame_moon_lotus",
        "profile_bg": "cos_profile_bg_forest",
    }, vip=True)
    assert renewed["avatar_frame"]["lineup"] == "moon_lotus"
    assert renewed["lineage"] == {"id": "moon_lotus", "source_slot": "avatar_frame"}
    assert renewed["composition"]["dominant_lineup"] == "forest"

    # Wardrobe data remains private, has no checkout payload and does not grant
    # items merely because the fitting room was opened.
    with (
        patch("services.cosmetics._owned", new=AsyncMock(return_value={"cos_avatar_frame_moon_lotus"})),
        patch("services.cosmetics._loadout", new=AsyncMock(return_value={"avatar_frame": "cos_avatar_frame_moon_lotus"})),
        patch("services.cosmetics.is_vip_active", new=AsyncMock(return_value=False)),
    ):
        wardrobe = await get_fitting_inventory(object(), 42)
    frame = next(x for x in wardrobe["slots"]["avatar_frame"] if x["id"] == "cos_avatar_frame_moon_lotus")
    assert frame["owned"] is True and frame["equipped"] is True
    assert "price" not in frame
    assert wardrobe["saved_look"]["vip_inactive"] is False
    assert wardrobe["transfers"]["available"] is False

    # Policy 2026-10 (core/appearance_v3.py): the owner always sees their own look, but the compact
    # projection used for other players' rows shows a nickname style only while the owner has VIP.
    rows = [(42, "name_glow", "cos_name_glow_moon"), (42, "title", "cos_title_forest_wanderer")]
    with patch("services.cosmetics.is_vip_active_batch", new=AsyncMock(return_value=set())):
        assert await get_flex_cosmetics_batch(_RowsDb(rows), [42]) == {}
    with patch("services.cosmetics.is_vip_active_batch", new=AsyncMock(return_value={42})):
        flex = await get_flex_cosmetics_batch(_RowsDb(rows), [42])
    assert flex[42]["glow"] == COSMETICS["cos_name_glow_moon"]["css"]
    assert flex[42]["title"] == COSMETICS["cos_title_forest_wanderer"]["text"]

    print("OK: owner sees own look without VIP; others see nickname styles only with VIP; wardrobe stays private")


if __name__ == "__main__":
    asyncio.run(main())
