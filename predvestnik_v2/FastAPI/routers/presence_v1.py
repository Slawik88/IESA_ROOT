"""Presence V1 API: the player's own privacy choice for "last seen"."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from services import presence_v1

router = APIRouter(prefix="/presence-v1", tags=["presence-v1"])


class VisibilityRequest(BaseModel):
    visibility: str


@router.get("/settings")
async def get_settings(db=Depends(get_db), user=Depends(require_tg_user)) -> dict:
    return await presence_v1.settings(db, int(user["id"]))


@router.post("/settings")
async def save_settings(body: VisibilityRequest, db=Depends(get_db), user=Depends(require_tg_user)) -> dict:
    try:
        result = await presence_v1.set_level(db, int(user["id"]), body.visibility)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return result
