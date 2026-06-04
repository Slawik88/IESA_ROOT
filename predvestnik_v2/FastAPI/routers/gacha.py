"""FastAPI/routers/gacha.py — крутки гачи."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from core.constants import SPIN_COSTS, SPIN_TYPE_LABELS, SPIN_TOKEN_IDS
from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.economy import get_balance, get_item_quantity
from services.gacha import roll_single

router = APIRouter(prefix="/gacha", tags=["gacha"])


@router.get("/")
async def gacha_info(db=Depends(get_db), user=Depends(require_tg_user)):
    """Типы круток, стоимость и наличие жетонов у пользователя."""
    bal = await get_balance(db, user["id"])
    types = []
    for spin_type, cost in SPIN_COSTS.items():
        token_qty = await get_item_quantity(db, user["id"], SPIN_TOKEN_IDS.get(spin_type, ""))
        types.append({
            "spin_type":  spin_type,
            "label":      SPIN_TYPE_LABELS.get(spin_type, spin_type),
            "cost_mora":  cost["mora"],
            "cost_dia":   cost["diamonds"],
            "token_qty":  token_qty,
        })
    return {"mora": float(bal["user_balance_mora"] or 0), "spin_types": types}


class SpinRequest(BaseModel):
    spin_type: str
    chat_id: int = 0   # optional: send bot notification to this chat


@router.post("/spin")
async def spin(body: SpinRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Один спин выбранного типа крутки."""
    ok, result = await roll_single(db, user["id"], body.spin_type)
    if not ok:
        raise HTTPException(400, result)
    await db.commit()

    # Track quest metric: gacha_spins_today
    if body.chat_id:
        try:
            from services.quests import increment_metric as _q_incr
            await _q_incr(db, user["id"], body.chat_id, "gacha_spins_today", delta=1.0)
            await db.commit()
        except Exception:
            pass

    # Send bot notification to chat (best-effort)
    if body.chat_id:
        try:
            import os, httpx
            token = os.getenv("BOT_TOKEN", "")
            if token:
                from infrastructure.repositories.users import get_user_name as _gname
                _raw = await _gname(db, user["id"])
                username = f"@{_raw}" if _raw else f"Игрок #{user['id']}"
                label = SPIN_TYPE_LABELS.get(body.spin_type, body.spin_type)
                from core.registry import PET_SPECIES as _PS, ITEMS_REGISTRY as _IR
                _RARITY_ORDER = ["common","uncommon","rare","epic","legendary","mythic"]
                dups = result.get("dup_outcomes", [])
                # Build human-readable drop string
                if dups:
                    top = max(dups, key=lambda d: _RARITY_ORDER.index(d.get("rarity","common")) if d.get("rarity") in _RARITY_ORDER else 0)
                    sp_name = _PS.get(top['species'], {}).get('name', top['species'])
                    drop_str = f"🐾 {sp_name} [{top['rarity']}]"
                elif result.get('mora', 0) > 0:
                    drop_str = f"🪙 {result['mora']:.0f} Мора"
                elif result.get('diamonds', 0) > 0:
                    drop_str = f"💎 {result['diamonds']} Алмазов"
                elif result.get('items'):
                    first = result['items'][0]
                    drop_str = f"{_IR.get(first['id'],{}).get('name', first['id'])} ×{first['qty']}"
                else:
                    drop_str = "—"
                text = f"🎲 <b>{username}</b> крутанул <b>{label}</b>\n└ Выпало: {drop_str}"
                async with httpx.AsyncClient(timeout=3) as c:
                    await c.post(f"https://api.telegram.org/bot{token}/sendMessage",
                                 json={"chat_id": body.chat_id, "text": text, "parse_mode": "HTML"})
        except Exception:
            pass

    return result
