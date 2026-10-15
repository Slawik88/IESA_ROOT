"""Authenticated adapter for gifts by tier and the gift shelf (ECO-04 PR-C), dark behind the gifts_v2 flag."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from FastAPI.deps import get_db, require_tg_user
from services import gifts_v2


router = APIRouter(prefix="/gifts-v2", tags=["gifts-v2"])


class SendRequest(BaseModel):
    gift_id: str = Field(min_length=1, max_length=64)
    action_id: str = Field(min_length=1, max_length=96)
    catalog_version: str = Field(min_length=1, max_length=96)
    catalog_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    note: str | None = Field(default=None, max_length=200)   # the service strips and enforces 60
    to: str | None = Field(default=None, max_length=64)       # public profile ref; omitted = the partner


class PinRequest(BaseModel):
    send_id: str = Field(min_length=32, max_length=32, pattern=r"^[0-9a-f]{32}$")
    pinned: bool


@router.get("/me")
async def my_gifts(db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return await gifts_v2.overview(db, user_id=int(user["id"]))
    except gifts_v2.GiftsClosed as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/send")
async def send(body: SendRequest, background: BackgroundTasks, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        receipt = await gifts_v2.send(
            db, sender_id=int(user["id"]), gift_id=body.gift_id, action_id=body.action_id,
            catalog_version=body.catalog_version, catalog_digest=body.catalog_digest, note=body.note, to_ref=body.to,
        )
    except gifts_v2.GiftsClosed as exc:
        raise HTTPException(404, str(exc)) from exc
    except gifts_v2.GiftConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    # Committed above. The recipient is told after the response: the sender never waits on Telegram,
    # and a failed notification (logged inside) never turns a delivered gift into an error.
    if receipt.get("applied"):
        background.add_task(gifts_v2.notify_recipient_detached, sender_id=int(user["id"]), receipt=receipt)
    public = {key: value for key, value in receipt.items() if key != "receiver_id"}
    return {"ok": True, "receipt": public, "balances": await gifts_v2.balances(db, int(user["id"]))}


@router.get("/history")
async def history(
    box: str = Query("received", pattern="^(received|sent)$"), tier: int | None = Query(None, ge=1, le=4),
    gift_id: str | None = Query(None, max_length=64), limit: int = Query(50, ge=1, le=100),
    db=Depends(get_db), user=Depends(require_tg_user),
):
    try:
        return await gifts_v2.history(db, user_id=int(user["id"]), box=box, tier=tier, gift_id=gift_id, limit=limit)
    except gifts_v2.GiftsClosed as exc:
        raise HTTPException(404, str(exc)) from exc
    except gifts_v2.GiftConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/pin")
async def pin(body: PinRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return await gifts_v2.set_pin(db, user_id=int(user["id"]), send_id=body.send_id, pinned=body.pinned)
    except gifts_v2.GiftsClosed as exc:
        raise HTTPException(404, str(exc)) from exc
    except gifts_v2.GiftConflict as exc:
        raise HTTPException(409, str(exc)) from exc
