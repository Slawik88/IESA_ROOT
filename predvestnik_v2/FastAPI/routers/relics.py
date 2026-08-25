"""FastAPI/routers/relics.py — архивные реликвии за сохранённый остаток.
Веб-адаптер; вся бизнес-логика в infrastructure.repositories.relics (паритет с
ботом `бот реликвии`)."""
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from core.registry import RELICS, RELIC_RARITY_META
from infrastructure.repositories import relics as relics_db

router = APIRouter(prefix="/relics", tags=["relics"])


@router.get("/")
async def list_relics(db=Depends(get_db), user=Depends(require_tg_user)):
    """Каталог архивных реликвий и владение без игровой силы."""
    owned = await relics_db.list_owned(db, user["id"])
    bonus = await relics_db.get_expedition_mora_bonus(db, user["id"])
    catalog = []
    for rid, r in RELICS.items():
        meta = RELIC_RARITY_META.get(r["rarity"], {})
        catalog.append({
            "id": rid, "name": r["name"], "rarity": r["rarity"],
            "rarity_name": meta.get("name", r["rarity"]), "badge": meta.get("badge", ""),
            "exp_mora_pct": r["exp_mora_pct"], "price": r["price"],
            "desc": r["desc"], "owned": rid in owned,
        })
    return {
        "relics": catalog,
        "owned_count": len(owned),
        "total": len(RELICS),
        "power": 0,
        "bonus_pct": round(bonus * 100),
        "archive_only": True,
    }


class BuyRequest(BaseModel):
    relic_id: str


@router.post("/buy")
async def buy(
    body: BuyRequest,
    db=Depends(get_db),
    user=Depends(require_tg_user),
    request_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Атомарно исполнить уже доступную архивную покупку."""
    if body.relic_id not in RELICS:
        raise HTTPException(400, "Неизвестная реликвия.")
    if request_key is None or not request_key.strip() or len(request_key.strip()) > 120:
        raise HTTPException(400, "Idempotency-Key должен содержать 1–120 символов.")
    ok, msg = await relics_db.buy_relic(
        db, user["id"], body.relic_id, idempotency_key=request_key.strip(),
    )
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}
