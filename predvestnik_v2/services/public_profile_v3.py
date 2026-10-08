"""Public player card: an explicit allow-list over the aggregate profile, plus the appearance projection.

The aggregate (FastAPI.routers.profile.public_profile) is the single source of numbers; this module only
decides which of them another player may see and attaches the VIP-gated look.
"""
from __future__ import annotations


def shape(base: dict, appearance: dict, *, is_self: bool, presence: dict | None = None, presence_level: str | None = None) -> dict:
    pets = base.get("pets") or []
    active_pet = next((pet for pet in pets if pet.get("active")), None)
    vip = base.get("vip")
    return {
        "ref": base["profile_ref"],
        "name": base["display_name"],
        "rank": base.get("rank"),
        "is_self": bool(is_self),
        "vip": {
            "label": vip.get("label"), "days_left": vip.get("days_left"),
            "badge": vip.get("badge"), "badge_position": vip.get("badge_position"),
        } if vip else None,
        "avatar": base.get("avatar") if vip else None,
        "level": {
            "level": int(base.get("account_level") or 1),
            "xp_into": int(base.get("xp_into") or 0),
            "xp_to_next": int(base.get("xp_to_next") or 0),
        },
        "stats": {
            "messages": int(base.get("messages_all_time") or 0),
            "streak": int(base.get("streak") or 0),
            "achievements": int(base.get("achievements") or 0),
            "joined_date": base.get("joined_date"),
            "has_partner": bool(base.get("partner")),
            "pets_total": len(pets),
            "active_pet": {"name": active_pet["name"], "rarity": active_pet.get("rarity"), "level": active_pet.get("level")} if active_pet else None,
        },
        "games": base.get("game_results") or {},
        "paths": base.get("achievement_paths") or {},
        "best_achievement": base.get("best_achievement"),
        "appearance": appearance,
        "marks": list(base.get("marks") or []),
        # label only, never a timestamp; None when the owner hides it. The owner also learns their own setting.
        "presence": {"state": presence["state"], "label": presence["label"]} if presence else None,
        **({"presence_level": presence_level} if is_self else {}),
    }
