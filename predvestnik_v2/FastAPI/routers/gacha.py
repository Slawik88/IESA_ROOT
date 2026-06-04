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
                dups = result.get("dup_outcomes", [])
                top = max(dups, key=lambda d: ["common","uncommon","rare","epic","legendary","mythic"].index(d.get("rarity","common")) if d.get("rarity") in ["common","uncommon","rare","epic","legendary","mythic"] else 0, default=None) if dups else None
                drop_str = f"🐾 {top['species']} [{top['rarity']}]" if top else (f"🪙 {result.get('mora',0):.0f}" if result.get('mora') else "предмет")
                text = f"🎲 <b>{username}</b> крутанул <b>{label}</b>\n└ Выпало: {drop_str}"
                async with httpx.AsyncClient(timeout=3) as c:
                    await c.post(f"https://api.telegram.org/bot{token}/sendMessage",
                                 json={"chat_id": body.chat_id, "text": text, "parse_mode": "HTML"})
        except Exception:
            pass

    return result
