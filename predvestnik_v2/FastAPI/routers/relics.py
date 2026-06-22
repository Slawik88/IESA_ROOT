"""FastAPI/routers/relics.py — Реликвии (Block 13): коллекция за Тёмную Мору.
Веб-адаптер; вся бизнес-логика в infrastructure.repositories.relics (паритет с
ботом `бот реликвии`)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from core.registry import RELICS, RELIC_RARITY_META
from infrastructure.repositories import relics as relics_db

router = APIRouter(prefix="/relics", tags=["relics"])


@router.get("/")
async def list_relics(db=Depends(get_db), user=Depends(require_tg_user)):
    """Каталог реликвий + владение + агрегаты (сила коллекции, бонус походам)."""
    owned = await relics_db.list_owned(db, user["id"])
    power = sum(RELIC_RARITY_META.get(RELICS[r]["rarity"], {}).get("power", 0)
                for r in owned if r in RELICS)
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
        "power": power,
        "bonus_pct": round(bonus * 100),
    }


class BuyRequest(BaseModel):
    relic_id: str


@router.post("/buy")
async def buy(body: BuyRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Купить реликвию (атомарно, мультивалютно — buy_relic коммитит сам)."""
    if body.relic_id not in RELICS:
        raise HTTPException(400, "Неизвестная реликвия.")
    ok, msg = await relics_db.buy_relic(db, user["id"], body.relic_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}
