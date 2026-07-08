"""
services/duel.py
Pure duel business logic. No bot imports.
Боёвка 3.0: сила дуэлянта = CP отряда юнитов (Казарма) × случайность —
мирные питомцы в дуэлях больше не участвуют, усталость не начисляется.
"""
import random

from core.constants import (
    DUEL_COMMISSION,
    DUEL_COOLDOWN_HOURS, DUEL_MIN_BET, DUEL_MAX_BET,
)
from infrastructure.repositories import economy as eco_repo
from infrastructure.repositories.duel import (
    create_duel, set_duel_status, set_cooldown, get_cooldown, get_duel,
)
from services.formatting import parse_dt


async def squad_power(db, user_id: int) -> float:
    """Сила отряда: CP юнитов × rand(0.85–1.15); без отряда — базовые 50."""
    from services.barracks import squad_cp
    cp = await squad_cp(db, user_id)
    return max(50.0, float(cp)) * random.uniform(0.85, 1.15)


async def create_challenge(
    db,
    challenger_id: int,
    challenged_id: int,
    chat_id: int,
    stake: float,
) -> tuple[bool, dict | str]:
    """Reserve challenger's stake and create a pending duel.
    Returns (True, {duel_id, ...}) or (False, error_str)."""
    from datetime import datetime, timedelta

    # Границы ставки — в сервисном слое (единый источник для бота и сайта).
    # Раньше проверялись только в мёртвом bot/handlers/duel.py — вызов с сайта
    # полностью обходил лимиты (БЛОК 36 / GAME_BIBLE «Известные проблемы» №6).
    if not (DUEL_MIN_BET <= stake <= DUEL_MAX_BET):
        return False, f"Ставка дуэли: от {int(DUEL_MIN_BET)} до {int(DUEL_MAX_BET)} 🪙."

    # Check cooldown
    last = await get_cooldown(db, challenger_id, challenged_id)
    if last:
        try:
            last_dt = parse_dt(last)
            if datetime.now() - last_dt < timedelta(hours=DUEL_COOLDOWN_HOURS):
                remaining = timedelta(hours=DUEL_COOLDOWN_HOURS) - (datetime.now() - last_dt)
                h, rem = divmod(int(remaining.total_seconds()), 3600)
                m = rem // 60
                return False, f"КД с этим игроком: ещё {h}ч {m}мин."
        except ValueError:
            pass

    # Reserve stake atomically — prevents double-spend under concurrency
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT user_balance_mora FROM users WHERE user_tg_id = ? FOR UPDATE",
                (challenger_id,),
            ) as c:
                row = await c.fetchone()
            bal_mora = row[0] if row else 0.0
            reserved = await _get_reserved(db, challenger_id)
            free = bal_mora - reserved
            if free < stake:
                return False, f"Недостаточно Моры (нужно {stake:.0f} 🪙, свободно {free:.0f} 🪙)."

            await _add_reserve(db, challenger_id, stake)
            duel_id = await create_duel(
                db, challenger_id, challenged_id, chat_id, stake, 0
            )
    except Exception as e:
        return False, f"Ошибка: {e}"

    return True, {"duel_id": duel_id}


