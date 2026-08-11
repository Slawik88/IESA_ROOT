"""FastAPI/routers/exchange.py — постоянный обменник Моры ↔ Алмазов.

БЛОК 2.2: ивентовый обмен (B15) заменён на постоянный двусторонний обменник,
доступный из профиля по клику на 🪙/💎.

Квота — дневная, без миграций: ключ в user_exchange_quota.event_id =
  • дата YYYYMMDD  — для покупки (Мора → Алмазы);
  • -YYYYMMDD      — для продажи (Алмазы → Мора), отдельный неймспейс.
Новый день = новый ключ ⇒ авто-сброс лимита в полночь. Старые event-строки
(с настоящими event_id из exchange_events) сосуществуют безвредно.
"""
import math
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from core.economy_contract import IdempotencyConflict, InvalidEconomicMutation
from core.constants import (
    EXCHANGE_RATE_MORA_PER_DIAMOND, EXCHANGE_RATE_MORA_PER_DIAMOND_SELL,
    EXCHANGE_DAILY_CAP_DIAMONDS, EXCHANGE_SELL_DAILY_CAP_DIAMONDS,
    EXCHANGE_MIN_DIAMONDS_PER_REQUEST, CRYPTO_TRADE_FEE, CRYPTO_MIN_TRADE_MORA,
)
from FastAPI.deps import get_db, require_tg_user, require_module
from infrastructure.repositories import economy as eco_repo
from infrastructure.repositories.economy_ledger import find_balance_replay
from infrastructure.repositories.exchange import get_user_quota, add_quota
from infrastructure.repositories import crypto as crypto_repo
from services import crypto_exchange as cx

router = APIRouter(prefix="/exchange", tags=["exchange"], dependencies=[Depends(require_module("module_exchange"))])


def _buy_key() -> int:
    """Ключ дневной квоты покупки: YYYYMMDD."""
    return int(date.today().strftime("%Y%m%d"))


def _sell_key() -> int:
    """Ключ дневной квоты продажи: -YYYYMMDD (отдельный неймспейс от покупки)."""
    return -_buy_key()


def _idempotency_key(raw_key: str | None, action: str) -> str | None:
    if raw_key is None:
        return None
    clean = raw_key.strip()
    if not clean or len(clean) > 120:
        raise HTTPException(400, "Idempotency-Key должен содержать 1–120 символов.")
    return f"web:exchange:{action}:{clean}"


@router.get("/")
async def exchange_status(db=Depends(get_db), user=Depends(require_tg_user)):
    """Статус постоянного обменника + остаток дневных квот в обе стороны."""
    bought = await get_user_quota(db, user["id"], _buy_key())
    sold = await get_user_quota(db, user["id"], _sell_key())
    bal = await eco_repo.get_balance(db, user["id"])
    return {
        "active":         True,  # обменник теперь доступен всегда
        "rate":           EXCHANGE_RATE_MORA_PER_DIAMOND,
        "sell_rate":      EXCHANGE_RATE_MORA_PER_DIAMOND_SELL,
        "min_diamonds":   EXCHANGE_MIN_DIAMONDS_PER_REQUEST,
        "daily_cap":      EXCHANGE_DAILY_CAP_DIAMONDS,
        "sell_daily_cap": EXCHANGE_SELL_DAILY_CAP_DIAMONDS,
        "used_today":     bought,
        "sold_today":     sold,
        "remaining":      max(0.0, EXCHANGE_DAILY_CAP_DIAMONDS - bought),
        "sell_remaining": max(0.0, EXCHANGE_SELL_DAILY_CAP_DIAMONDS - sold),
        "mora":           float(bal["user_balance_mora"] or 0),
        "diamonds":       float(bal["user_balance_diamonds"] or 0),
    }


class ConvertRequest(BaseModel):
    diamonds: float


