"""FastAPI/routers/combat.py — БЛОК19 Ч.6: клановые Рейды.
Боёвка 3.0: атака отрядом юнитов из Казармы (мирные питомцы в боях не участвуют)."""
from fastapi import APIRouter, Depends, HTTPException

from FastAPI.deps import get_db, require_tg_user
from core.units import UNITS, unit_stats
from infrastructure.repositories import raids as raids_repo
from services.barracks import squad_units

router = APIRouter(prefix="/combat", tags=["combat"])


# R2: старые Теневые Врата заменены Вратами 2.0 (/combat2/*); shadow_gates.py
# остаётся только ради одноразовой миграции при деплое (см. bot/__main__.py).


@router.get("/raid")
async def raid_overview(db=Depends(get_db), user=Depends(require_tg_user)):
    uid = user["id"]
    info = await raids_repo.get_active(db, uid)
    if info is None:
        return {"in_clan": False}
    squad = await squad_units(db, uid)
    dmg = round(sum(unit_stats(s["unit_id"], s["level"])["atk"] for s in squad) * 1.5, 1)
    return {"in_clan": True, **info,
            "squad": [{"unit_id": s["unit_id"], "level": s["level"],
                       "name": UNITS[s["unit_id"]]["name"],
                       "emoji": UNITS[s["unit_id"]]["emoji"]} for s in squad],
            "squad_damage": dmg}


@router.post("/raid/start")
async def raid_start(db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await raids_repo.start(db, user["id"])
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


@router.post("/raid/attack")
async def raid_attack(db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await raids_repo.attack(db, user["id"])
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}
