"""Public decorations only; never read roles, private choices or game history."""
from loguru import logger

from infrastructure.repositories import public_profiles_v1 as profiles, users
from services import appearance_public_v3, avatar_photos, marks_v1
from services.vip import is_vip_active_batch


def plain_player(player: dict) -> dict:
    return {"look": None, "avatar": None, "avatar_state": "vip_only", "mark": None,
            "level": 1, "is_bot": bool(player.get("is_bot", False))}


async def player_presentations(db, players: list[dict]) -> dict[int, dict]:
    """Batch the same public look/mark/photo projections used by the profile and top.

    Standalone rooms also work before the profile schema exists. A cosmetic lookup
    failure rolls back its savepoint, keeping the surrounding room transaction usable.
    """
    out = {p["id"]: plain_player(p) for p in players}
    ids = list(out)
    if not ids or not await db.connection.fetchval(
            "SELECT to_regclass('users') IS NOT NULL AND to_regclass('vip_subscriptions') IS NOT NULL"):
        return out
    try:
        async with db.connection.transaction():
            vip_ids = await is_vip_active_batch(db, ids)
            looks = await appearance_public_v3.nick_styles(db, list(vip_ids))
            refs = await profiles.ensure_references(db, vip_ids)
            avatars = await avatar_photos.views(db, refs) if refs else {}
            marks = await marks_v1.top_mark_batch(db, ids)
            levels = await users.account_levels(db, ids)
            for uid in ids:
                avatar = avatars.get(uid)
                out[uid] = {**out[uid], "look": looks.get(uid) if uid in vip_ids else None,
                            "avatar": avatar.avatar if avatar and uid in vip_ids else None,
                            "avatar_state": avatar.state if avatar and uid in vip_ids else "vip_only",
                            "mark": marks.get(uid), "level": levels.get(uid, 1)}
    except Exception:
        logger.exception("Online Mafia public player decorations unavailable")
    return out
