"""dev_console/promocodes.py — admin_audit B6: управление промокодами с сайта.

Раньше промокоды администрировались ТОЛЬКО текстовыми FSM-командами в чате
(«dev промокод создать/список/инфо») — единственная админ-механика без веб-аналога.
Чатовые команды остаются; этот роутер даёт тот же CRUD + статистику активаций.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.registry import ITEMS_REGISTRY
from infrastructure.repositories import promocodes as promo_repo
from FastAPI.deps import get_db, require_tg_user
from ._common import require_console_perm

router = APIRouter()


@router.get("/promocodes")
async def dev_promocodes_list(db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "promo_manage")
    rows = await promo_repo.list_promocodes(db)
    return {"promocodes": rows}


@router.get("/promocodes/{code}")
async def dev_promocode_info(code: str, db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "promo_manage")
    promo = await promo_repo.get_promocode(db, code.upper())
    if not promo:
        raise HTTPException(404, "Промокод не найден.")
    activators = await promo_repo.get_promo_activators(db, code.upper(), limit=30)
    return {"promocode": promo, "activators": activators}


class PromoCreateRequest(BaseModel):
    code: str
    description: str = ""
    mora: float = 0
    diamonds: float = 0
    dark_mora: float = 0
    zarniki: float = 0
    items: dict[str, int] = {}          # {item_id: qty}
    max_activations: int = 0            # 0 = безлимит
    valid_from: str | None = None       # 'YYYY-MM-DD HH:MM' или None
    valid_until: str | None = None


@router.post("/promocodes")
async def dev_promocode_create(body: PromoCreateRequest, db=Depends(get_db),
                               user=Depends(require_tg_user)):
    await require_console_perm(db, user, "promo_manage")
    code = body.code.strip().upper()
    if not (3 <= len(code) <= 32) or not code.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(400, "Код: 3–32 символа, буквы/цифры/-/_.")
    if await promo_repo.get_promocode(db, code):
        raise HTTPException(400, f"Промокод {code} уже существует.")
    # Валидация предметов против реестра — как в services.promocodes
    bad = [i for i in body.items if i not in ITEMS_REGISTRY]
    if bad:
        raise HTTPException(400, f"Неизвестные предметы: {', '.join(bad)}")
    ok = await promo_repo.create_promocode(
        db, code, body.description.strip(),
        body.mora, body.diamonds, body.dark_mora, body.zarniki,
        json.dumps({k: int(v) for k, v in body.items.items() if int(v) > 0}),
        max(0, body.max_activations), body.valid_from, body.valid_until,
        created_by=user["id"],
    )
    if not ok:
        raise HTTPException(400, "Не удалось создать промокод.")
    return {"ok": True, "code": code}


@router.post("/promocodes/{code}/toggle")
async def dev_promocode_toggle(code: str, db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "promo_manage")
    promo = await promo_repo.get_promocode(db, code.upper())
    if not promo:
        raise HTTPException(404, "Промокод не найден.")
    if promo.get("is_active"):
        await promo_repo.deactivate_promocode(db, code.upper())
        return {"ok": True, "is_active": False}
    await promo_repo.activate_promocode_record(db, code.upper())
    return {"ok": True, "is_active": True}


@router.delete("/promocodes/{code}")
async def dev_promocode_delete(code: str, db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "promo_manage")
    ok = await promo_repo.delete_promocode(db, code.upper())
    if not ok:
        raise HTTPException(404, "Промокод не найден.")
    return {"ok": True}
