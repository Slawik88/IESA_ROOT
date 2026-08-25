"""Owner-v3 currency information and the integrated lore market."""
import math

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from core.constants import (
    CRYPTO_TRADE_FEE, CRYPTO_MIN_TRADE_MORA,
)
from FastAPI.deps import get_db, require_tg_user, require_module
from infrastructure.repositories import economy as eco_repo
from infrastructure.repositories import crypto as crypto_repo
from services import crypto_exchange as cx

router = APIRouter(prefix="/exchange", tags=["exchange"], dependencies=[Depends(require_module("module_exchange"))])


@router.get("/")
async def exchange_status(db=Depends(get_db), user=Depends(require_tg_user)):
    """Explain the distinct roles of Mora and earned Diamonds."""
    bal = await eco_repo.get_balance(db, user["id"])
    return {
        "active": False,
        "policy_version": "owner-v3-provisional-1",
        "mora": float(bal["user_balance_mora"] or 0),
        "diamonds": float(bal["user_balance_diamonds"] or 0),
        "title": "У валют разные задачи",
        "mora_rule": "Мора оплачивает подготовку, торговлю и проекты.",
        "diamonds_rule": "Алмазы выдаются за испытания и сезонные рубежи.",
        "blocked_rule": "Покупка и продажа Алмазов за Мору отключены.",
    }


class ConvertRequest(BaseModel):
    diamonds: float


@router.post("/convert")
async def convert(
    body: ConvertRequest,
    db=Depends(get_db),
    user=Depends(require_tg_user),
):
    """Retained as a fail-closed compatibility route for old clients."""
    raise HTTPException(
        410,
        "Алмазы больше нельзя купить за Мору — они выдаются за испытания и сезонные рубежи.",
    )


@router.post("/sell")
async def sell(
    body: ConvertRequest,
    db=Depends(get_db),
    user=Depends(require_tg_user),
):
    """Retained as a fail-closed compatibility route for old clients."""
    raise HTTPException(
        410,
        "Алмазы больше нельзя продать за Мору — они нужны для редких решений.",
    )


# ── Крипто-Биржа (ШАГ4) ─────────────────────────────────────────────────────────

@router.get("/crypto")
async def crypto_market(db=Depends(get_db), user=Depends(require_tg_user)):
    """Server-priced lore assets, portfolio, P&L and public risk limits."""
    holds = await crypto_repo.get_holdings(db, user["id"])
    watchlist = await crypto_repo.get_watchlist(db, user["id"])
    bal = await eco_repo.get_balance(db, user["id"])
    coins = []
    portfolio_value = 0.0
    portfolio_cost = 0.0
    for c in cx.COINS:
        p = cx.price_now(c)
        hold = holds.get(c["id"], {"amount": 0.0, "avg_buy": 0.0})
        amt = hold["amount"]
        avg_buy = hold["avg_buy"]
        value = round(amt * p, 2)
        portfolio_value += value
        portfolio_cost += amt * avg_buy
        pnl_abs = round(amt * (p - avg_buy), 2) if avg_buy and amt else 0.0
        pnl_pct = round((p - avg_buy) / avg_buy * 100, 2) if avg_buy and amt else 0.0
        coins.append({
            "id": c["id"], "name": c["name"], "emoji": c["emoji"],
            "region": c["region"], "world_use": c["use"],
            "price": p, "change_24h": cx.change_pct(c),
            "candles": cx.candles(c), "holding": amt, "value": value,
            "avg_buy": avg_buy, "pnl_abs": pnl_abs, "pnl_pct": pnl_pct,
            "starred": c["id"] in watchlist,
        })
    total_pnl = round(portfolio_value - portfolio_cost, 2) if portfolio_cost else 0.0
    budget = await crypto_repo.get_market_budget(db)
    return {
        "coins": coins,
        "mora": float(bal["user_balance_mora"] or 0),
        "portfolio_value": round(portfolio_value, 2),
        "portfolio_pnl": total_pnl,
        "fee": CRYPTO_TRADE_FEE,
        "min_trade": CRYPTO_MIN_TRADE_MORA,
        "risk_budget": budget,
        "market_rule": "Продажи оплачиваются из публичного недельного резерва; цена и исполнение определяет сервер.",
        "world_phase": cx.world_phase(),
    }


class CryptoTradeRequest(BaseModel):
    coin_id: str
    action: str          # "buy" | "sell"
    amount: float


