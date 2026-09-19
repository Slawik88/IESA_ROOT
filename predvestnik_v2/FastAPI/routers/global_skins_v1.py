"""Authenticated reader/selector for visual-only Mini App skins."""
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from FastAPI.deps import get_db, require_tg_user
from services import global_skins_v1 as skins


router = APIRouter(prefix="/global-skins-v1", tags=["global-skins-v1"])


class SelectRequest(BaseModel):
    skin_id: str = Field(min_length=1, max_length=80)


class BuyRequest(BaseModel):
    skin_id: str = Field(min_length=1, max_length=80)


def _economic_key(value: str) -> str:
    key = value.strip()
    if not key or len(key) > 120:
        raise HTTPException(400, "Idempotency-Key должен содержать 1–120 символов.")
    return f"global-skin:{key}"


@router.get("/me")
async def my_skin(db=Depends(get_db), user=Depends(require_tg_user)):
    return await skins.state(db, int(user["id"]))


@router.post("/select")
async def select_skin(body: SelectRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return await skins.select(db, int(user["id"]), body.skin_id)
    except skins.SkinConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/buy")
async def buy_skin(
    body: BuyRequest,
    db=Depends(get_db),
    user=Depends(require_tg_user),
    request_key: str = Header(alias="Idempotency-Key"),
):
    try:
        message, state = await skins.buy(
            db,
            int(user["id"]),
            body.skin_id,
            idempotency_key=_economic_key(request_key),
        )
        await db.commit()
        return {"ok": True, "message": message, "state": state}
    except skins.SkinConflict as exc:
        raise HTTPException(409, str(exc)) from exc
