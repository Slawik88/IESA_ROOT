"""Authenticated adapter for the shop screen (ECO-04 PR-B), dark behind the shop_v1 flag."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StrictInt

from FastAPI.deps import get_db, require_tg_user
from core.zarniki_exchange_v1 import DAILY_ZARNIKI_CAP
from services import shop_v1


router = APIRouter(prefix="/shop-v1", tags=["shop-v1"])


class BuyRequest(BaseModel):
    item_id: str = Field(min_length=1, max_length=64)
    action_id: str = Field(min_length=1, max_length=96)
    catalog_version: str = Field(min_length=1, max_length=96)
    catalog_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    amount: StrictInt | None = Field(default=None, ge=1, le=DAILY_ZARNIKI_CAP)


@router.get("/me")
async def my_shop(db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return await shop_v1.overview(db, user_id=int(user["id"]))
    except shop_v1.ShopClosed as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/buy")
async def buy(body: BuyRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return await shop_v1.buy(
            db, user_id=int(user["id"]), item_id=body.item_id, action_id=body.action_id,
            catalog_version=body.catalog_version, catalog_digest=body.catalog_digest, amount=body.amount,
        )
    except shop_v1.ShopClosed as exc:
        raise HTTPException(404, str(exc)) from exc
    except shop_v1.ShopConflict as exc:
        raise HTTPException(409, str(exc)) from exc
