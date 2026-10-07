"""Mini App catalog and purchase adapter over the shared economy service."""
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from FastAPI.deps import get_db, require_tg_user, require_module
from infrastructure.repositories.economy import get_balance

router = APIRouter(prefix="/shop", tags=["shop"], dependencies=[Depends(require_module("module_shop"))])

@router.get("/")
async def get_shop(db=Depends(get_db), user=Depends(require_tg_user)):
    """Fail-closed workshop while the new useful-item catalog is versioned."""
    bal = await get_balance(db, user["id"])
    return {
        "active": False,
        "message": "Мастерская обновляется: старые расходники больше не продаются, потому что их механики закрыты. Баланс не списывается.",
        "mora":     float(bal["user_balance_mora"] or 0),
        "diamonds": float(bal["user_balance_diamonds"] or 0),
        "zarniki":  float(bal["user_balance_zarniki"] or 0),
        "items":    [],
    }


class BuyRequest(BaseModel):
    item_id:  str
    quantity: int = Field(default=1, ge=1, le=99)


@router.post("/buy")
async def buy_item(
    body: BuyRequest,
    db=Depends(get_db),
    user=Depends(require_tg_user),
    request_key: str = Header(alias="Idempotency-Key"),
):
    """Keep the retired purchase contract closed without executing legacy writers."""
    raise HTTPException(410, "Старый каталог закрыт. Новая Мастерская не продаёт предметы без действующей роли.")
