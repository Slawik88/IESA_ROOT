"""Pure projection for the first modular Predvestnik home screen.

The hub is deliberately read-only.  It combines durable facts that already
exist (profile, family, clan, pets and ledger history) but never settles a
reward, opens a family bank or changes account progression.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from services.leveling import account_progress


def build_hub_view(
    *,
    identity: Mapping[str, Any],
    family: Mapping[str, Any] | None,
    clan: Mapping[str, Any] | None,
    active_pet: Mapping[str, Any] | None,
    transactions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return the stable public contract for ``GET /hub/me``.

    XP is the source of truth for the visible level.  Wallet/family balances
    are projected from the audited custody balance; mutations stay in the
    dedicated family-wallet service rather than this read model.
    """
    xp = max(0, int(identity.get("account_xp") or 0))
    progress = account_progress(xp)
    family_view = None
    if family:
        family_view = {
            "marriage_id": int(family["id"]),
            "partner_id": int(family["partner_id"]),
            "partner_name": str(family.get("partner_name") or "Партнёр"),
            "since": str(family.get("marriage_date") or ""),
            "bank_status": "active_receipted",
            "balances": {
                "mora": float(family.get("family_balance") or 0),
                "diamonds": float(family.get("family_balance_diamonds") or 0),
                "dark_mora": float(family.get("family_balance_dark_mora") or 0),
                "zarniki": float(family.get("family_balance_zarniki") or 0),
            },
            "recent_gifts": list(family.get("recent_gifts") or ()),
        }

    clan_view = None
    if clan:
        clan_view = {
            "id": int(clan["clan_id"]),
            "name": str(clan.get("name") or ""),
            "tag": str(clan.get("tag") or ""),
            "emblem": str(clan.get("emblem") or "🛡"),
            "role": str(clan.get("role") or "fighter"),
            "one_clan_only": True,
        }

    pet_view = None
    if active_pet:
        pet_view = {
            "id": int(active_pet["id"]),
            "name": str(active_pet.get("name") or "Питомец"),
            "species_id": str(active_pet.get("species_id") or ""),
            "fatigue": int(active_pet.get("fatigue") or 0),
        }

    return {
        "version": "hub-v1",
        "identity": {
            "user_id": int(identity["user_tg_id"]),
            "username": str(identity.get("user_tg_username") or "Игрок"),
            "level": progress["level"],
            "account_xp": xp,
            "xp_into_level": progress["xp_into"],
            "xp_to_next_level": progress["xp_need"],
        },
        "primary_action": None,
        "modules": {
            "games": {"status": "planned"},
            "pets": pet_view,
            "family": family_view,
            "clan": clan_view,
            "transactions": list(transactions),
        },
        "economy_status": "family_wallet_active_receipted",
    }
