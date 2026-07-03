"""FastAPI/routers/showcase.py — Витрина недели (R4.2, GDD_REBUILD_PLAN.md).

5 тёмных карточек косметики со скидкой 10–30%, ротация раз в ISO-неделю.
Скрытность до reveal и скидочная цена считаются ТОЛЬКО на сервере."""
import math
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from core.cosmetics import COSMETICS
from infrastructure.repositories import showcase as sc_repo
from services.cosmetics import buy as cosmetics_buy

router = APIRouter(prefix="/showcase", tags=["showcase"])


def _zarniki_price(cos: dict) -> int:
    """Базовая ✨-цена предмета (все shop-предметы имеют зарниковый вариант)."""
    for opt in cos.get("price") or []:
        if "zarniki" in opt:
            return int(opt["zarniki"])
    return 0


def _discounted(base: int, pct: int) -> int:
    return max(1, int(math.floor(base * (100 - pct) / 100)))


def _seconds_to_next_week() -> int:
    now = datetime.now(timezone.utc)
    days_ahead = 7 - now.isoweekday() % 7  # до следующего понедельника 00:00 UTC
    next_monday = (now + timedelta(days=days_ahead or 7)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    if next_monday <= now:
        next_monday += timedelta(days=7)
    return int((next_monday - now).total_seconds())


@router.get("/")
async def get_showcase(db=Depends(get_db), user=Depends(require_tg_user)):
    wk = sc_repo.week_key()
    slots = await sc_repo.get_week_slots(db, wk)
    state = await sc_repo.get_user_state(db, user["id"], wk)
    out = []
    for i, s in enumerate(slots):
        cos = COSMETICS.get(s["cosmetic_id"])
        if not cos:
            continue  # предмет убран из реестра после генерации недели
        st = state.get(i, {})
        revealed = st.get("revealed", False)
        base = _zarniki_price(cos)
        item = {
            "slot_idx": i,
            "slot": cos["slot"],
            "rarity": cos["rarity"],
            "revealed": revealed,
            "purchased": st.get("purchased", False),
        }
        if revealed:
            item.update({
                "cosmetic_id": s["cosmetic_id"],
                "name": cos["name"],
                "discount_pct": s["discount_pct"],
                "price_base": base,
                "price": _discounted(base, s["discount_pct"]),
            })
        out.append(item)
    return {"week": wk, "slots": out, "rotates_in_sec": _seconds_to_next_week()}


class SlotRequest(BaseModel):
    slot_idx: int


@router.post("/reveal")
async def reveal_slot(body: SlotRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    wk = sc_repo.week_key()
    slots = await sc_repo.get_week_slots(db, wk)
    if not (0 <= body.slot_idx < len(slots)):
        raise HTTPException(400, "Нет такого слота витрины.")
    await sc_repo.reveal(db, user["id"], wk, body.slot_idx)
    s = slots[body.slot_idx]
    cos = COSMETICS.get(s["cosmetic_id"])
    if not cos:
        raise HTTPException(404, "Предмет недели больше не существует.")
    base = _zarniki_price(cos)
    return {
        "cosmetic_id": s["cosmetic_id"],
        "name": cos["name"],
        "slot": cos["slot"],
        "rarity": cos["rarity"],
        "discount_pct": s["discount_pct"],
        "price_base": base,
        "price": _discounted(base, s["discount_pct"]),
    }


@router.post("/buy")
async def buy_slot(body: SlotRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    wk = sc_repo.week_key()
    slots = await sc_repo.get_week_slots(db, wk)
    if not (0 <= body.slot_idx < len(slots)):
        raise HTTPException(400, "Нет такого слота витрины.")
    state = await sc_repo.get_user_state(db, user["id"], wk)
    st = state.get(body.slot_idx, {})
    if not st.get("revealed"):
        raise HTTPException(400, "Сначала открой карточку — покупка вслепую недоступна.")
    if st.get("purchased"):
        raise HTTPException(400, "Этот слот витрины ты уже выкупил на этой неделе.")

    s = slots[body.slot_idx]
    cos = COSMETICS.get(s["cosmetic_id"])
    if not cos:
        raise HTTPException(404, "Предмет недели больше не существует.")
    price = _discounted(_zarniki_price(cos), s["discount_pct"])
    ok, msg = await cosmetics_buy(
        db, user["id"], s["cosmetic_id"], price_override={"zarniki": price},
    )
    if not ok:
        raise HTTPException(400, msg)
    await sc_repo.mark_purchased(db, user["id"], wk, body.slot_idx)
    return {"ok": True, "message": msg, "price": price}