@router.post("/convert")
async def convert(
    body: ConvertRequest,
    db=Depends(get_db),
    user=Depends(require_tg_user),
    request_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Купить Алмазы за Мору (3000🪙 → 1💎). Постоянно, дневной лимит."""
    diamonds = round(body.diamonds, 2)
    if diamonds < EXCHANGE_MIN_DIAMONDS_PER_REQUEST:
        raise HTTPException(400, f"Минимум {int(EXCHANGE_MIN_DIAMONDS_PER_REQUEST)} 💎.")

    key = _buy_key()
    scoped_key = _idempotency_key(request_key, "mora-to-diamonds")
    mora_needed = diamonds * EXCHANGE_RATE_MORA_PER_DIAMOND
    # atomic: лочим строку игрока — параллельные обмены не уведут баланс в минус
    try:
        async with eco_repo.atomic(db, user["id"]):
            if scoped_key:
                replay = await find_balance_replay(
                    db, user["id"], {"mora": -mora_needed, "diamonds": diamonds},
                    reason_code="exchange_mora_to_dia", idempotency_key=scoped_key,
                    source_type="exchange", reference_type="currency_pair",
                    reference_id="mora_diamonds",
                )
                if replay:
                    return {
                        "ok": True, "replayed": True, "operation_id": replay.operation_id,
                        "mora_spent": mora_needed, "diamonds_gained": diamonds,
                    }

            used = await get_user_quota(db, user["id"], key)
            remaining = EXCHANGE_DAILY_CAP_DIAMONDS - used
            if diamonds > remaining:
                raise HTTPException(400, f"Дневной лимит покупки: {remaining:.1f} 💎 осталось.")

            bal = await eco_repo.get_balance(db, user["id"])
            if bal["user_balance_mora"] < mora_needed:
                raise HTTPException(400, f"Нужно {mora_needed:,.0f} 🪙, есть {bal['user_balance_mora']:,.0f}.")

            mutation = await eco_repo.add_balance(
                db, user["id"], mora=-mora_needed, diamonds=diamonds,
                source="exchange_mora_to_dia", source_type="exchange",
                idempotency_key=scoped_key, reference_type="currency_pair",
                reference_id="mora_diamonds",
            )
            if mutation and mutation.applied:
                await add_quota(db, user["id"], key, diamonds)
    except (IdempotencyConflict, InvalidEconomicMutation) as exc:
        raise HTTPException(409, str(exc)) from exc

    return {
        "ok": True, "replayed": False,
        "operation_id": mutation.operation_id if mutation else None,
        "mora_spent": mora_needed, "diamonds_gained": diamonds,
    }


@router.post("/sell")
async def sell(
    body: ConvertRequest,
    db=Depends(get_db),
    user=Depends(require_tg_user),
    request_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Продать Алмазы за Мору (1💎 → 2000🪙, спред). Постоянно, дневной лимит."""
    diamonds = round(body.diamonds, 2)
    if diamonds < EXCHANGE_MIN_DIAMONDS_PER_REQUEST:
        raise HTTPException(400, f"Минимум {int(EXCHANGE_MIN_DIAMONDS_PER_REQUEST)} 💎.")

    key = _sell_key()
    scoped_key = _idempotency_key(request_key, "diamonds-to-mora")
    mora_gained = diamonds * EXCHANGE_RATE_MORA_PER_DIAMOND_SELL
    try:
        async with eco_repo.atomic(db, user["id"]):
            if scoped_key:
                replay = await find_balance_replay(
                    db, user["id"], {"mora": mora_gained, "diamonds": -diamonds},
                    reason_code="exchange_dia_to_mora", idempotency_key=scoped_key,
                    source_type="exchange", reference_type="currency_pair",
                    reference_id="diamonds_mora",
                )
                if replay:
                    return {
                        "ok": True, "replayed": True, "operation_id": replay.operation_id,
                        "mora_gained": mora_gained, "diamonds_spent": diamonds,
                    }

            used = await get_user_quota(db, user["id"], key)
            remaining = EXCHANGE_SELL_DAILY_CAP_DIAMONDS - used
            if diamonds > remaining:
                raise HTTPException(400, f"Дневной лимит продажи: {remaining:.1f} 💎 осталось.")

            bal = await eco_repo.get_balance(db, user["id"])
            if bal["user_balance_diamonds"] < diamonds:
                raise HTTPException(400, f"Нужно {diamonds:.0f} 💎, есть {bal['user_balance_diamonds']:.1f}.")

            mutation = await eco_repo.add_balance(
                db, user["id"], mora=mora_gained, diamonds=-diamonds,
                source="exchange_dia_to_mora", source_type="exchange",
                idempotency_key=scoped_key, reference_type="currency_pair",
                reference_id="diamonds_mora",
            )
            if mutation and mutation.applied:
                await add_quota(db, user["id"], key, diamonds)
    except (IdempotencyConflict, InvalidEconomicMutation) as exc:
        raise HTTPException(409, str(exc)) from exc

    return {
        "ok": True, "replayed": False,
        "operation_id": mutation.operation_id if mutation else None,
        "mora_gained": mora_gained, "diamonds_spent": diamonds,
    }


# ── Крипто-Биржа (ШАГ4) ─────────────────────────────────────────────────────────

@router.get("/crypto")
async def crypto_market(db=Depends(get_db), user=Depends(require_tg_user)):
    """Рынок: монеты (цена/изменение/свечи) + портфель с P&L + баланс Моры + вотчлист."""
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
            "price": p, "change_24h": cx.change_pct(c),
            "candles": cx.candles(c), "holding": amt, "value": value,
            "avg_buy": avg_buy, "pnl_abs": pnl_abs, "pnl_pct": pnl_pct,
            "starred": c["id"] in watchlist,
        })
    total_pnl = round(portfolio_value - portfolio_cost, 2) if portfolio_cost else 0.0
    return {
        "coins": coins,
        "mora": float(bal["user_balance_mora"] or 0),
        "portfolio_value": round(portfolio_value, 2),
        "portfolio_pnl": total_pnl,
        "fee": CRYPTO_TRADE_FEE,
        "min_trade": CRYPTO_MIN_TRADE_MORA,
    }


