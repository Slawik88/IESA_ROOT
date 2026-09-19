"""Authenticated adapter for the release chest catalogue."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from FastAPI.deps import get_db, require_tab_enabled, require_tg_user
from core.chests_v1 import ChestPolicyError
from services import chests_v1


router = APIRouter(
    prefix="/chests-v1", tags=["chests-v1"],
    dependencies=[Depends(require_tab_enabled("content_chests_v1"))],
)


class PrepareRequest(BaseModel):
    action_id: str = Field(min_length=1, max_length=96)
    catalog_version: str = Field(min_length=1, max_length=96)
    catalog_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


@router.get("/me")
async def my_chests(db=Depends(get_db), user=Depends(require_tg_user)):
    return await chests_v1.overview(db, user_id=int(user["id"]))


@router.post("/prepare")
async def prepare(body: PrepareRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return await chests_v1.prepare_free_open(
            db, user_id=int(user["id"]), action_id=body.action_id,
            requested_catalog_version=body.catalog_version,
            requested_catalog_digest=body.catalog_digest,
        )
    except (ChestPolicyError, chests_v1.ChestKeyConflict, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/purchase")
async def purchase(body: PrepareRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return await chests_v1.purchase_key(
            db, user_id=int(user["id"]), action_id=body.action_id,
            requested_catalog_version=body.catalog_version,
            requested_catalog_digest=body.catalog_digest,
        )
    except (ChestPolicyError, chests_v1.ChestKeyConflict, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{open_id}/reveal")
async def reveal(open_id: str, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return await chests_v1.reveal(db, user_id=int(user["id"]), open_id=open_id)
    except (ChestPolicyError, chests_v1.ChestKeyConflict, ValueError) as exc:
        raise HTTPException(404, str(exc)) from exc
