"""Тонкий HTTP-адаптер Reconstruction 3.0."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from FastAPI.deps import get_db, require_tg_user
from core.reconstruction import FEATURE_FLAG_KEY
from infrastructure.repositories import system_flags
from services import reconstruction as game


router = APIRouter(prefix="/reconstruction", tags=["reconstruction"])


class StartBody(BaseModel):
    encounter_id: str = game.FIRST_ENCOUNTER


class ActionBody(BaseModel):
    action_id: str = Field(min_length=1, max_length=96)
    type: Literal["frame", "strike", "choose_upgrade"]
    delta_ms: int | None = Field(default=None, ge=0, le=500)
    upgrade_id: str | None = None
    challenge_id: int | None = Field(default=None, ge=1)
    target_slot: Literal["left", "center", "right"] | None = None


class MemoryBody(BaseModel):
    memory_id: str


async def _guard(db) -> None:
    if not await system_flags.is_enabled(db, FEATURE_FLAG_KEY):
        raise HTTPException(404, "Reconstruction 3.0 пока доступна только на dev-стенде.")


def _raise_service_error(exc: Exception) -> None:
    status = 409 if isinstance(exc, game.ReconstructionConflict) else 400
    raise HTTPException(status, str(exc)) from exc


@router.get("")
async def get_overview(db=Depends(get_db), user=Depends(require_tg_user)):
    await _guard(db)
    return await game.overview(db, int(user["id"]))


@router.post("/start")
async def start(body: StartBody, db=Depends(get_db), user=Depends(require_tg_user)):
    await _guard(db)
    try:
        return await game.start_encounter(db, int(user["id"]), body.encounter_id)
    except game.ReconstructionError as exc:
        _raise_service_error(exc)


@router.post("/runs/{run_id}/actions")
async def action(
    run_id: int,
    body: ActionBody,
    db=Depends(get_db),
    user=Depends(require_tg_user),
):
    await _guard(db)
    payload: dict[str, Any] = body.model_dump(exclude={"action_id"}, exclude_none=True)
    try:
        return await game.apply_run_action(
            db, int(user["id"]), run_id, body.action_id, payload
        )
    except game.ReconstructionError as exc:
        _raise_service_error(exc)


@router.post("/memory")
async def choose_memory(
    body: MemoryBody, db=Depends(get_db), user=Depends(require_tg_user)
):
    await _guard(db)
    try:
        return await game.choose_memory(db, int(user["id"]), body.memory_id)
    except game.ReconstructionError as exc:
        _raise_service_error(exc)
