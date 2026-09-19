"""Read-only modular home projection for the Mini App."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories import clans as clans_repo
from infrastructure.repositories.marriages import get_received_gifts, get_user_marriage
from infrastructure.repositories.wallet_log import get_recent
from services.hub_v1 import build_hub_view

router = APIRouter(prefix="/hub", tags=["hub"])


@router.get("/me")
async def my_hub(db=Depends(get_db), user=Depends(require_tg_user)):
    """Return the home screen projection without changing any player state."""
    user_id = int(user["id"])
    async with db.execute(
        "SELECT user_tg_id, user_tg_username, COALESCE(account_xp, 0) AS account_xp "
        "FROM users WHERE user_tg_id = ?",
        (user_id,),
    ) as cursor:
        identity = await cursor.fetchone()
    if not identity:
        raise HTTPException(404, "Профиль не найден. Напишите боту, чтобы зарегистрироваться.")

    marriage = await get_user_marriage(db, user_id)
    family = None
    if marriage:
        partner_id = int(marriage["user2_id"] if int(marriage["user1_id"]) == user_id else marriage["user1_id"])
        partner_name = marriage["user2_name"] if int(marriage["user1_id"]) == user_id else marriage["user1_name"]
        family = dict(marriage)
        family["partner_id"] = partner_id
        family["partner_name"] = partner_name
        family["recent_gifts"] = [
            {"gift_id": str(item["gift_id"]), "sent_at": str(item["sent_at"])}
            for item in await get_received_gifts(db, user_id, 3)
        ]

    clan = await clans_repo.get_user_clan(db, user_id)
    async with db.execute(
        "SELECT id, name, species_id, fatigue FROM pets "
        "WHERE owner_id = ? AND placement = 'active' ORDER BY id LIMIT 1",
        (user_id,),
    ) as cursor:
        active_pet = await cursor.fetchone()

    transactions = [
        {
            "id": int(item["id"]),
            "source": str(item.get("source") or ""),
            "created_at": str(item.get("created_at") or ""),
            "delta_mora": float(item.get("delta_mora") or 0),
            "delta_diamonds": float(item.get("delta_diamonds") or 0),
            "delta_dark_mora": float(item.get("delta_dark_mora") or 0),
            "delta_zarniki": float(item.get("delta_zarniki") or 0),
        }
        for item in await get_recent(db, user_id, n=3)
    ]
    return build_hub_view(
        identity=dict(identity), family=family, clan=clan,
        active_pet=dict(active_pet) if active_pet else None,
        transactions=transactions,
    )
