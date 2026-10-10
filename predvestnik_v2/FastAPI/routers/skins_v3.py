"""Skins V3 API: catalog and own state, buy, equip, upgrade, Essence."""
from fastapi import APIRouter, Depends, Header, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from FastAPI.deps import get_db, require_tg_user
from services import skins_v3 as skins

router = APIRouter(prefix="/skins-v3", tags=["skins-v3"])


class SkinRequest(BaseModel):
    skin_id: str = Field(min_length=1, max_length=40)


class EquipRequest(BaseModel):
    skin_id: str | None = Field(default=None, max_length=40)


class EssenceRequest(BaseModel):
    zarniki: int = Field(ge=1, le=1000)


def _key(value: str) -> str:
    key = value.strip()
    if not key or len(key) > 100:
        raise HTTPException(status_code=400, detail="Idempotency-Key должен содержать 1–100 символов.")
    return key


async def _run(call):
    try:
        return await call
    except skins.SkinConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("skins_v3 failed")
        raise HTTPException(status_code=500, detail="Скины временно недоступны") from exc


@router.get("/me")
async def my_state(db=Depends(get_db), user=Depends(require_tg_user)) -> dict:
    return await _run(skins.state(db, int(user["id"])))


@router.post("/buy")
async def buy(body: SkinRequest, db=Depends(get_db), user=Depends(require_tg_user), request_key: str = Header(alias="Idempotency-Key")) -> dict:
    message, state = await _run(skins.buy(db, int(user["id"]), body.skin_id, idempotency_key=_key(request_key)))
    await db.commit()
    return {"ok": True, "message": message, "state": state}


@router.post("/equip")
async def equip(body: EquipRequest, db=Depends(get_db), user=Depends(require_tg_user)) -> dict:
    state = await _run(skins.equip(db, int(user["id"]), body.skin_id))
    await db.commit()
    return state


@router.post("/upgrade")
async def upgrade(body: SkinRequest, db=Depends(get_db), user=Depends(require_tg_user), request_key: str = Header(alias="Idempotency-Key")) -> dict:
    message, state = await _run(skins.upgrade(db, int(user["id"]), body.skin_id, idempotency_key=_key(request_key)))
    await db.commit()
    return {"ok": True, "message": message, "state": state}


@router.post("/essence")
async def buy_essence(body: EssenceRequest, db=Depends(get_db), user=Depends(require_tg_user), request_key: str = Header(alias="Idempotency-Key")) -> dict:
    message, state = await _run(skins.buy_essence(db, int(user["id"]), body.zarniki, idempotency_key=_key(request_key)))
    await db.commit()
    return {"ok": True, "message": message, "state": state}