class CryptoTradeRequest(BaseModel):
    coin_id: str
    action: str          # "buy" | "sell"
    amount: float


@router.post("/crypto/trade")
async def crypto_trade(body: CryptoTradeRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Купить/продать монету. Цена считается СЕРВЕРОМ в момент сделки (no client trust)."""
    coin = cx.get_coin(body.coin_id)
    if not coin:
        raise HTTPException(404, "Монета не найдена.")
    if body.action not in ("buy", "sell"):
        raise HTTPException(400, "action: buy | sell.")
    if not math.isfinite(body.amount) or body.amount <= 0:
        raise HTTPException(400, "Некорректное количество.")
    price = cx.price_now(coin)
    ok, msg = await crypto_repo.trade(db, user["id"], coin["id"], body.action, body.amount, price)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg, "price": price}


@router.get("/crypto/history")
async def crypto_history(coin_id: str | None = None, db=Depends(get_db), user=Depends(require_tg_user)):
    """История сделок текущего игрока (по монете или все)."""
    return await crypto_repo.get_trade_history(db, user["id"], coin_id=coin_id, limit=30)


@router.get("/crypto/top")
async def crypto_top(db=Depends(get_db), user=Depends(require_tg_user)):
    """Топ-10 трейдеров по текущей стоимости портфеля."""
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
    """Добавить/убрать монету из избранного (тоггл)."""
    if not cx.get_coin(coin_id):
        raise HTTPException(404, "Монета не найдена.")
    added = await crypto_repo.toggle_watchlist(db, user["id"], coin_id)
    return {"ok": True, "starred": added}


# ── VIP-алерты цен ────────────────────────────────────────────────────────────

CRYPTO_ALERTS_MAX = 5  # активных алертов на игрока


class AlertRequest(BaseModel):
    coin_id: str
    target_price: float


@router.get("/crypto/alerts")
async def crypto_alerts_list(db=Depends(get_db), user=Depends(require_tg_user)):
    """Активные ценовые алерты игрока + VIP-статус (создание — только VIP)."""
    from services.vip import is_vip_active
    return {
        "alerts": await crypto_repo.list_alerts(db, user["id"]),
        "is_vip": await is_vip_active(db, user["id"]),
        "max": CRYPTO_ALERTS_MAX,
    }


@router.post("/crypto/alerts")
async def crypto_alert_add(body: AlertRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Создать разовый алерт: бот пришлёт ЛС, когда цена достигнет отметки.
    Направление определяется автоматически от текущей цены (выше/ниже)."""
    from services.vip import is_vip_active
    if not await is_vip_active(db, user["id"]):
        raise HTTPException(403, "Ценовые алерты — привилегия 👑 VIP.")
    coin = cx.get_coin(body.coin_id)
    if not coin:
        raise HTTPException(404, "Монета не найдена.")
    if not math.isfinite(body.target_price) or body.target_price <= 0:
        raise HTTPException(400, "Некорректная цена.")
    if await crypto_repo.count_alerts(db, user["id"]) >= CRYPTO_ALERTS_MAX:
        raise HTTPException(400, f"Лимит: {CRYPTO_ALERTS_MAX} активных алертов. Удалите старый.")
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
