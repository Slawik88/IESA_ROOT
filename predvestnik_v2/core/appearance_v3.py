"""Appearance V3: one place for cosmetic tiers and who may see what.

Rules (owner decisions, 2026-10):
  * Cosmetics and app skins of tiers D, C, B, A, S and SS can be equipped by anyone, with or without VIP.
  * Other players see a player's cosmetics, nickname style and skin only while that player has VIP.
    Without VIP the public card shows what is equipped, but does not render it.
  * The owner always sees their own look.
Tier of a cosmetic follows its collection (lineup) rarity, so no per-item table has to be kept in sync.
"""
from __future__ import annotations

from core.cosmetics import LINEUPS

TIERS = ("D", "C", "B", "A", "S", "SS", "SSS")
RARITY_TIER = {"common": "D", "rare": "C", "epic": "B", "legendary": "A", "mythic": "S", "artifact": "SS"}
USABLE_WITHOUT_VIP = frozenset({"D", "C", "B", "A", "S", "SS"})


def tier_of_lineup(lineup_id: str | None) -> str | None:
    rarity = (LINEUPS.get(lineup_id or "") or {}).get("rarity")
    return RARITY_TIER.get(str(rarity))


def tier_of_cosmetic(cosmetic: dict | None) -> str | None:
    return tier_of_lineup((cosmetic or {}).get("lineup"))


def usable_without_vip(tier: str | None) -> bool:
    return tier in USABLE_WITHOUT_VIP


def visible_to_others(owner_has_vip: bool) -> bool:
    return bool(owner_has_vip)
