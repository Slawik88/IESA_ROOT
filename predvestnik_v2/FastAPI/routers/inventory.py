"""FastAPI/routers/inventory.py — инвентарь: просмотр + взаимодействие с предметами."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.registry import ITEMS_REGISTRY
from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.economy import get_inventory, remove_item
from infrastructure.repositories.zoo import grant_duplicate
from services.inventory_resolve import resolve_and_migrate_item_id, item_display_name

router = APIRouter(prefix="/inventory", tags=["inventory"])

_CATEGORY_ORDER = {"food": 0, "spin_token": 1, "booster": 2, "material": 3}


@router.get("/")
async def my_inventory(db=Depends(get_db), user=Depends(require_tg_user)):
    rows = await get_inventory(db, user["id"])
    result = []
    for row in rows:
        real_id = await resolve_and_migrate_item_id(db, user["id"], row["item_id"])

        item = ITEMS_REGISTRY.get(real_id, {})
        result.append({
            "item_id":        real_id,
            "name":           item_display_name(real_id),
            "quantity":       row["quantity"],
            "category":       item.get("category", "unknown"),
            "description":    item.get("description", ""),
            "spin_type":      item.get("spin_type"),
            "boost_hours":    item.get("boost_hours"),
            "fatigue_restore": item.get("fatigue_restore"),
        })
    result.sort(key=lambda x: (_CATEGORY_ORDER.get(x["category"], 9), x["item_id"]))
    return result


# /open-egg УДАЛЁН (БЛОК19 Ч.2): открытие яиц вырезано, питомцы — только через /gacha.


class UseRequest(BaseModel):
    item_id: str


@router.post("/use")
async def use_item(body: UseRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Применить активируемый расходник (паритет с ботом `бот использовать`).
    Вручную активируется только study_notes (+50% XP 4ч). Зелья удачи/рывка —
    `gacha_luck`/`expedition_loot` — применяются автоматически на следующем
    действии (гача/экспедиция), активировать их вручную не нужно."""
    from datetime import datetime, timedelta
    item_id = body.item_id.strip().lower()
    if item_id != "study_notes":
        raise HTTPException(400, "Этот предмет нельзя активировать вручную.")
    async with db.execute(
        "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ? AND quantity > 0",
        (user["id"], item_id),
    ) as c:
        if not await c.fetchone():
            raise HTTPException(400, "Нет предмета в инвентаре.")
    # Зеркалит bot/handlers/inventory.py: study_xp на 4ч, ON CONFLICT обновляет срок.
    expires = (datetime.utcnow() + timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S")
    await db.execute(
        "INSERT INTO player_buffs (user_id, buff_type, uses_left, expires_at, value) "
        "VALUES (?, ?, 1, ?, 0.5) "
        "ON CONFLICT(user_id, buff_type) DO UPDATE SET expires_at = EXCLUDED.expires_at",
        (user["id"], "study_xp", expires),
    )
    await db.execute(
        "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = 'study_notes'",
        (user["id"],),
    )
    await db.commit()
    return {"ok": True, "message": "📚 Конспект применён! +50% XP от сообщений на 4 часа."}


# buff_type → как показать в «активно сейчас» (mode: time = до HH:MM, uses = N круток)
_BUFF_META = {
    "study_xp":         {"icon": "📚", "label": "Конспект: +XP от сообщений", "mode": "time"},
    "gacha_luck":       {"icon": "🧪", "label": "Удача гачи: +шанс редких",   "mode": "uses"},
    "expedition_loot":  {"icon": "⚡", "label": "Рывок: +лут экспедиции",      "mode": "uses"},
    "unicorn_immunity": {"icon": "🦄", "label": "Иммунитет питомца",           "mode": "time"},
}


@router.get("/buffs")
async def active_buffs(db=Depends(get_db), user=Depends(require_tg_user)):
    """Активные баффы игрока (player_buffs) — что действует прямо сейчас.
    Зелья применяются автоматически, поэтому игрок иначе их не видит."""
    async with db.execute(
        "SELECT buff_type, uses_left, value, expires_at FROM player_buffs "
        "WHERE user_id = ? AND (expires_at IS NULL OR expires_at > NOW()) "
        "AND (uses_left IS NULL OR uses_left > 0)",
        (user["id"],),
    ) as c:
        rows = [dict(r) for r in await c.fetchall()]
    out = []
    for r in rows:
        meta = _BUFF_META.get(r["buff_type"],
                              {"icon": "✨", "label": r["buff_type"], "mode": "uses"})
        out.append({
            "type": r["buff_type"], "icon": meta["icon"], "label": meta["label"],
            "mode": meta["mode"], "value": float(r["value"] or 0),
            "uses_left": r["uses_left"],
            "expires_at": str(r["expires_at"]) if r["expires_at"] else None,
        })
    return {"buffs": out}


class ApplyDustRequest(BaseModel):
    dust_id: str
    pet_id: int


@router.post("/apply-dust")
async def apply_dust(body: ApplyDustRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Применить Звёздную пыль к питомцу (добавить дубликаты)."""
    dust_amounts = {"star_dust_s": 1, "star_dust_l": 5}
    amount = dust_amounts.get(body.dust_id)
    if not amount:
        raise HTTPException(400, "Не является звёздной пылью.")

    async with db.execute(
        "SELECT species_id, rarity, COALESCE(pet_level, 1) AS pet_level "
        "FROM pets WHERE id = ? AND owner_id = ?",
        (body.pet_id, user["id"]),
    ) as c:
        pet = await c.fetchone()
    if not pet:
        raise HTTPException(404, "Питомец не найден.")
    if (pet["pet_level"] or 1) >= 10:
        raise HTTPException(400, "Питомец уже на максимальном уровне!")

    ok = await remove_item(db, user["id"], body.dust_id, 1, commit=False)
    if not ok:
        raise HTTPException(400, "Нет пыли в инвентаре.")

    outcomes = [await grant_duplicate(db, user["id"], pet["species_id"]) for _ in range(amount)]

    # Grant one-time milestone rewards (mora/diamonds/items) for any level
    # thresholds (3/5/7/10) crossed — same as bot's cb_use_stardust.
    from services.zoo import apply_pet_milestones
    milestones = []
    for r in outcomes:
        if r.get("pet_id") and r.get("milestones_unlocked"):
            milestones.extend(await apply_pet_milestones(db, user["id"], r["pet_id"], r["milestones_unlocked"]))

    await db.commit()
    return {"ok": True, "duplicates_added": amount, "outcomes": outcomes, "milestones": milestones}
