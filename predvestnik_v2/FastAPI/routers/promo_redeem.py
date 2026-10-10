"""Ввод промокода игроком из Mini App: те же коды и те же награды, что у «бот промокод КОД» (services/promo_v2)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from FastAPI.deps import get_db, require_tg_user
from services import promo_v2

router = APIRouter(prefix="/promo-v2", tags=["promo-v2"])


class RedeemRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)


@router.post("/redeem")
async def redeem(body: RedeemRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        result = await promo_v2.redeem(db, user_id=int(user["id"]), code=body.code, chat_id=None)
    except promo_v2.PromoError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "code": result.code, "granted": result.granted}
