"""COS-N1: сервер сам определяет родословную надетого образа.

Клиент получает lineup id уже вместе с активной косметикой и не поддерживает
отдельную карту cosmetic_id → lineup. Приоритет: рамка → гало → эффект → фон.
VIP-фильтр применяется раньше родословной, поэтому «спящий» предмет не окрашивает
профиль.
"""
import asyncio
import pathlib
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from services.cosmetics import get_active_cosmetics


async def _active(loadout: dict[str, str], *, vip: bool) -> dict:
    with (
        patch("services.cosmetics._loadout", new=AsyncMock(return_value=loadout)),
        patch("services.cosmetics.is_vip_active", new=AsyncMock(return_value=vip)),
    ):
        return await get_active_cosmetics(object(), 42)


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

    without_frame = await _active({
        "avatar_halo": "cos_avatar_halo_moon_ripple",
        "card_fx": "cos_card_fx_ryujin_current",
        "profile_bg": "cos_profile_bg_forest",
    }, vip=True)
    assert without_frame["lineage"] == {"id": "moon_lotus", "source_slot": "avatar_halo"}

    # Artifact-рамка без VIP скрыта. Родословная должна перейти к доступному
    # common-фону, а не оставлять на профиле цвет невидимого предмета.
    sleeping_frame = await _active({
        "avatar_frame": "cos_avatar_frame_moon_lotus",
        "profile_bg": "cos_profile_bg_forest",
    }, vip=False)
    assert "avatar_frame" not in sleeping_frame
    assert sleeping_frame["lineage"] == {"id": "forest", "source_slot": "profile_bg"}

    print("OK: родословная образа приходит с сервера, соблюдает приоритет слотов и VIP-фильтр")


if __name__ == "__main__":
    asyncio.run(main())
