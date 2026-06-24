"""FastAPI/routers/combat.py — БЛОК19 Ч.6/7: Теневые Врата + Рейды (боевые питомцы)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories import pet_combat as combat_repo
from infrastructure.repositories import shadow_gates as gates_repo

router = APIRouter(prefix="/combat", tags=["combat"])


class PetReq(BaseModel):
    pet_id: int


# ── Теневые Врата (Ч.7) ─────────────────────────────────────────────────────────

@router.get("/gates")
async def gates_overview(db=Depends(get_db), user=Depends(require_tg_user)):
    """Активные забеги + питомцы, которых можно отправить во Врата."""
    uid = user["id"]
    runs = await gates_repo.status(db, uid)
    async with db.execute(
        "SELECT id FROM pets WHERE owner_id = ? AND COALESCE(placement,'') != 'gates' "
        "AND id NOT IN (SELECT pet_id FROM active_expeditions)",
        (uid,),
    ) as c:
        pet_ids = [r[0] for r in await c.fetchall()]
    pets = []
    for pid in pet_ids:
        st = await combat_repo.get_state(db, pid, owner_id=uid)
        if st:
            pets.append({"pet_id": st["pet_id"], "name": st["name"], "species_id": st["species_id"],
                         "rarity": st["rarity"], "level": st["level"], "hp": st["hp"],
                         "hp_max": st["hp_max"], "stamina": st["stamina"], "stamina_max": st["stamina_max"]})
    return {"runs": runs, "pets": pets}


@router.post("/gates/enter")
async def gates_enter(body: PetReq, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await gates_repo.enter(db, user["id"], body.pet_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


@router.post("/gates/collect")
async def gates_collect(body: PetReq, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await gates_repo.collect(db, user["id"], body.pet_id)
    return {"ok": ok, "message": msg}


@router.post("/gates/heal")
async def gates_heal(body: PetReq, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await gates_repo.heal(db, user["id"], body.pet_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}
