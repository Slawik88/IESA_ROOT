"""
api/bank.py — unified bank deposit/withdraw operations.

All functions are async; the mini app wraps them with async_to_sync.
"""
from datetime import datetime, timezone
import logging
_log = logging.getLogger(__name__)

# +2% rate bonus for single (unmarried) players
SINGLES_BANK_BONUS = 0.02


async def get_bank_info(uid: int, chat_id: int) -> dict:
    """
    Returns full bank info: personal balance, family balance, active deposits
    with maturity analysis, and available plans.
    """
    from database.db import get_mora, get_user_deposits, is_user_single

    try:
        from config import BANK_PLANS, BANK_MIN_DEPOSIT, BANK_MAX_DEPOSIT, BANK_EARLY_PENALTY_PCT
    except Exception:
        BANK_PLANS = {}
        BANK_MIN_DEPOSIT, BANK_MAX_DEPOSIT, BANK_EARLY_PENALTY_PCT = 100, 10_000, 0.10

    from database.postgres import connect as postgres_connect

    # Personal balance
    mora_row = await get_mora(uid, chat_id)
    balance  = mora_row["balance"] if mora_row else 0

    # Family balance — scoped to this user's pair only
    family_balance = 0
    try:
        from database.db import get_total_family_balance
        total_fbal, _my, _pid = await get_total_family_balance(chat_id, uid)
        family_balance = total_fbal
    except Exception as _e:
        _log.debug("%s", _e)
    # Deposits
    raw_deps   = await get_user_deposits(uid, chat_id)
    single     = await is_user_single(uid, chat_id)
    now        = datetime.now(timezone.utc)
    deposits   = []
    for dep in raw_deps:
        dep_id     = dep["id"]
        amount     = dep["amount"]
        rate       = dep["rate"]
        created_at = dep["created_at"]
        matures_at = dep["matures_at"]

        if isinstance(matures_at, str):
            matures_at = datetime.fromisoformat(matures_at.replace("Z", "+00:00"))
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if matures_at is not None and getattr(matures_at, "tzinfo", None) is None:
            matures_at = matures_at.replace(tzinfo=timezone.utc)
        if created_at is not None and getattr(created_at, "tzinfo", None) is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        mature          = now >= matures_at
        reward          = int(amount * rate)
        time_left_secs  = max(0, (matures_at - now).total_seconds()) if not mature else 0
        time_left_h     = int(time_left_secs // 3600)
        time_left_m     = int((time_left_secs % 3600) // 60)
        total_secs      = max(1, (matures_at - created_at).total_seconds())
        elapsed_secs    = (now - created_at).total_seconds()
        progress_pct    = min(100, max(0, int(elapsed_secs / total_secs * 100)))
        plan_days       = max(1, round(total_secs / 86400))
        deposits.append({
            "id":              dep_id,
            "amount":          amount,
            "rate":            rate,
            "rate_pct":        round(rate * 100, 1),
            "reward":          reward,
            "mature":          mature,
            "time_left_h":     time_left_h,
            "time_left_m":     time_left_m,
            "progress_pct":    progress_pct,
            "plan_days":       plan_days,
            "matures_at_iso":  matures_at.strftime("%d.%m %H:%M"),
        })

    # Plans
    plans_out = []
    for key, p in BANK_PLANS.items():
        plans_out.append({
            "key":      key,
            "days":     p["days"],
            "rate_pct": round(p["rate"] * 100, 1),
            "label":    p.get("label", key),
            "amounts":  [a for a in (100, 250, 500, 1_000, 2_500, 5_000, 10_000)
                         if BANK_MIN_DEPOSIT <= a <= BANK_MAX_DEPOSIT],
        })

    return {
        "balance":           balance,
        "family_balance":    family_balance,
        "deposits":          deposits,
        "plans":             plans_out,
        "min_deposit":       BANK_MIN_DEPOSIT,
        "max_deposit":       BANK_MAX_DEPOSIT,
        "early_penalty_pct": round(BANK_EARLY_PENALTY_PCT * 100, 1),
        "singles_bonus":     single,
    }


async def deposit(uid: int, chat_id: int, plan_key: str,
                  amount: int, wallet: str = "personal") -> dict:
    """
    Open a bank deposit.

    Applies +2% singles bonus automatically.
    wallet: "personal" | "family"
    Raises ValueError on error.
    Returns {ok, deposit_id, amount, rate_pct, reward, days, new_balance, wallet, singles_bonus}
    """
    from database.db import (
        get_mora, is_user_single,
    )

    try:
        from config import BANK_PLANS, BANK_MIN_DEPOSIT, BANK_MAX_DEPOSIT
    except Exception:
        BANK_PLANS = {}
        BANK_MIN_DEPOSIT, BANK_MAX_DEPOSIT = 100, 10_000

    if plan_key not in BANK_PLANS:
        raise ValueError("Неизвестный план вклада")
    if not (BANK_MIN_DEPOSIT <= amount <= BANK_MAX_DEPOSIT):
        raise ValueError(f"Сумма вклада: {BANK_MIN_DEPOSIT}–{BANK_MAX_DEPOSIT} 🪙")
    if wallet not in ("personal", "family"):
        wallet = "personal"

    plan         = BANK_PLANS[plan_key]
    single       = await is_user_single(uid, chat_id)
    eff_rate     = plan["rate"] + (SINGLES_BANK_BONUS if single else 0.0)

    if wallet == "family":
        # Use the proper pair-aware deduction (FOR UPDATE, scoped to uid + partner_id)
        from database.db import deduct_family_pool, get_total_family_balance
        total_fbal, _my, partner_id = await get_total_family_balance(chat_id, uid)
        if total_fbal < amount:
            raise ValueError(f"Недостаточно семейных средств ({total_fbal}/{amount} 🪙)")

        # Atomic deduction from the pair's pool
        new_family_bal = await deduct_family_pool(chat_id, uid, partner_id, amount)

        # Create deposit
        from database.postgres import connect as postgres_connect
        now = datetime.now(timezone.utc)
        from datetime import timedelta
        matures = now + timedelta(days=plan["days"])
        async with postgres_connect() as db:
            dep_cursor = await db.execute(
                "INSERT INTO bank_deposits (user_id, chat_id, amount, rate, created_at, matures_at)"
                " VALUES (?,?,?,?,?,?) RETURNING id",
                (uid, chat_id, amount, eff_rate,
                 now.strftime("%Y-%m-%dT%H:%M"), matures.strftime("%Y-%m-%dT%H:%M")),
            )
            dep_row = await dep_cursor.fetchone()
            dep_id = dep_row[0] if dep_row else 0
            await db.commit()
        new_balance = new_family_bal
    else:
        from database.postgres import connect as postgres_connect
        async with postgres_connect() as db:
            # Atomic: deduct mora + create deposit in one transaction
            cursor = await db.execute(
                "UPDATE users SET balance=balance-? WHERE user_id=? AND COALESCE(balance,0)>=?",
                (amount, uid, amount),
            )
            if cursor.rowcount == 0:
                mora_row = await get_mora(uid, chat_id)
                bal = mora_row["balance"] if mora_row else 0
                raise ValueError(f"Недостаточно Моры ({bal}/{amount} 🪙)")
            now = datetime.now(timezone.utc)
            from datetime import timedelta
            matures = now + timedelta(days=plan["days"])
            dep_cursor = await db.execute(
                "INSERT INTO bank_deposits (user_id, chat_id, amount, rate, created_at, matures_at)"
                " VALUES (?,?,?,?,?,?) RETURNING id",
                (uid, chat_id, amount, eff_rate,
                 now.strftime("%Y-%m-%dT%H:%M"), matures.strftime("%Y-%m-%dT%H:%M")),
            )
            dep_row = await dep_cursor.fetchone()
            dep_id = dep_row[0] if dep_row else 0
            await db.commit()
            # Read new personal balance
            async with db.execute(
                "SELECT COALESCE(balance, 0) FROM users WHERE user_id=?",
                (uid,),
            ) as c:
                row = await c.fetchone()
            new_balance = row[0] if row else 0
    reward = int(amount * eff_rate)

    # Log to wallet ledger
    try:
        from api.economy import log_wallet_tx
        await log_wallet_tx(uid, chat_id, "expense", amount, "bank_deposit",
                            f"Вклад {plan_key} {plan['days']}д")
    except Exception as _e:
        _log.debug("%s", _e)
    # Check deposits achievement
    try:
        from api.achievements import check_and_award as _ach
        from database.postgres import connect as _pg
        async with _pg() as _db:
            async with _db.execute(
                "SELECT COUNT(*) FROM bank_deposits WHERE user_id=? AND chat_id=?",
                (uid, chat_id),
            ) as _c:
                _row = await _c.fetchone()
        await _ach(uid, chat_id, "deposits", int(_row[0]) if _row else 1)
    except Exception as _e:
        _log.debug("deposits achievement failed: %s", _e)
    return {
        "ok":            True,
        "deposit_id":    dep_id,
        "amount":        amount,
        "rate_pct":      round(eff_rate * 100, 1),
        "reward":        reward,
        "days":          plan["days"],
        "new_balance":   new_balance,
        "wallet":        wallet,
        "singles_bonus": single,
    }


async def withdraw(uid: int, chat_id: int, deposit_id: int) -> dict:
    """
    Withdraw a deposit (early or mature).

    Mature: interest_tax = 10% of interest; payout = amount + interest - interest_tax
    Early:  penalty = BANK_EARLY_PENALTY_PCT% of principal; payout = amount - penalty

    Raises ValueError on error.
    Returns {ok, deposit_id, payout, early, interest_tax, new_balance}
    """
    from database.db import add_mora, add_to_treasury, withdraw_deposit

    try:
        from config import BANK_EARLY_PENALTY_PCT
    except Exception:
        BANK_EARLY_PENALTY_PCT = 0.10

    dep_data = await withdraw_deposit(deposit_id)
    if not dep_data:
        raise ValueError("Вклад не найден или уже снят")

    if dep_data.get("user_id") != uid:
        raise ValueError("Это не твой вклад")

    amount     = dep_data["amount"]
    rate       = dep_data["rate"]
    matures_at = dep_data["matures_at"]

    if isinstance(matures_at, str):
        matures_at = datetime.fromisoformat(matures_at.replace("Z", "+00:00"))
    from datetime import timezone
    if matures_at is not None and getattr(matures_at, "tzinfo", None) is None:
        matures_at = matures_at.replace(tzinfo=timezone.utc)

    now        = datetime.now(timezone.utc)
    mature     = now >= matures_at

    if mature:
        interest      = int(amount * rate)
        interest_tax  = max(0, int(interest * 0.10))
        payout        = amount + interest - interest_tax
        early         = False
    else:
        penalty       = int(amount * BANK_EARLY_PENALTY_PCT)
        payout        = max(0, amount - penalty)
        interest_tax  = 0
        early         = True

    new_balance = await add_mora(uid, chat_id, payout)
    if interest_tax > 0:
        await add_to_treasury(chat_id, interest_tax, "bank_interest", uid)

    # Log to wallet ledger
    try:
        from api.economy import log_wallet_tx
        desc = f"Досрочно, штраф {amount - payout}🪙" if early else f"Прибыль {int(amount * rate)}🪙"
        await log_wallet_tx(uid, chat_id, "income", payout, "bank_withdraw", desc)
    except Exception as _e:
        _log.debug("%s", _e)

    return {
        "ok":           True,
        "deposit_id":   deposit_id,
        "payout":       payout,
        "early":        early,
        "interest_tax": interest_tax,
        "amount":       amount,
        "new_balance":  new_balance,
    }
