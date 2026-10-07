"""Read-only compatibility surface for the retired random-reward system."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_module, require_tg_user
from core.constants import SPIN_COSTS, SPIN_TOKEN_IDS
from infrastructure.repositories.economy import get_balance, get_item_quantity
from infrastructure.repositories.gacha import get_pity

router = APIRouter(
    prefix="/gacha",
    tags=["gacha"],
    dependencies=[Depends(require_module("module_gacha"))],
)


@router.get("/odds")
async def gacha_odds():
    """Return an explicit closure receipt instead of obsolete odds."""
    return {
        "retired": True,
        "tables": {},
        "message": "Случайные награды закрыты. Сохранённые права будут разобраны в Архиве без скрытых шансов.",
    }


@router.get("/")
async def gacha_info(db=Depends(get_db), user=Depends(require_tg_user)):
    """Show saved tokens and pity while Archive conversion is pending."""
    balance = await get_balance(db, user["id"])
    saved_tokens = 0
    saved_pity = []
    for spin_type in SPIN_COSTS:
        token_id = SPIN_TOKEN_IDS.get(spin_type, "")
        token_qty = await get_item_quantity(db, user["id"], token_id)
        pity = await get_pity(db, user["id"], spin_type)
        saved_tokens += int(token_qty or 0)
        if pity:
            saved_pity.append({"type": spin_type, "count": int(pity)})
    return {
        "retired": True,
        "archive_pending": True,
        "message": "Крутки больше не продают силу и валюту. Жетоны и накопленный гарант сохранены для прозрачного разбора в Архиве.",
        "mora": float(balance["user_balance_mora"] or 0),
        "diamonds": float(balance["user_balance_diamonds"] or 0),
        "spin_types": [],
        "saved_tokens": saved_tokens,
        "saved_pity": saved_pity,
    }


class SpinRequest(BaseModel):
    spin_type: str
    chat_id: int = 0


@router.post("/spin")
async def spin(body: SpinRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Reject retired single spins without invoking legacy writers."""
    raise HTTPException(410, "Случайные крутки закрыты. Жетоны и гарант сохранены для Архива.")


@router.post("/multi-spin")
async def multi_spin(body: SpinRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Reject retired multi-spins without invoking legacy writers."""
    raise HTTPException(410, "Случайные крутки закрыты. Жетоны и гарант сохранены для Архива.")
