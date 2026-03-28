"""
api/spy.py — unified espionage operations.

All functions are async; the mini app wraps them with async_to_sync.
"""
import random
from datetime import datetime, timezone, timedelta


SPY_COST = 50
SPY_COOLDOWN_SEC = 3600   # 1 hour per spy→target pair
SPY_FAIL_CHANCE = 0.30    # 30 %


async def spy(uid: int, chat_id: int, target_id: int) -> dict:
    """Perform espionage on target_id's balance.

    Costs SPY_COST mora. 30% fail chance. 1h cooldown per target.
    Raises ValueError on validation/cooldown errors.
    Returns {ok, success, cost, new_balance, message?, target?}.
    """
    from database.db import deduct_mora, get_mora, get_user
    from database.postgres import connect as postgres_connect

    if target_id == uid:
        raise ValueError("Нельзя шпионить за собой")

    now_utc = datetime.now(timezone.utc)

    # Check cooldown
    since = now_utc - timedelta(seconds=SPY_COOLDOWN_SEC)
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT attempted_at FROM espionage_log "
            "WHERE spy_id=? AND target_id=? AND chat_id=? AND attempted_at > ? "
            "ORDER BY id DESC LIMIT 1",
            (uid, target_id, chat_id, since),
        ) as c:
            cd_row = await c.fetchone()

    if cd_row:
        last = cd_row[0]
        if isinstance(last, str):
            last = datetime.fromisoformat(last.replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        remaining = max(0, int(SPY_COOLDOWN_SEC - (now_utc - last).total_seconds()))
        if remaining > 0:
            mins = remaining // 60
            secs = remaining % 60
            raise ValueError(f"Кулдаун: {mins} мин. {secs} сек.")

    # Check balance
    mora_row = await get_mora(uid, chat_id)
    balance = mora_row["balance"] if mora_row else 0
    if balance < SPY_COST:
        raise ValueError(f"Недостаточно Моры. Нужно {SPY_COST} 🪙")

    # Deduct cost
    async with postgres_connect() as db:
        cursor = await db.execute(
            "UPDATE user_mora SET balance=balance-? WHERE user_id=? AND chat_id=? AND balance>=?",
            (SPY_COST, uid, chat_id, SPY_COST),
        )
        if cursor.rowcount == 0:
            raise ValueError("Не удалось списать Мору")
        await db.commit()

    # Roll success/fail
    failed = random.random() < SPY_FAIL_CHANCE
    success_int = 0 if failed else 1

    # Log attempt
    async with postgres_connect() as db:
        await db.execute(
            "INSERT INTO espionage_log (spy_id, target_id, chat_id, success, attempted_at) "
            "VALUES (?,?,?,?,?)",
            (uid, target_id, chat_id, success_int, now_utc),
        )
        await db.commit()

    new_mora = await get_mora(uid, chat_id)
    new_balance = new_mora["balance"] if new_mora else 0

    if failed:
        return {
            "ok": True,
            "success": False,
            "cost": SPY_COST,
            "new_balance": new_balance,
            "message": "💥 Провал! Агент обнаружен.",
        }

    # Success — get target info
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT balance, vip FROM user_mora WHERE user_id=? AND chat_id=?",
            (target_id, chat_id),
        ) as c:
            t_row = await c.fetchone()

    t_balance = t_row[0] if t_row else 0
    t_vip = bool(t_row[1]) if t_row else False

    t_user = await get_user(target_id)
    t_name = t_user["full_name"] if t_user else f"Игрок {target_id}"
    t_username = t_user.get("username") if t_user else None

    return {
        "ok": True,
        "success": True,
        "cost": SPY_COST,
        "new_balance": new_balance,
        "target": {
            "id": target_id,
            "name": t_name,
            "username": t_username,
            "balance": t_balance,
            "vip": t_vip,
        },
    }