@router.post("/crypto/trade")
async def crypto_trade(
    body: CryptoTradeRequest,
    db=Depends(get_db),
    user=Depends(require_tg_user),
    request_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Купить/продать актив; цену и итог определяет только сервер."""
    coin = cx.get_coin(body.coin_id)
    if not coin:
        raise HTTPException(404, "Актив не найден.")
    if body.action not in ("buy", "sell"):
        raise HTTPException(400, "Допустимо только купить или продать.")
    if not math.isfinite(body.amount) or body.amount <= 0:
        raise HTTPException(400, "Некорректное количество.")
    if request_key is None or not request_key.strip() or len(request_key.strip()) > 120:
        raise HTTPException(400, "Idempotency-Key должен содержать 1–120 символов.")
    price = cx.price_now(coin)
    ok, msg = await crypto_repo.trade(
        db, user["id"], coin["id"], body.action, body.amount, price,
        idempotency_key=request_key.strip(),
    )
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


@router.get("/crypto/history")
async def crypto_history(coin_id: str | None = None, db=Depends(get_db), user=Depends(require_tg_user)):
    """История сделок текущего игрока (по монете или все)."""
    return await crypto_repo.get_trade_history(db, user["id"], coin_id=coin_id, limit=30)


@router.get("/crypto/top")
async def crypto_top(db=Depends(get_db), user=Depends(require_tg_user)):
    """Топ-10 портфелей по текущей серверной оценке."""
    async with db.execute(
        "SELECT h.user_id, u.user_tg_username, h.coin_id, h.amount "
        "FROM crypto_holdings h JOIN users u ON u.user_tg_id = h.user_id "
        "WHERE h.amount > 0"
    ) as c:
        rows = await c.fetchall()
    totals: dict[int, dict] = {}
    for row in rows:
        uid, uname, coin_id, amount = int(row[0]), row[1], row[2], float(row[3])
        coin = cx.get_coin(coin_id)
        if not coin:
            continue
        val = amount * cx.price_now(coin)
        if uid not in totals:
            totals[uid] = {"username": uname or f"id{uid}", "value": 0.0}
        totals[uid]["value"] += val
    top = sorted(totals.items(), key=lambda x: x[1]["value"], reverse=True)[:10]
    return [
        {"rank": i + 1, "user_id": uid, "username": d["username"], "value": round(d["value"], 2)}
        for i, (uid, d) in enumerate(top)
    ]


@router.post("/crypto/watchlist/{coin_id}")
async def watchlist_toggle(coin_id: str, db=Depends(get_db), user=Depends(require_tg_user)):
    if not cx.get_coin(coin_id):
        raise HTTPException(404, "Актив не найден.")
    added = await crypto_repo.toggle_watchlist(db, user["id"], coin_id)
    return {"ok": True, "starred": added}


# ── VIP-алерты цен ────────────────────────────────────────────────────────────

CRYPTO_ALERTS_MAX = 5  # активных алертов на игрока


class AlertRequest(BaseModel):
    coin_id: str
    target_price: float


@router.get("/crypto/alerts")
async def crypto_alerts_list(db=Depends(get_db), user=Depends(require_tg_user)):
    from services.vip import is_vip_active
    return {
        "alerts": await crypto_repo.list_alerts(db, user["id"]),
        "is_vip": await is_vip_active(db, user["id"]),
        "max": CRYPTO_ALERTS_MAX,
    }


@router.post("/crypto/alerts")
async def crypto_alert_add(body: AlertRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    from services.vip import is_vip_active
    if not await is_vip_active(db, user["id"]):
        raise HTTPException(403, "Ценовые алерты — сервис 👑 VIP.")
    coin = cx.get_coin(body.coin_id)
    if not coin:
        raise HTTPException(404, "Актив не найден.")
    if not math.isfinite(body.target_price) or body.target_price <= 0:
        raise HTTPException(400, "Некорректная цена.")
    if await crypto_repo.count_alerts(db, user["id"]) >= CRYPTO_ALERTS_MAX:
        raise HTTPException(400, f"Лимит: {CRYPTO_ALERTS_MAX} активных алертов.")
    now_price = cx.price_now(coin)
    target = round(body.target_price, 2)
    if abs(target - now_price) < 0.01:
        raise HTTPException(400, "Цена уже на этой отметке.")
    direction = "above" if target > now_price else "below"
    alert_id = await crypto_repo.add_alert(db, user["id"], coin["id"], target, direction)
    return {"ok": True, "id": alert_id, "direction": direction, "price_now": now_price}


@router.delete("/crypto/alerts/{alert_id}")
async def crypto_alert_delete(alert_id: int, db=Depends(get_db), user=Depends(require_tg_user)):
    if not await crypto_repo.delete_alert(db, user["id"], alert_id):
        raise HTTPException(404, "Алерт не найден.")
    return {"ok": True}
