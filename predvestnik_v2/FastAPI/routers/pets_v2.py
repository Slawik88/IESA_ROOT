"""Authenticated Mini App adapter for pets v2 «Тропа». Подключается в main.py только за флагом pets_v2."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from FastAPI.deps import get_db, require_tg_user
from core.pets_v2 import PetV2PolicyError
from infrastructure.repositories import chests_v1 as chest_repo, pets_v2 as repo, system_flags
from services import pets_v2 as service

router = APIRouter(prefix="/pets-v2", tags=["pets-v2"])


class StartRequest(BaseModel):
    pet_id: int = Field(gt=0)
    kind: str = Field(pattern="^(trek|expedition|watch)$")
    hours: int = Field(ge=3, le=24)
    route: str | None = Field(default=None, pattern="^(forest|pass|ruins|swamp)$")
    action_id: str = Field(min_length=1, max_length=96)


class ClaimRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=64)
    path: str | None = Field(default=None, pattern="^(careful|steady|bold)$")
    action_id: str = Field(min_length=1, max_length=96)


class BuildRequest(BaseModel):
    pet_id: int = Field(gt=0)
    calling: str | None = Field(default=None, pattern="^(feeder|guardian|seeker)$")
    traits: list[str] = Field(default_factory=list, max_length=3)
    talismans: list[str] = Field(default_factory=list, max_length=2)
    action_id: str = Field(min_length=1, max_length=96)


class CampRequest(BaseModel):
    building: str = Field(pattern="^(lounge|markers|workshop)$")
    action_id: str = Field(min_length=1, max_length=96)


class ReforgeRequest(BaseModel):
    talisman_id: str = Field(min_length=1, max_length=96)
    action_id: str = Field(min_length=1, max_length=96)


class TrackStartRequest(BaseModel):
    pet_id: int = Field(gt=0)
    action_id: str = Field(min_length=1, max_length=96)


class TrackOpenRequest(BaseModel):
    track_id: str = Field(min_length=1, max_length=64)
    cell: int = Field(ge=0, le=8)
    action_id: str = Field(min_length=1, max_length=96)


class TrialRequest(BaseModel):
    pet_id: int = Field(gt=0)
    difficulty: int = Field(ge=1, le=3)
    action_id: str = Field(min_length=1, max_length=96)


async def _ready(db) -> None:
    if not await system_flags.is_enabled(db, "pets_v2"):
        raise HTTPException(404, "Тропа пока закрыта.")
    await chest_repo.ensure_tables(db)
    await repo.ensure_tables(db)


@router.get("/me")
async def my_pets(db=Depends(get_db), user=Depends(require_tg_user)):
    await _ready(db)
    return await service.overview(db, int(user["id"]))


@router.post("/start")
async def start(body: StartRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    await _ready(db)
    try:
        return await service.start_run(db, user_id=int(user["id"]), pet_id=body.pet_id, kind=body.kind,
                                       hours=body.hours, route=body.route, action_id=body.action_id)
    except PetV2PolicyError as error:
        raise HTTPException(409, str(error))


@router.post("/claim")
async def claim(body: ClaimRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    await _ready(db)
    try:
        return await service.claim_run(db, user_id=int(user["id"]), run_id=body.run_id, path=body.path, action_id=body.action_id)
    except PetV2PolicyError as error:
        raise HTTPException(409, str(error))


@router.post("/build")
async def build(body: BuildRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    await _ready(db)
    try:
        return await service.set_build(db, user_id=int(user["id"]), pet_id=body.pet_id, calling=body.calling,
                                       traits=body.traits, talisman_ids=body.talismans, action_id=body.action_id)
    except PetV2PolicyError as error:
        raise HTTPException(409, str(error))


@router.post("/camp/upgrade")
async def camp_upgrade(body: CampRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    await _ready(db)
    try:
        return await service.camp_upgrade(db, user_id=int(user["id"]), building=body.building, action_id=body.action_id)
    except PetV2PolicyError as error:
        raise HTTPException(409, str(error))


@router.post("/talisman/reforge")
async def reforge(body: ReforgeRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    await _ready(db)
    try:
        return await service.reforge_talisman(db, user_id=int(user["id"]), talisman_id=body.talisman_id, action_id=body.action_id)
    except PetV2PolicyError as error:
        raise HTTPException(409, str(error))


@router.post("/track/start")
async def track_start(body: TrackStartRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    await _ready(db)
    try:
        return await service.start_track(db, user_id=int(user["id"]), pet_id=body.pet_id, action_id=body.action_id)
    except PetV2PolicyError as error:
        raise HTTPException(409, str(error))


@router.post("/track/open")
async def track_open(body: TrackOpenRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    await _ready(db)
    try:
        return await service.open_track_cell(db, user_id=int(user["id"]), track_id=body.track_id, cell=body.cell, action_id=body.action_id)
    except PetV2PolicyError as error:
        raise HTTPException(409, str(error))


@router.post("/trial")
async def trial(body: TrialRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    await _ready(db)
    try:
        return await service.submit_trial(db, user_id=int(user["id"]), pet_id=body.pet_id, difficulty=body.difficulty, action_id=body.action_id)
    except PetV2PolicyError as error:
        raise HTTPException(409, str(error))
