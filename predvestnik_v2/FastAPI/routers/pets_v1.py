"""Authenticated Mini App adapter for the new pet foundation."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from FastAPI.deps import get_db, require_tg_user
from services.pets_v1 import PetConflict, choose_expedition, feed_pet, select_active_pet, start_activity, overview
from core.pets_v1 import PetPolicyError
from infrastructure.repositories.pets_v1 import ensure_tables
from infrastructure.repositories.chests_v1 import ensure_tables as ensure_chest_tables

router = APIRouter(prefix="/pets-v1", tags=["pets-v1"])

class ActivePetRequest(BaseModel):
    pet_id: int = Field(gt=0)
    action_id: str = Field(min_length=1, max_length=96)

class StartActivityRequest(BaseModel):
    kind: str = Field(pattern="^(trek|expedition)$")
    hours: int = Field(ge=3, le=9)
    action_id: str = Field(min_length=1, max_length=96)

class ExpeditionDecisionRequest(BaseModel):
    decision: str = Field(pattern="^(careful|steady|bold)$")
    action_id: str = Field(min_length=1, max_length=96)

class FeedPetRequest(BaseModel):
    pet_id: int = Field(gt=0)
    food_id: str = Field(min_length=1, max_length=64)
    action_id: str = Field(min_length=1, max_length=96)

async def _ensure_release_tables(db) -> None:
    await ensure_chest_tables(db)
    await ensure_tables(db)

@router.get("/me")
async def my_pets(db=Depends(get_db), user=Depends(require_tg_user)):
    # A web worker can serve the first request before the co-hosted bot's
    # schema initializer reaches this new table.  The idempotent ensure keeps
    # the read path fail-safe during a rolling deployment.
    await _ensure_release_tables(db)
    return await overview(db, int(user["id"]))

@router.post("/active")
async def set_active_pet(body: ActivePetRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        await _ensure_release_tables(db)
        return await select_active_pet(db, int(user["id"]), body.pet_id, body.action_id)
    except (PetPolicyError, PetConflict) as error:
        raise HTTPException(409, str(error))

@router.post("/activity")
async def start_pet_activity(body: StartActivityRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        await _ensure_release_tables(db)
        return await start_activity(db, user_id=int(user["id"]), kind=body.kind, hours=body.hours, action_id=body.action_id)
    except (PetPolicyError, PetConflict) as error:
        raise HTTPException(409, str(error))

@router.post("/expedition/decision")
async def decide_expedition(body: ExpeditionDecisionRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        await _ensure_release_tables(db)
        return await choose_expedition(db, user_id=int(user["id"]), decision=body.decision, action_id=body.action_id)
    except (PetPolicyError, PetConflict) as error:
        raise HTTPException(409, str(error))

@router.post("/feed")
async def feed(body: FeedPetRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        await _ensure_release_tables(db)
        return await feed_pet(
            db, user_id=int(user["id"]), pet_id=body.pet_id,
            food_id=body.food_id, action_id=body.action_id,
        )
    except (PetPolicyError, PetConflict) as error:
        raise HTTPException(409, str(error))
