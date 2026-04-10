"""
api/marriage.py — marriage status, proposal, and family wallet operations.

All functions are async; the mini app wraps them with async_to_sync.
"""
import html as _html


async def get_status(uid: int, chat_id: int) -> dict:
    """Return marriage status and singles list for the given user in chat.

    Returns {has_partner, partner_id, partner_name, married_at, singles}.
    singles is a list of {user_id, name, xp} for single users in chat,
    excluding uid itself.
    """
    from database.db import get_marriage, get_user, get_singles

    marriage = await get_marriage(uid, chat_id)
    has_partner = marriage is not None
    partner_id = marriage["partner_id"] if marriage else None
    married_at = marriage["married_at"] if marriage else None

    partner_name = None
    if partner_id:
        partner = await get_user(partner_id)
        partner_name = partner["full_name"] if partner else f"user_{partner_id}"

    singles_rows = await get_singles(chat_id, limit=20)
    singles = [
        {
            "user_id": r["user_id"],
            "name":    r["full_name"] or f"user_{r['user_id']}",
            "xp":      r["xp"] or 0,
        }
        for r in singles_rows
        if r["user_id"] != uid
    ]

    return {
        "has_partner":  has_partner,
        "partner_id":   partner_id,
        "partner_name": partner_name,
        "married_at":   str(married_at) if married_at else None,
        "singles":      singles,
    }


async def propose(uid: int, target_id: int, chat_id: int) -> dict:
    """Create a marriage proposal from uid to target_id.

    Raises ValueError with a Russian message on any validation error.
    Returns {ok, proposal_id, message}.
    """
    from database.db import get_marriage, get_user, create_marriage_proposal

    if uid == target_id:
        raise ValueError("Нельзя предложить руку самому себе")

    if await get_marriage(uid, chat_id):
        raise ValueError("Ты уже в браке. Сначала разведись.")

    if await get_marriage(target_id, chat_id):
        raise ValueError("Этот игрок уже состоит в браке.")

    to_user = await get_user(target_id)
    to_name = to_user["full_name"] if to_user else f"user_{target_id}"

    proposal_id = await create_marriage_proposal(uid, target_id, chat_id)

    return {
        "ok":          True,
        "proposal_id": proposal_id,
        "message":     f"Предложение отправлено игроку {_html.escape(to_name)}!",
    }


async def respond_to_proposal_api(uid: int, chat_id: int, proposal_id: int, action: str) -> dict:
    """Accept or reject a proposal as the recipient.

    On accept, creates the marriage.
    Raises ValueError on error.
    Returns {ok, action, partner_id?, partner_name?}.
    """
    from database.db import (
        respond_to_proposal, create_marriage, get_user, get_pending_proposals,
    )

    if action not in ("accept", "reject"):
        raise ValueError("action must be accept or reject")

    # Verify this proposal is for the current user
    proposals = await get_pending_proposals(uid, chat_id)
    proposal = None
    for p in proposals:
        if p.get("id") == proposal_id:
            proposal = p
            break
    if not proposal:
        raise ValueError("Предложение не найдено или уже обработано")

    status = "accepted" if action == "accept" else "rejected"
    result = await respond_to_proposal(proposal_id, status)
    if not result:
        raise ValueError("Не удалось обработать предложение")

    if action == "accept":
        from_uid = result["from_user_id"]
        await create_marriage(from_uid, uid, chat_id)
        partner = await get_user(from_uid)
        partner_name = partner["full_name"] if partner else f"user_{from_uid}"

        # Season XP за регистрацию брака (обоим партнёрам)
        try:
            from database.db import add_season_xp
            await add_season_xp(from_uid, 15)  # +15 XP инициатору
            await add_season_xp(uid, 15)        # +15 XP принявшему
        except Exception as _e:
            _log.debug("%s", _e)

        return {
            "ok": True,
            "action": "accepted",
            "partner_id": from_uid,
            "partner_name": partner_name,
        }

    return {"ok": True, "action": "rejected"}


