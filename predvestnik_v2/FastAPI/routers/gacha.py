"""FastAPI/routers/gacha.py — крутки гачи."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from core.constants import (SPIN_COSTS, SPIN_TYPE_LABELS, SPIN_TOKEN_IDS,
                             PITY_HARD, SPIN_MULTI_COUNT, SPIN_MULTI_DISCOUNT)
from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.economy import get_balance, get_item_quantity
from infrastructure.repositories.gacha import get_pity
from core.registry import GACHA_TABLES
from services.gacha import roll_single, roll_multi, maybe_grant_theme_drop

router = APIRouter(prefix="/gacha", tags=["gacha"])


def _compute_rates(spin_type: str) -> dict:
    """Compute pet rarity drop rates (%) from GACHA_TABLES for display."""
    table = GACHA_TABLES.get(spin_type, [])
    total = sum(e.get("weight", 0) for e in table)
    if not total:
        return {}
    rw: dict = {}
    for e in table:
        if e.get("type") in ("pet_dup", "pet_dup_multi"):
            r = e.get("rarity", "common")
            rw[r] = rw.get(r, 0) + e.get("weight", 0)
    order = ["common", "uncommon", "rare", "epic", "legendary", "mythic"]
    return {r: round(rw[r] / total * 100, 1) for r in order if rw.get(r, 0) > 0}


@router.get("/")
async def gacha_info(db=Depends(get_db), user=Depends(require_tg_user)):
    """Типы круток, стоимость, ставки редкости и пити у пользователя."""
    bal = await get_balance(db, user["id"])
    types = []
    for spin_type, cost in SPIN_COSTS.items():
        token_qty = await get_item_quantity(db, user["id"], SPIN_TOKEN_IDS.get(spin_type, ""))
        pity = await get_pity(db, user["id"], spin_type)
        hard = PITY_HARD.get(spin_type, 60)
        disc_cost_mora = round(cost["mora"] * SPIN_MULTI_COUNT * (1 - SPIN_MULTI_DISCOUNT))
        disc_cost_dia  = round(cost["diamonds"] * SPIN_MULTI_COUNT * (1 - SPIN_MULTI_DISCOUNT), 1)
        types.append({
            "spin_type":      spin_type,
            "label":          SPIN_TYPE_LABELS.get(spin_type, spin_type),
            "cost_mora":      cost["mora"],
            "cost_dia":       cost["diamonds"],
            "token_qty":      token_qty,
            "rates":          _compute_rates(spin_type),
            "pity":           pity,
            "pity_hard":      hard,
            "multi_cost_mora": disc_cost_mora,
            "multi_cost_dia":  disc_cost_dia,
        })
    return {
        "mora":      float(bal["user_balance_mora"] or 0),
        "diamonds":  float(bal["user_balance_diamonds"] or 0),
        "spin_types": types,
        "multi_count": SPIN_MULTI_COUNT,
        "multi_discount_pct": int(SPIN_MULTI_DISCOUNT * 100),
    }


async def _notify_chat_spin(db, user_id: int, chat_id: int, spin_type: str, result: dict, multi_count: int = 0) -> None:
    """Best-effort: notify the originating chat about a gacha spin result."""
    try:
        import os, httpx
        token = os.getenv("BOT_TOKEN", "")
        if not token:
            return
        from infrastructure.repositories.users import get_user_name as _gname
        _raw = await _gname(db, user_id)
        username = f"@{_raw}" if _raw else f"Игрок #{user_id}"
        label = SPIN_TYPE_LABELS.get(spin_type, spin_type)
        from core.registry import PET_SPECIES as _PS, ITEMS_REGISTRY as _IR
        _RARITY_ORDER = ["common", "uncommon", "rare", "epic", "legendary", "mythic"]
        dups = result.get("dup_outcomes", [])
        if dups:
            top = max(dups, key=lambda d: _RARITY_ORDER.index(d.get("rarity", "common")) if d.get("rarity") in _RARITY_ORDER else 0)
            sp_name = _PS.get(top['species_id'], {}).get('name', top.get('species_id', '?'))
            drop_str = f"🐾 {sp_name} [{top['rarity']}]"
        elif result.get('mora', 0) > 0:
            drop_str = f"🪙 {result['mora']:.0f} Мора"
        elif result.get('diamonds', 0) > 0:
            drop_str = f"💎 {result['diamonds']} Алмазов"
        elif result.get('items'):
            first = result['items'][0]
            drop_str = f"{_IR.get(first['id'], {}).get('name', first['id'])} ×{first['qty']}"
        else:
            drop_str = "—"
        suffix = f" ×{multi_count}" if multi_count else ""
        label_line = "Лучшее" if multi_count else "Выпало"
        text = f"🎲 <b>{username}</b> крутанул <b>{label}</b>{suffix}\n└ {label_line}: {drop_str}"
        async with httpx.AsyncClient(timeout=3) as c:
            await c.post(f"https://api.telegram.org/bot{token}/sendMessage",
                         json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
    except Exception:
        pass


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

    # Theme drop (rare cosmetic bonus) — same chance as the bot's gacha,
    # otherwise website spins never grant profile themes.
    theme_drop = await maybe_grant_theme_drop(db, user["id"], body.spin_type)
    if theme_drop:
        try:
            await db.commit()
        except Exception:
            pass
        result["theme_drop"] = theme_drop

    # Send bot notification to chat (best-effort)
    if body.chat_id:
        await _notify_chat_spin(db, user["id"], body.chat_id, body.spin_type, result)

    return result


@router.post("/multi-spin")
async def multi_spin(body: SpinRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """10× мультикрутка со скидкой."""
    ok, results = await roll_multi(db, user["id"], body.spin_type, count=SPIN_MULTI_COUNT)
    if not ok:
        raise HTTPException(400, results)
    await db.commit()

    if body.chat_id:
        try:
            from services.quests import increment_metric as _q_incr
            await _q_incr(db, user["id"], body.chat_id, "gacha_spins_today", delta=float(SPIN_MULTI_COUNT))
            await db.commit()
        except Exception:
            pass

    # Aggregate results for frontend
    total_mora = sum(r.get("mora", 0) for r in results)
    total_dia  = sum(r.get("diamonds", 0) for r in results)
    all_dups   = [d for r in results for d in (r.get("dup_outcomes") or [])]
    all_items  = [i for r in results for i in (r.get("items") or [])]
    summary = {
        "mora":     total_mora,
        "diamonds": total_dia,
        "dup_outcomes": all_dups,
        "items":    all_items,
        "count":    len(results),
    }

    # Theme drop — 10x spins roll the chance 10 times (slightly better odds),
    # same as the bot's multi-spin. Otherwise website multi-spins never
    # grant profile themes.
    for _ in range(SPIN_MULTI_COUNT):
        theme_drop = await maybe_grant_theme_drop(db, user["id"], body.spin_type)
        if theme_drop:
            try:
                await db.commit()
            except Exception:
                pass
            summary["theme_drop"] = theme_drop
            break

    if body.chat_id:
        await _notify_chat_spin(db, user["id"], body.chat_id, body.spin_type, summary, multi_count=SPIN_MULTI_COUNT)

    return {"results": results, "summary": summary}
