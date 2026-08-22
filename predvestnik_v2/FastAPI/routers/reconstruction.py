"""Тонкий HTTP-адаптер Reconstruction 3.0."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from FastAPI.deps import get_db, require_tg_user
from services import reconstruction as game
from services import companions_v3 as companions


router = APIRouter(prefix="/reconstruction", tags=["reconstruction"])


class StartBody(BaseModel):
    encounter_id: str = game.FIRST_ENCOUNTER
    practice: bool = False


class ActionBody(BaseModel):
    action_id: str = Field(min_length=1, max_length=96)
    expected_revision: int = Field(ge=0)
    type: Literal["frame", "strike", "choose_upgrade", "branch_action"]
    delta_ms: int | None = Field(default=None, ge=0, le=500)
    upgrade_id: str | None = None
    challenge_id: int | None = Field(default=None, ge=1)
    target_slot: Literal["left", "center", "right"] | None = None
    command: Literal[
        "vow_keep", "vow_release", "manual_discharge",
        "forbidden_toggle", "tide_swap", "companion_guardian_window",
    ] | None = None
    decision_id: str | None = Field(default=None, max_length=96)
    enabled: bool | None = None


class MemoryBody(BaseModel):
    memory_id: str


class UnitBranchBody(BaseModel):
    unit_id: str
    branch_id: str


class ChroniclePathBody(BaseModel):
    path_id: Literal["ink", "ash"]


class CompanionPetBody(BaseModel):
    pet_id: int = Field(gt=0)


class CompanionRoleBody(BaseModel):
    role_id: str = Field(min_length=1, max_length=48)


class CompanionCareBody(BaseModel):
    pet_id: int = Field(gt=0)
    action: Literal["feed", "play", "groom"]
    action_id: str = Field(min_length=1, max_length=96)


class CompanionExpeditionBody(BaseModel):
    pet_id: int = Field(gt=0)
    duration_hours: Literal[2, 6, 12]
    action_id: str = Field(min_length=1, max_length=96)


class CompanionClaimBody(BaseModel):
    action_id: str = Field(min_length=1, max_length=96)


def _raise_service_error(exc: Exception) -> None:
    status = 409 if isinstance(exc, game.ReconstructionConflict) else 400
    raise HTTPException(status, str(exc)) from exc


def _raise_companion_error(exc: Exception) -> None:
    status = 409 if isinstance(exc, companions.CompanionConflict) else 400
    raise HTTPException(status, str(exc)) from exc


@router.get("")
async def get_overview(db=Depends(get_db), user=Depends(require_tg_user)):
    return await game.overview(db, int(user["id"]))


@router.post("/start")
async def start(body: StartBody, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        companion_role_id = await companions.selected_role(db, int(user["id"]))
        return await game.start_encounter(
            db,
            int(user["id"]),
            body.encounter_id,
            practice=body.practice,
            companion_role_id=companion_role_id,
        )
    except game.ReconstructionError as exc:
        _raise_service_error(exc)


@router.post("/runs/{run_id}/actions")
async def action(
    run_id: int,
    body: ActionBody,
    db=Depends(get_db),
    user=Depends(require_tg_user),
):
    payload: dict[str, Any] = body.model_dump(
        exclude={"action_id", "expected_revision"},
        exclude_none=True,
    )
    try:
        return await game.apply_run_action(
            db,
            int(user["id"]),
            run_id,
            body.action_id,
            body.expected_revision,
            payload,
        )
    except game.ReconstructionError as exc:
        _raise_service_error(exc)


@router.post("/runs/{run_id}/cancel")
async def cancel(
    run_id: int,
    db=Depends(get_db),
    user=Depends(require_tg_user),
):
    try:
        return await game.cancel_run(db, int(user["id"]), run_id)
    except game.ReconstructionError as exc:
        _raise_service_error(exc)


@router.post("/memory")
async def choose_memory(
    body: MemoryBody, db=Depends(get_db), user=Depends(require_tg_user)
):
    try:
        return await game.choose_memory(db, int(user["id"]), body.memory_id)
    except game.ReconstructionError as exc:
        _raise_service_error(exc)


@router.post("/units/branch")
async def choose_unit_branch(
    body: UnitBranchBody, db=Depends(get_db), user=Depends(require_tg_user)
):
    try:
        return await game.choose_unit_branch(
            db, int(user["id"]), body.unit_id, body.branch_id
        )
    except game.ReconstructionError as exc:
        _raise_service_error(exc)


@router.post("/chronicle/path")
async def choose_chronicle_path(
    body: ChroniclePathBody, db=Depends(get_db), user=Depends(require_tg_user)
):
    try:
        return await game.choose_chronicle_path(db, int(user["id"]), body.path_id)
    except game.ReconstructionError as exc:
        _raise_service_error(exc)


@router.get("/companions")
async def companion_overview(db=Depends(get_db), user=Depends(require_tg_user)):
    return await companions.overview(db, int(user["id"]))


@router.post("/companions/active")
async def companion_active(
    body: CompanionPetBody, db=Depends(get_db), user=Depends(require_tg_user)
):
    try:
        return await companions.select_active_pet(db, int(user["id"]), body.pet_id)
    except companions.CompanionError as exc:
        _raise_companion_error(exc)


@router.post("/companions/role")
async def companion_role(
    body: CompanionRoleBody, db=Depends(get_db), user=Depends(require_tg_user)
):
    try:
        return await companions.select_role(db, int(user["id"]), body.role_id)
    except companions.CompanionError as exc:
        _raise_companion_error(exc)


@router.post("/companions/care")
async def companion_care(
    body: CompanionCareBody, db=Depends(get_db), user=Depends(require_tg_user)
):
    try:
        return await companions.care(
            db, int(user["id"]), body.pet_id, body.action, body.action_id
        )
    except companions.CompanionError as exc:
        _raise_companion_error(exc)


@router.post("/companions/expeditions/start")
async def companion_expedition_start(
    body: CompanionExpeditionBody, db=Depends(get_db), user=Depends(require_tg_user)
):
    try:
        return await companions.start_expedition(
            db, int(user["id"]), body.pet_id, body.duration_hours, body.action_id
        )
    except companions.CompanionError as exc:
        _raise_companion_error(exc)


@router.post("/companions/expeditions/claim")
async def companion_expedition_claim(
    body: CompanionClaimBody, db=Depends(get_db), user=Depends(require_tg_user)
):
    try:
        return await companions.claim_expeditions(
            db, int(user["id"]), body.action_id
        )
    except companions.CompanionError as exc:
        _raise_companion_error(exc)
