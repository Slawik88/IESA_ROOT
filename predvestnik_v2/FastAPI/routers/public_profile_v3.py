"""Public player card for the Mini App (opened from leaderboards and any visible nickname)."""
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from FastAPI.deps import get_db, require_tg_user
from FastAPI.routers import profile as profile_router
from infrastructure.repositories import public_profiles_v1 as public_profiles
from services import appearance_public_v3, public_profile_v3

router = APIRouter(prefix="/public-profile-v3", tags=["public-profile-v3"])


@router.get("/{profile_ref}")
async def public_card(profile_ref: str, db=Depends(get_db), user=Depends(require_tg_user)) -> dict:
    target_id = await public_profiles.resolve_reference(db, profile_ref=profile_ref)
    if target_id is None:
        raise HTTPException(status_code=404, detail="Игрок не найден.")
    try:
        base = await profile_router.public_profile(profile_ref, db=db, user=user)
        look = await appearance_public_v3.public_view(db, int(target_id))
        return public_profile_v3.shape(base, look, is_self=int(target_id) == int(user["id"]))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("public_profile_v3 failed")
        raise HTTPException(status_code=500, detail="Профиль временно недоступен") from exc
