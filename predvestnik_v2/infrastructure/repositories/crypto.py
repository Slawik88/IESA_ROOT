# infrastructure/repositories/crypto.py — лорная биржа и серверные сделки.
import math
from datetime import datetime, timezone

from core.constants import (
    CRYPTO_TRADE_FEE, CRYPTO_MIN_TRADE_MORA, CRYPTO_MAX_HOLDING,
    CRYPTO_AMOUNT_DECIMALS, CRYPTO_WEEKLY_PAYOUT_BUDGET,
)
from core.economy_contract import IdempotencyConflict, InsufficientBalance
from infrastructure.repositories.economy_ledger import (
    apply_balance_change,
    find_reference_replay,
)


async def ensure_tables(db) -> None:
    """Идемпотентно создать таблицы биржи (нужно веб-процессу до init_db бота)."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS crypto_holdings (
            user_id       BIGINT NOT NULL,
            coin_id       TEXT   NOT NULL,
            amount        FLOAT8 DEFAULT 0,
            avg_buy_price FLOAT8 DEFAULT 0,
            PRIMARY KEY (user_id, coin_id)
        )
    """)
    # Идемпотентная миграция для старых инсталляций без avg_buy_price
    await db.execute(
        "ALTER TABLE crypto_holdings ADD COLUMN IF NOT EXISTS avg_buy_price FLOAT8 DEFAULT 0"
    )
    await db.execute("""
        CREATE TABLE IF NOT EXISTS crypto_trades (
            id         SERIAL PRIMARY KEY,
            user_id    BIGINT NOT NULL,
            coin_id    TEXT   NOT NULL,
            action     TEXT   NOT NULL,
            amount     FLOAT8 NOT NULL,
            price      FLOAT8 NOT NULL,
            total_mora FLOAT8 NOT NULL,
            traded_at  TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_ct_user_coin ON crypto_trades(user_id, coin_id, traded_at DESC)"
    )
    await db.execute("""
        CREATE TABLE IF NOT EXISTS crypto_watchlist (
            user_id BIGINT NOT NULL,
            coin_id TEXT   NOT NULL,
            PRIMARY KEY (user_id, coin_id)
        )
    """)
    # VIP-алерты цен: разовые (сработал → удалился), direction фиксируется при
    # создании от текущей цены — «упала до X» и «выросла до X» различаются сами.
    await db.execute("""
        CREATE TABLE IF NOT EXISTS crypto_price_alerts (
            id           SERIAL PRIMARY KEY,
            user_id      BIGINT NOT NULL,
            coin_id      TEXT   NOT NULL,
            target_price FLOAT8 NOT NULL,
            direction    TEXT   NOT NULL,
            created_at   TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_cpa_user ON crypto_price_alerts(user_id)"
    )
    await db.execute("""
        CREATE TABLE IF NOT EXISTS crypto_market_budget (
            period_key  TEXT PRIMARY KEY,
            payout_cap  FLOAT8 NOT NULL,
            payout_used FLOAT8 NOT NULL DEFAULT 0,
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.commit()


def _period_key() -> str:
    now = datetime.now(timezone.utc)
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


async def get_market_budget(db) -> dict:
    """Published house-risk ceiling for the current UTC week."""
    key = _period_key()
    await db.execute(
        "INSERT INTO crypto_market_budget (period_key, payout_cap) VALUES (?, ?) "
        "ON CONFLICT (period_key) DO NOTHING",
        (key, CRYPTO_WEEKLY_PAYOUT_BUDGET),
    )
    async with db.execute(
        "SELECT payout_cap, payout_used FROM crypto_market_budget WHERE period_key = ?",
        (key,),
    ) as c:
        row = await c.fetchone()
    cap = float(row[0]) if row else CRYPTO_WEEKLY_PAYOUT_BUDGET
    used = float(row[1]) if row else 0.0
    return {"period": key, "cap": cap, "used": used, "remaining": max(0.0, cap - used)}


# ── VIP-алерты цен ────────────────────────────────────────────────────────────

async def list_alerts(db, user_id: int) -> list[dict]:
    async with db.execute(
        "SELECT id, coin_id, target_price, direction FROM crypto_price_alerts "
        "WHERE user_id = ? ORDER BY id",
        (user_id,),
    ) as c:
        return [{"id": r[0], "coin_id": r[1], "target_price": float(r[2]),
                 "direction": r[3]} for r in await c.fetchall()]


async def count_alerts(db, user_id: int) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM crypto_price_alerts WHERE user_id = ?", (user_id,)
    ) as c:
        row = await c.fetchone()
    return int(row[0] or 0)


async def add_alert(db, user_id: int, coin_id: str, target_price: float, direction: str) -> int:
    async with db.execute(
        "INSERT INTO crypto_price_alerts (user_id, coin_id, target_price, direction) "
        "VALUES (?, ?, ?, ?) RETURNING id",
        (user_id, coin_id, target_price, direction),
    ) as c:
        row = await c.fetchone()
    await db.commit()
    return int(row[0])


async def delete_alert(db, user_id: int, alert_id: int) -> bool:
    async with db.execute(
        "DELETE FROM crypto_price_alerts WHERE id = ? AND user_id = ? RETURNING id",
        (alert_id, user_id),
    ) as c:
        row = await c.fetchone()
    await db.commit()
    return row is not None


async def all_alerts(db) -> list[dict]:
    """Все активные алерты — для фонового чекера (services/scheduler.py)."""
    async with db.execute(
        "SELECT id, user_id, coin_id, target_price, direction FROM crypto_price_alerts"
    ) as c:
        return [{"id": r[0], "user_id": r[1], "coin_id": r[2],
                 "target_price": float(r[3]), "direction": r[4]} for r in await c.fetchall()]


async def delete_alerts_by_ids(db, ids: list[int]) -> None:
    if not ids:
        return
    ph = ",".join("?" * len(ids))
    await db.execute(f"DELETE FROM crypto_price_alerts WHERE id IN ({ph})", tuple(ids))
    await db.commit()


async def get_holdings(db, user_id: int) -> dict[str, dict]:
    """Возвращает {coin_id: {amount, avg_buy}} для позиций > 0."""
    try:
        async with db.execute(
            "SELECT coin_id, amount, COALESCE(avg_buy_price, 0) FROM crypto_holdings "
            "WHERE user_id = ? AND amount > 0",
            (user_id,),
        ) as c:
            return {r[0]: {"amount": float(r[1]), "avg_buy": float(r[2])} for r in await c.fetchall()}
    except Exception:
        # avg_buy_price ещё не мигрирован — fallback без P&L
        async with db.execute(
            "SELECT coin_id, amount FROM crypto_holdings WHERE user_id = ? AND amount > 0",
            (user_id,),
        ) as c:
            return {r[0]: {"amount": float(r[1]), "avg_buy": 0.0} for r in await c.fetchall()}


async def get_trade_history(db, user_id: int, coin_id: str | None = None, limit: int = 50) -> list[dict]:
    try:
        if coin_id:
            q = ("SELECT coin_id, action, amount, price, total_mora, traded_at "
                 "FROM crypto_trades WHERE user_id = ? AND coin_id = ? "
                 "ORDER BY traded_at DESC LIMIT ?")
            args: tuple = (user_id, coin_id, limit)
        else:
            q = ("SELECT coin_id, action, amount, price, total_mora, traded_at "
                 "FROM crypto_trades WHERE user_id = ? ORDER BY traded_at DESC LIMIT ?")
            args = (user_id, limit)
        async with db.execute(q, args) as c:
            rows = await c.fetchall()
        return [
            {"coin_id": r[0], "action": r[1], "amount": float(r[2]),
             "price": float(r[3]), "total_mora": float(r[4]), "traded_at": str(r[5])[:16]}
            for r in rows
        ]
    except Exception:
        return []


async def get_watchlist(db, user_id: int) -> set[str]:
    try:
        async with db.execute(
            "SELECT coin_id FROM crypto_watchlist WHERE user_id = ?", (user_id,)
        ) as c:
            return {r[0] for r in await c.fetchall()}
    except Exception:
        return set()


async def toggle_watchlist(db, user_id: int, coin_id: str) -> bool:
    """Добавляет/убирает монету из избранного. Возвращает True если добавлена."""
    try:
        async with db.execute(
            "SELECT 1 FROM crypto_watchlist WHERE user_id = ? AND coin_id = ?", (user_id, coin_id)
        ) as c:
            exists = await c.fetchone()
        if exists:
            await db.execute(
                "DELETE FROM crypto_watchlist WHERE user_id = ? AND coin_id = ?", (user_id, coin_id)
            )
            await db.commit()
            return False
        await db.execute(
            "INSERT INTO crypto_watchlist (user_id, coin_id) VALUES (?, ?)", (user_id, coin_id)
        )
        await db.commit()
        return True
    except Exception:
        return False


async def trade(db, user_id: int, coin_id: str, action: str,
                amount: float, unit_price: float,
                *, idempotency_key: str | None = None) -> tuple[bool, str]:
    """Атомарная серверная сделка с ledger, повтором и лимитом риска системы."""
    if not math.isfinite(amount) or amount <= 0:
        return False, "Некорректное количество."
    if not math.isfinite(unit_price) or unit_price <= 0:
        return False, "Некорректная цена."
    amount = round(float(amount), CRYPTO_AMOUNT_DECIMALS)
    if amount <= 0:
        return False, "Слишком маленькое количество."
    gross = amount * unit_price
    if gross < CRYPTO_MIN_TRADE_MORA:
        return False, f"Минимальная сделка — {CRYPTO_MIN_TRADE_MORA:.0f} 🪙."
    if action not in ("buy", "sell"):
        return False, "Допустимо только купить или продать."
    if not idempotency_key:
        return False, "Не удалось подтвердить уникальность запроса. Обновите страницу и повторите."
    amt_txt = f"{amount:g}"
    reason = "crypto_buy" if action == "buy" else "crypto_sell"
    reference_id = f"{coin_id}:{action}:{amount:.{CRYPTO_AMOUNT_DECIMALS}f}"
    operation_key = f"crypto:trade:{idempotency_key}"
    try:
        async with db.connection.transaction():
            async with db.execute("SELECT pg_advisory_xact_lock(?)", (int(user_id),)) as c:
                await c.fetchone()
            replay = await find_reference_replay(
                db, user_id,
                reason_code=reason,
                idempotency_key=operation_key,
                source_type="exchange",
                reference_type="crypto_trade",
                reference_id=reference_id,
            )
            if replay:
                return True, "Эта сделка уже была выполнена; повторно баланс не изменён."
            async with db.execute(
                "SELECT user_balance_mora FROM users WHERE user_tg_id = ? FOR UPDATE",
                (user_id,),
            ) as c:
                row = await c.fetchone()
            bal = float(row[0]) if row else 0.0
            async with db.execute(
                "SELECT amount, COALESCE(avg_buy_price, 0) FROM crypto_holdings "
                "WHERE user_id = ? AND coin_id = ? FOR UPDATE",
                (user_id, coin_id),
            ) as c:
                hr = await c.fetchone()
            have = float(hr[0]) if hr else 0.0
            old_avg = float(hr[1]) if hr else 0.0

            if action == "buy":
                cost = round(gross * (1 + CRYPTO_TRADE_FEE), 2)
                if bal < cost:
                    return False, "Недостаточно Моры для покупки."
                if have + amount > CRYPTO_MAX_HOLDING:
                    return False, "Достигнут лимит по этой монете."
                new_avg = (have * old_avg + amount * unit_price) / (have + amount)
                await apply_balance_change(
                    db, user_id, {"mora": -cost}, reason_code="crypto_buy",
                    idempotency_key=operation_key, source_type="exchange",
                    reference_type="crypto_trade", reference_id=reference_id,
                    metadata={"coin_id": coin_id, "action": action, "amount": amount,
                              "price": unit_price, "fee": CRYPTO_TRADE_FEE, "total": cost},
                    note=f"{coin_id} ×{amt_txt}",
                )
                await db.execute(
                    "INSERT INTO crypto_holdings (user_id, coin_id, amount, avg_buy_price) "
                    "VALUES (?, ?, ?, ?) ON CONFLICT (user_id, coin_id) DO UPDATE "
                    "SET amount = crypto_holdings.amount + ?, avg_buy_price = ?",
                    (user_id, coin_id, amount, new_avg, amount, new_avg),
                )
                await db.execute(
                    "INSERT INTO crypto_trades (user_id, coin_id, action, amount, price, total_mora) "
                    "VALUES (?, ?, 'buy', ?, ?, ?)",
                    (user_id, coin_id, amount, unit_price, cost),
                )
                return True, f"Куплено {amt_txt} {coin_id} за {cost:.0f} 🪙 (комиссия {int(CRYPTO_TRADE_FEE * 100)}%)."

            if action == "sell":
                if have + 1e-9 < amount:
                    return False, "Недостаточно монет для продажи."
                sell_amt = min(amount, have)
                payout = round(sell_amt * unit_price * (1 - CRYPTO_TRADE_FEE), 2)
                new_have = max(0.0, have - sell_amt)
                period = _period_key()
                await db.execute(
                    "INSERT INTO crypto_market_budget (period_key, payout_cap) VALUES (?, ?) "
                    "ON CONFLICT (period_key) DO NOTHING",
                    (period, CRYPTO_WEEKLY_PAYOUT_BUDGET),
                )
                async with db.execute(
                    "SELECT payout_cap, payout_used FROM crypto_market_budget "
                    "WHERE period_key = ? FOR UPDATE", (period,),
                ) as c:
                    budget_row = await c.fetchone()
                cap, used = float(budget_row[0]), float(budget_row[1])
                if used + payout > cap + 1e-9:
                    return False, "Резерв выплат этой недели исчерпан. Продажа снова откроется в новом периоде."
                await apply_balance_change(
                    db, user_id, {"mora": payout}, reason_code="crypto_sell",
                    idempotency_key=operation_key, source_type="exchange",
                    reference_type="crypto_trade", reference_id=reference_id,
                    metadata={"coin_id": coin_id, "action": action, "amount": sell_amt,
                              "price": unit_price, "fee": CRYPTO_TRADE_FEE,
                              "total": payout, "risk_period": period},
                    note=f"{coin_id} ×{sell_amt:g}",
                )
                await db.execute(
                    "UPDATE crypto_holdings SET amount = ? WHERE user_id = ? AND coin_id = ?",
                    (new_have, user_id, coin_id),
                )
                await db.execute(
                    "UPDATE crypto_market_budget SET payout_used = payout_used + ?, updated_at = NOW() "
                    "WHERE period_key = ?", (payout, period),
                )
                await db.execute(
                    "INSERT INTO crypto_trades (user_id, coin_id, action, amount, price, total_mora) "
                    "VALUES (?, ?, 'sell', ?, ?, ?)",
                    (user_id, coin_id, sell_amt, unit_price, payout),
                )
                return True, f"Продано {sell_amt:g} {coin_id} за {payout:.0f} 🪙 (комиссия {int(CRYPTO_TRADE_FEE * 100)}%)."

            return False, "Неизвестное действие."
    except InsufficientBalance as e:
        return False, str(e)
    except IdempotencyConflict:
        return False, "Этот ключ запроса уже использован для другой сделки."
    except Exception:
        return False, "Сделка не выполнена. Баланс и портфель не изменены."
