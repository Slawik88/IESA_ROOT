"""
api/marriage.py — marriage status and proposal operations.

All functions are async; the mini app wraps them with async_to_sync.
"""
import html as _html


async def get_status(uid: int, chat_id: int) -> dict:
    """Return marriage status and singles list for the given user in chat.

    Returns {has_partner, partner_id, partner_name, married_at, singles}.
    singles is a list of {user_id, name, xp} for single users in chat,
    excluding uid itself.
    """
    from database.db import get_marriage, get_user, get_singles

    marriage = await get_marriage(uid, chat_id)
    has_partner = marriage is not None
    partner_id = marriage["partner_id"] if marriage else None
    married_at = marriage["married_at"] if marriage else None

    partner_name = None
    if partner_id:
        partner = await get_user(partner_id)
        partner_name = partner["full_name"] if partner else f"user_{partner_id}"

    singles_rows = await get_singles(chat_id, limit=20)
    singles = [
        {
            "user_id": r["user_id"],
            "name":    r["full_name"] or f"user_{r['user_id']}",
            "xp":      r["xp"] or 0,
        }
        for r in singles_rows
        if r["user_id"] != uid
    ]

    return {
        "has_partner":  has_partner,
        "partner_id":   partner_id,
        "partner_name": partner_name,
        "married_at":   str(married_at) if married_at else None,
        "singles":      singles,
    }


async def propose(uid: int, target_id: int, chat_id: int) -> dict:
    """Create a marriage proposal from uid to target_id.

    Raises ValueError with a Russian message on any validation error.
    Returns {ok, proposal_id, message}.
    """
    from database.db import get_marriage, get_user, create_marriage_proposal

    if uid == target_id:
        raise ValueError("Нельзя предложить руку самому себе")

    if await get_marriage(uid, chat_id):
        raise ValueError("Ты уже в браке. Сначала разведись.")

    if await get_marriage(target_id, chat_id):
        raise ValueError("Этот игрок уже состоит в браке.")

    to_user = await get_user(target_id)
    to_name = to_user["full_name"] if to_user else f"user_{target_id}"

    proposal_id = await create_marriage_proposal(uid, target_id, chat_id)

    return {
        "ok":          True,
        "proposal_id": proposal_id,
        "message":     f"Предложение отправлено игроку {_html.escape(to_name)}!",
    }
