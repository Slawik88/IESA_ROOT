"""Public player card for the Mini App (opened from leaderboards and any visible nickname)."""
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from FastAPI.deps import get_db, require_tg_user
from FastAPI.routers import profile as profile_router
from infrastructure.repositories import public_profiles_v1 as public_profiles
from services import appearance_public_v3, gifts_v2, presence_v1, public_profile_v3

router = APIRouter(prefix="/public-profile-v3", tags=["public-profile-v3"])


async def _gifts_block(db, target_id: int, viewer_id: int) -> dict | None:
    """Gift showcase of the card (None while gifts_v2 is off). A gifts failure never takes the whole card down."""
    try:
        return await gifts_v2.public_view(db, target_id=target_id, viewer_id=viewer_id)
    except Exception:
        logger.exception("public_profile_v3: gifts block failed")
        return None


@router.get("/{profile_ref}")
async def public_card(profile_ref: str, db=Depends(get_db), user=Depends(require_tg_user)) -> dict:
    target_id = await public_profiles.resolve_reference(db, profile_ref=profile_ref)
    if target_id is None:
        raise HTTPException(status_code=404, detail="Игрок не найден.")
    try:
        base = await profile_router.public_profile(profile_ref, db=db, user=user)
        look = await appearance_public_v3.public_view(db, int(target_id))
        is_self = int(target_id) == int(user["id"])
        presence = await presence_v1.view_for(db, int(target_id), int(user["id"]))
        level = (await presence_v1.settings(db, int(target_id)))["visibility"] if is_self else None
        gifts = await _gifts_block(db, int(target_id), int(user["id"]))
        return public_profile_v3.shape(base, look, is_self=is_self, presence=presence, presence_level=level, gifts=gifts)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("public_profile_v3 failed")
        raise HTTPException(status_code=500, detail="Профиль временно недоступен") from exc
