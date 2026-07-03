"""FastAPI/routers/combat.py — БЛОК19 Ч.6/7: Теневые Врата + Рейды (боевые питомцы)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories import pet_combat as combat_repo
from infrastructure.repositories import raids as raids_repo

router = APIRouter(prefix="/combat", tags=["combat"])


class PetReq(BaseModel):
    pet_id: int


async def _combat_pets(db, uid: int) -> list[dict]:
    """Боевые питомцы игрока, свободные (не во Вратах/экспедиции)."""
    async with db.execute(
        "SELECT id FROM pets WHERE owner_id = ? AND COALESCE(placement,'') != 'gates' "
        "AND id NOT IN (SELECT pet_id FROM active_expeditions)",
        (uid,),
    ) as c:
        pet_ids = [r[0] for r in await c.fetchall()]
    out = []
    for pid in pet_ids:
        st = await combat_repo.get_state(db, pid, owner_id=uid)
        if st:
            out.append({"pet_id": st["pet_id"], "name": st["name"], "species_id": st["species_id"],
                        "rarity": st["rarity"], "level": st["level"], "hp": st["hp"],
                        "hp_max": st["hp_max"], "attack": st["attack"], "defense": st["defense"]})
    return out


# ── Теневые Врата (Ч.7) ─────────────────────────────────────────────────────────

# R2: старые Теневые Врата (пассивный дрейн HP) заменены Вратами 2.0 —
# PvE-лестница с Боем 2.0, роутер FastAPI/routers/battle.py (/combat2/*).
# Эндпоинты /gates* удалены; shadow_gates.py остаётся только ради
# одноразовой миграции активных забегов при деплое (см. bot/__main__.py).


# ── Клановые Рейды (Ч.6, замена PvP) ────────────────────────────────────────────

@router.get("/raid")
async def raid_overview(db=Depends(get_db), user=Depends(require_tg_user)):
    uid = user["id"]
    info = await raids_repo.get_active(db, uid)
    if info is None:
        return {"in_clan": False}
    return {"in_clan": True, **info, "pets": await _combat_pets(db, uid)}


@router.post("/raid/start")
async def raid_start(db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await raids_repo.start(db, user["id"])
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


@router.post("/raid/attack")
async def raid_attack(body: PetReq, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await raids_repo.attack(db, user["id"], body.pet_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}