async def accept_duel(
    db,
    duel_id: int,
) -> tuple[bool, dict | str]:
    """Process the challenged player accepting. Resolve the duel.
    Returns (True, result_dict) or (False, error_str)."""
    # Lock duel row immediately to prevent double-accept race condition
    async with db.connection.transaction():
        async with db.execute(
            "SELECT id, status, stake, challenger_id, challenged_id, challenger_pet_id, chat_id "
            "FROM duels WHERE id = ? FOR UPDATE",
            (duel_id,),
        ) as _dc:
            _drow = await _dc.fetchone()
        if not _drow or _drow[1] != "pending":
            return False, "Вызов уже недействителен."
        # Mark as processing immediately to block concurrent accepts
        await db.execute("UPDATE duels SET status = 'processing' WHERE id = ?", (duel_id,))

    duel = await get_duel(db, duel_id)
    if not duel:
        return False, "Вызов не найден."

    stake = duel["stake"]
    challenged_id = duel["challenged_id"]
    challenger_id = duel["challenger_id"]

    # Reserve challenged's stake atomically
    async with db.connection.transaction():
        async with db.execute(
            "SELECT user_balance_mora FROM users WHERE user_tg_id = ? FOR UPDATE",
            (challenged_id,),
        ) as c:
            row = await c.fetchone()
        bal_mora = row[0] if row else 0.0
        reserved = await _get_reserved(db, challenged_id)
        if bal_mora - reserved < stake:
            # Properly close the duel so it doesn't stay stuck in 'processing'
            await set_duel_status(db, duel_id, "declined")
            await _remove_reserve(db, challenger_id, stake)
            return False, f"Недостаточно Моры для принятия ставки ({stake:.0f} 🪙)."
        await _add_reserve(db, challenged_id, stake)

    # Боёвка 3.0: сила обеих сторон — из отрядов Казармы
    challenged_power = await squad_power(db, challenged_id)
    challenger_power = await squad_power(db, challenger_id)

    winner_id = challenger_id if challenger_power >= challenged_power else challenged_id
    loser_id = challenged_id if winner_id == challenger_id else challenger_id

    # Settle finances: loser's stake → winner (minus commission)
    total_pot = stake * 2.0
    commission = total_pot * DUEL_COMMISSION
    winner_gain = total_pot - commission - stake  # net gain (already deducted stake from winner)

    # Settle all finances atomically
    async with db.connection.transaction():
        await _remove_reserve(db, challenger_id, stake)
        await _remove_reserve(db, challenged_id, stake)
        await eco_repo.add_balance(db, loser_id, mora=-stake,
                                   source="duel_loss", chat_id=duel["chat_id"])
        await eco_repo.add_balance(db, winner_id, mora=winner_gain,
                                   source="duel_win", chat_id=duel["chat_id"])
        await set_duel_status(db, duel_id, "finished",
                              winner_id=winner_id,
                              challenged_pet_id=0,
                              winner_gain=winner_gain,
                              commission=commission)
        await set_cooldown(db, challenger_id, challenged_id)

    return True, {
        "duel_id": duel_id,
        "winner_id": winner_id,
        "loser_id": loser_id,
        "challenger_id": challenger_id,
        "challenged_id": challenged_id,
        "winner_gain": winner_gain,
        "stake": stake,
        "commission": commission,
        "challenger_power": challenger_power,
        "challenged_power": challenged_power,
        "chat_id": duel["chat_id"],
    }


async def decline_duel(db, duel_id: int) -> bool:
    """Decline or timeout a duel. Return challenger's stake."""
    duel = await get_duel(db, duel_id)
    if not duel or duel["status"] != "pending":
        return False
    stake = duel["stake"]
    await _remove_reserve(db, duel["challenger_id"], stake)
    await set_duel_status(db, duel_id, "declined")
    await db.commit()
    return True


# ── Reserve helpers ───────────────────────────────────────────────────────────

async def _get_reserved(db, user_id: int) -> float:
    async with db.execute(
        "SELECT reserved_mora FROM user_reserve WHERE user_id = ?", (user_id,)
    ) as c:
        row = await c.fetchone()
    return row[0] if row else 0.0


async def _add_reserve(db, user_id: int, amount: float) -> None:
    await db.execute(
        "INSERT INTO user_reserve (user_id, reserved_mora) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET reserved_mora = user_reserve.reserved_mora + ?",
        (user_id, amount, amount),
    )


async def _remove_reserve(db, user_id: int, amount: float) -> None:
    await db.execute(
        "UPDATE user_reserve SET reserved_mora = GREATEST(0, reserved_mora - ?) WHERE user_id = ?",
        (amount, user_id),
    )
