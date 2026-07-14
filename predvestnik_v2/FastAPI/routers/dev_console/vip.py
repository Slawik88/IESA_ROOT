"""dev_console/vip.py — VIP: выдать/продлить/заменить/отозвать/скорректировать дни."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from FastAPI.deps import get_db, require_tg_user
from core.registry import VIP_TIERS
from services.vip import grant_vip_days
from ._common import require_console_perm, _tg_call

router = APIRouter()


# ── 5. Выдать VIP (бесплатно, без списания зарников) ─────────────────────────────
class GiveVipRequest(BaseModel):
    user_id: int
    tier: str
    days: int


@router.post("/give-vip")
async def dev_give_vip(body: GiveVipRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "economy_vip")
    if body.tier not in VIP_TIERS:
        raise HTTPException(400, "Неизвестный тариф.")
    if not 1 <= body.days <= 3650:
        raise HTTPException(400, "days: 1..3650.")
    await grant_vip_days(db, body.user_id, body.tier, body.days)
    await db.commit()
    label = VIP_TIERS[body.tier]["label"]
    await _tg_call("sendMessage", chat_id=body.user_id, parse_mode="HTML",
                   text=f"🎁 Вам выдан <b>{label}</b> на {body.days} дн.! Загляни: «бот вип».")
    return {"ok": True, "label": label}


@router.post("/revoke-vip")
async def dev_revoke_vip(body: dict, db=Depends(get_db), user=Depends(require_tg_user)):
    """Отозвать VIP у пользователя (expires_at = NOW(), он сразу теряет статус)."""
    await require_console_perm(db, user, "economy_vip")
    uid = int(body.get("user_id", 0))
    if not uid:
        raise HTTPException(400, "user_id обязателен.")
    async with db.execute(
        "UPDATE vip_subscriptions SET expires_at = NOW(), expiry_notified = TRUE "
        "WHERE user_id = ? AND expires_at > NOW() RETURNING tier",
        (uid,),
    ) as c:
        row = await c.fetchone()
    if not row:
        raise HTTPException(400, "Активного VIP не найдено.")
    await db.commit()
    await _tg_call("sendMessage", chat_id=uid, parse_mode="HTML",
                   text="⚠️ Ваш VIP-статус был отозван администратором.")
    return {"ok": True, "revoked_tier": row[0]}


class SetVipRequest(BaseModel):
    user_id: int
    tier: str
    days: int


@router.post("/set-vip")
async def dev_set_vip(body: SetVipRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Принудительно заменить текущий VIP на новый тариф и срок.
    Предыдущий VIP (бонусы, срок) сгорают; начисляется gift нового тарифа."""
    await require_console_perm(db, user, "economy_vip")
    if body.tier not in VIP_TIERS:
        raise HTTPException(400, "Неизвестный тариф.")
    if not 1 <= body.days <= 3650:
        raise HTTPException(400, "days: 1..3650.")

    await db.execute(
        "INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (body.user_id,))
    # Полностью заменяем — сбрасываем started_at и expires_at
    await db.execute(
        "INSERT INTO vip_subscriptions (user_id, tier, started_at, expires_at, expiry_notified, total_days) "
        "VALUES (?, ?, NOW(), NOW() + make_interval(days => ?), FALSE, ?) "
        "ON CONFLICT (user_id) DO UPDATE SET "
        "tier = EXCLUDED.tier, "
        "started_at = NOW(), "
        "expires_at = NOW() + make_interval(days => ?), "
        "expiry_notified = FALSE, "
        "total_days = COALESCE(vip_subscriptions.total_days, 0) + ?",
        (body.user_id, body.tier, body.days, body.days, body.days, body.days),
    )
    # Начисляем gift нового тарифа
    info = VIP_TIERS[body.tier]
    gift = info["gift"]
    if gift.get("mora"):
        await db.execute(
            "UPDATE users SET user_balance_mora = user_balance_mora + ? WHERE user_tg_id = ?",
            (gift["mora"], body.user_id),
        )
    if gift.get("diamonds"):
        await db.execute(
            "UPDATE users SET user_balance_diamonds = user_balance_diamonds + ? WHERE user_tg_id = ?",
            (gift["diamonds"], body.user_id),
        )
    for item_id, qty in gift.get("items", ()):
        await db.execute(
            "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = inventory.quantity + ?",
            (body.user_id, item_id, qty, qty),
        )
    await db.commit()
    label = info["label"]
    await _tg_call("sendMessage", chat_id=body.user_id, parse_mode="HTML",
                   text=f"🔄 Ваш VIP переключён на <b>{label}</b> на {body.days} дн. + бонус пакета!")
    return {"ok": True, "label": label}


class AdjustVipRequest(BaseModel):
    user_id: int
    days: int


@router.post("/adjust-vip-days")
async def dev_adjust_vip_days(body: AdjustVipRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """± дней к ТЕКУЩЕМУ VIP, не меняя тариф. days<0 — убавить срок (не уходит в прошлое
    дальше NOW); days>0 — продлить (и +стаж). Требуется активный VIP."""
    await require_console_perm(db, user, "economy_vip")
    if not body.days or not (-3650 <= body.days <= 3650):
        raise HTTPException(400, "days: ненулевое значение в пределах ±3650.")
    async with db.execute(
        "SELECT (expires_at > NOW()) AS active FROM vip_subscriptions WHERE user_id = ?",
        (body.user_id,),
    ) as c:
        row = await c.fetchone()
    if not row or not row["active"]:
        raise HTTPException(400, "Нет активного VIP. Используйте «Выдать / продлить».")
    async with db.execute(
        "UPDATE vip_subscriptions SET "
        "expires_at = GREATEST(NOW(), expires_at + make_interval(days => ?)), "
        "expiry_notified = FALSE, "
        "total_days = CASE WHEN ? > 0 THEN COALESCE(total_days,0) + ? ELSE total_days END "
        "WHERE user_id = ? "
        "RETURNING GREATEST(0, CEIL(EXTRACT(EPOCH FROM (expires_at - NOW())) / 86400.0))::int AS days_left",
        (body.days, body.days, body.days, body.user_id),
    ) as c:
        res = await c.fetchone()
    await db.commit()
    if body.days > 0:
        msg = f"👑 Ваш VIP продлён на {body.days} дн. администратором."
    else:
        msg = f"⏳ Срок вашего VIP сокращён на {abs(body.days)} дн. администратором."
    await _tg_call("sendMessage", chat_id=body.user_id, parse_mode="HTML", text=msg)
    return {"ok": True, "days": body.days, "days_left": res["days_left"] if res else None}