async def family_deposit(uid: int, chat_id: int, amount: int) -> dict:
    """Deposit mora into the family wallet.

    Raises ValueError on error.
    Returns {ok, amount, personal_balance, family_balance}.
    """
    from database.db import (
        get_mora, add_to_family_wallet,
        log_family_transaction, is_user_single,
    )
    from database.postgres import connect as postgres_connect

    if amount <= 0:
        raise ValueError("Сумма должна быть > 0")

    single = await is_user_single(uid, chat_id)
    if single:
        raise ValueError("Нет семейного кошелька — ты не в браке")

    mora_row = await get_mora(uid, chat_id)
    balance = mora_row["balance"] if mora_row else 0
    if balance < amount:
        raise ValueError(f"Недостаточно Моры ({balance}/{amount} 🪙)")

    async with postgres_connect() as db:
        cursor = await db.execute(
            "UPDATE users SET balance=balance-? WHERE user_id=? AND COALESCE(balance,0)>=?",
            (amount, uid, amount),
        )
        if cursor.rowcount == 0:
            raise ValueError("Не удалось списать Мору")
        await db.commit()

    family_bal = await add_to_family_wallet(chat_id, uid, amount)
    await log_family_transaction(chat_id, uid, "deposit", amount)

    # Log to personal wallet ledger
    try:
        from api.economy import log_wallet_tx
        await log_wallet_tx(uid, chat_id, "expense", amount, "family_deposit",
                            "Вклад в семейный кошелёк")
    except Exception as _e:
        _log.debug("%s", _e)

    new_mora = await get_mora(uid, chat_id)
    personal_balance = new_mora["balance"] if new_mora else 0

    return {
        "ok": True,
        "amount": amount,
        "personal_balance": personal_balance,
        "family_balance": family_bal,
    }


async def family_withdraw(uid: int, chat_id: int, amount: int) -> dict:
    """Withdraw mora from the family wallet to personal balance.

    Deducts from the user's own contribution first, then partner's.
    Atomic: balance check + deduct happen inside deduct_family_pool with FOR UPDATE.
    Raises ValueError on error.
    Returns {ok, amount, personal_balance, family_balance}.
    """
    from database.db import (
        add_mora, get_mora,
        deduct_family_pool, log_family_transaction, is_user_single,
        get_total_family_balance,
    )

    if amount <= 0:
        raise ValueError("Сумма должна быть > 0")

    single = await is_user_single(uid, chat_id)
    if single:
        raise ValueError("Нет семейного кошелька — ты не в браке")

    # get_total_family_balance нужен только для получения partner_id
    _total_bal, _my_bal, partner_id = await get_total_family_balance(chat_id, uid)

    # Атомарная проверка + списание (FOR UPDATE внутри deduct_family_pool)
    new_family_bal = await deduct_family_pool(chat_id, uid, partner_id, amount)
    await add_mora(uid, chat_id, amount)
    await log_family_transaction(chat_id, uid, "withdraw", amount)

    # Log to personal wallet ledger (income side)
    try:
        from api.economy import log_wallet_tx
        await log_wallet_tx(uid, chat_id, "income", amount, "family_withdraw",
                            "Снятие из семейного кошелька")
    except Exception as _e:
        _log.debug("%s", _e)

    new_mora = await get_mora(uid, chat_id)
    personal_balance = new_mora["balance"] if new_mora else 0

    return {
        "ok": True,
        "amount": amount,
        "personal_balance": personal_balance,
        "family_balance": new_family_bal,
    }


async def get_family_log(uid: int, chat_id: int, limit: int = 30) -> dict:
    """Return family wallet transaction log for the user's pair only.

    Returns {ok, log: [{user_id, user_name, action, amount, description, created_at}]}.
    """
    from database.db import get_family_wallet_log, get_marriage
    from database.postgres import connect as postgres_connect

    # Resolve partner_id so query is scoped to this pair only
    marriage = await get_marriage(uid, chat_id)
    partner_id: int | None = marriage["partner_id"] if marriage else None

    # Auto-cleanup old records (> 60 days)
    async with postgres_connect() as db:
        await db.execute(
            "DELETE FROM family_wallet_log WHERE chat_id=? AND created_at < NOW() - INTERVAL '60 days'",
            (chat_id,),
        )
        await db.commit()

    rows = await get_family_wallet_log(chat_id, uid, partner_id, limit)
    log_entries = []
    for r in rows:
        log_entries.append({
            "user_id": r.get("user_id"),
            "user_name": r.get("full_name") or f"Игрок {r.get('user_id')}",
            "action": r.get("action"),
            "amount": r.get("amount"),
            "description": r.get("description") or "",
            "created_at": str(r.get("created_at") or ""),
        })

    return {"ok": True, "log": log_entries}
