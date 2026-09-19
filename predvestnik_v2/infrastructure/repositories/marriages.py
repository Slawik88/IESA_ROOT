# infrastructure/repositories/marriages.py
import aiosqlite
from asyncpg.exceptions import UndefinedTableError, UniqueViolationError
from core.economy_contract import IdempotencyConflict, InsufficientBalance
from infrastructure.repositories.economy_ledger import apply_balance_change, find_balance_replay

# item-цена → (колонка баланса, дельта-поле wallet_log, иконка)
_GIFT_PRICE_FIELDS = {
    "price_mora":     ("user_balance_mora",     "delta_mora",     "🪙"),
    "price_diamonds": ("user_balance_diamonds", "delta_diamonds", "💎"),
    "price_zarniki":  ("user_balance_zarniki",  "delta_zarniki",  "✨"),
}


# Семейный кошелёк на 4 валюты (Implementation Block 5). Колонки whitelisted —
# currency проверяется по ключам словаря, интерполяция имён колонок безопасна.
FAMILY_CURRENCIES: dict[str, dict] = {
    "mora":      {"user_col": "user_balance_mora",      "fam_col": "family_balance",             "icon": "🪙", "label": "Мора"},
    "diamonds":  {"user_col": "user_balance_diamonds",  "fam_col": "family_balance_diamonds",    "icon": "💎", "label": "Алмазы"},
    "dark_mora": {"user_col": "user_balance_dark_mora", "fam_col": "family_balance_dark_mora",   "icon": "🌑", "label": "Тёмная Мора"},
    "zarniki":   {"user_col": "user_balance_zarniki",   "fam_col": "family_balance_zarniki",     "icon": "✨", "label": "Зарники"},
}


class MarriageConflict(RuntimeError):
    """The global marriage invariant rejected a create/accept action."""


async def get_user_marriage(
    db: aiosqlite.Connection, user_id: int
) -> dict | None:
    """Брак — глобальный (один на пользователя, не зависит от чата)."""
    async with db.execute(
        "SELECT id, chat_id, user1_id, user1_name, user2_id, user2_name, marriage_date, "
        "family_balance, "
        "COALESCE(family_balance_diamonds, 0)  AS family_balance_diamonds, "
        "COALESCE(family_balance_dark_mora, 0) AS family_balance_dark_mora, "
        "COALESCE(family_balance_zarniki, 0)   AS family_balance_zarniki "
        "FROM marriage_members mm JOIN marriages m ON m.id = mm.marriage_id "
        "WHERE mm.user_id = ? AND m.ended_at IS NULL "
        "ORDER BY m.marriage_date DESC LIMIT 1",
        (user_id,),
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_family_bank_mora_cap(db, marriage_id: int) -> float:
    """R8: кап 🪙-части общака = FAMILY_BANK_DEFAULT_CAP + лучший bank_bonus
    Дракона любого из супругов (Дракон должен стоять в питомнике, не на складе).
    Раньше константа была объявлена, но нигде не проверялась — общак был
    безлимитным, а строка Дракона «🏦 +N к банку» — декоративной (БЛОК 36.3)."""
    from core.constants import FAMILY_BANK_DEFAULT_CAP, DRAGON_BONUSES
    async with db.execute(
        "SELECT COALESCE(MAX(p.pet_level), 0) FROM pets p "
        "JOIN marriages m ON m.id = ? "
        "AND p.owner_id IN (m.user1_id, m.user2_id) "
        "WHERE p.species_id = 'dragon' AND p.placement IN ('active', 'passive')",
        (marriage_id,),
    ) as c:
        row = await c.fetchone()
    lvl = int(row[0] or 0)
    bonus = DRAGON_BONUSES.get(lvl, {}).get("bank_bonus", 0.0) if lvl > 0 else 0.0
    return float(FAMILY_BANK_DEFAULT_CAP) + float(bonus)


async def family_bank_transaction(
    db: aiosqlite.Connection,
    marriage_id: int,
    user_id: int,
    amount: float,
    action: str,
    currency: str = "mora",
) -> tuple[bool, str]:
    """Депозит/вывод любой из 4 валют между личным балансом и семейным кошельком.
    Любой супруг может тратить ВСЮ сумму семейного кошелька (общий пул).
    R8: 🪙-часть общака ограничена капом (get_family_bank_mora_cap)."""
    # The former direct-column writer has no idempotency or premium-custody
    # proof.  Keep every old caller fail-closed while the reviewed ledger path
    # is completed; public endpoints must use family_wallet_v1 afterwards.
    return False, "Семейный кошелёк временно закрыт для проверяемого переноса."
    meta = FAMILY_CURRENCIES.get(currency)
    if not meta:
        return False, "Неизвестная валюта."
    if amount <= 0:
        return False, "Сумма должна быть больше нуля."
    user_col, fam_col = meta["user_col"], meta["fam_col"]

    try:
        async with db.connection.transaction():
            # FOR UPDATE на строке брака — защита от гонки двух супругов
            async with db.execute(
                f"SELECT COALESCE({fam_col}, 0) FROM marriages WHERE id = ? FOR UPDATE",
                (marriage_id,),
            ) as cursor:
                m_row = await cursor.fetchone()
                if not m_row:
                    return False, "Брак не найден."
                family_balance = float(m_row[0])

            if action == "deposit":
                if currency == "mora":
                    cap = await get_family_bank_mora_cap(db, marriage_id)
                    free = max(0.0, cap - family_balance)
                    if amount > free:
                        _cap_s = f"{int(cap):,}".replace(",", " ")
                        _free_s = f"{int(free):,}".replace(",", " ")
                        return False, (
                            f"🏦 Кап общака: {_cap_s} 🪙 (свободно {_free_s}). "
                            f"Кап поднимает Дракон в питомнике."
                        )
                async with db.execute(
                    f"SELECT COALESCE({user_col}, 0) FROM users WHERE user_tg_id = ? FOR UPDATE",
                    (user_id,),
                ) as c:
                    u_row = await c.fetchone()
                user_bal = float(u_row[0]) if u_row else 0.0
                if user_bal < amount:
                    return False, f"Недостаточно личной валюты: {meta['icon']} {meta['label']}."
                await db.execute(
                    f"UPDATE users SET {user_col} = COALESCE({user_col}, 0) - ? WHERE user_tg_id = ?",
                    (amount, user_id),
                )
                await db.execute(
                    f"UPDATE marriages SET {fam_col} = COALESCE({fam_col}, 0) + ? WHERE id = ?",
                    (amount, marriage_id),
                )
            elif action == "withdraw":
                if family_balance < amount:
                    return False, f"Недостаточно в семейном кошельке: {meta['icon']} {meta['label']}."
                await db.execute(
                    f"UPDATE marriages SET {fam_col} = COALESCE({fam_col}, 0) - ? WHERE id = ?",
                    (amount, marriage_id),
                )
                await db.execute(
                    "INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING",
                    (user_id,),
                )
                await db.execute(
                    f"UPDATE users SET {user_col} = COALESCE({user_col}, 0) + ? WHERE user_tg_id = ?",
                    (amount, user_id),
                )
            else:
                return False, "Неизвестное действие."

        return True, "Успешно."
    except Exception as e:
        return False, f"Ошибка: {e}"


async def purchase_partner_gift(
    db, buyer_id: int, partner_id: int, gift_id: str, *, idempotency_key: str,
):
    """Buy one social keepsake through the canonical ledger, exactly once."""
    from core.registry import PARTNER_GIFTS
    gift = PARTNER_GIFTS.get(gift_id)
    if not gift:
        return False, "Неизвестный подарок.", None

    currency = icon = None
    amount = 0.0
    for price_key, (_column, delta_field, ic) in _GIFT_PRICE_FIELDS.items():
        if gift.get(price_key):
            currency = delta_field.removeprefix("delta_")
            icon, amount = ic, float(gift[price_key])
            break
    if not currency or not idempotency_key:
        return False, "У подарка не задана цена.", None

    try:
        async with db.connection.transaction():
            delta = {currency: -amount}
            replay = await find_balance_replay(
                db, buyer_id, delta,
                reason_code="partner_gift", idempotency_key=idempotency_key,
                source_type="social", reference_type="partner_gift",
                reference_id=f"{partner_id}:{gift_id}",
            )
            if replay:
                return True, gift["msg"], gift
            async with db.execute(
                "SELECT 1 FROM marriages WHERE ended_at IS NULL AND "
                "(user1_id = ? AND user2_id = ?) OR (user1_id = ? AND user2_id = ?) "
                "FOR SHARE",
                (buyer_id, partner_id, partner_id, buyer_id),
            ) as cursor:
                if not await cursor.fetchone():
                    return False, "Партнёр больше не состоит с вами в союзе.", None
            await apply_balance_change(
                db, buyer_id, delta,
                reason_code="partner_gift", idempotency_key=idempotency_key,
                source_type="social", reference_type="partner_gift",
                reference_id=f"{partner_id}:{gift_id}",
                metadata={"gift_id": gift_id, "partner_id": int(partner_id), "no_power": True},
                target_id=partner_id, note=gift_id,
            )

            await db.execute(
                "INSERT INTO partner_gifts_log (sender_id, receiver_id, gift_id) VALUES (?, ?, ?)",
                (buyer_id, partner_id, gift_id),
            )
        return True, gift["msg"], gift
    except InsufficientBalance:
        return False, f"Недостаточно средств ({icon}).", None
    except IdempotencyConflict:
        return False, "Этот запрос уже использован для другого подарка.", None
    except Exception:
        return False, "Подарок не вручён. Баланс не изменён.", None


async def get_received_gifts(db, user_id: int, limit: int = 5) -> list[dict]:
    """Последние полученные подарки (для отображения в карточке брака)."""
    async with db.execute(
        "SELECT gift_id, sender_id, sent_at FROM partner_gifts_log "
        "WHERE receiver_id = ? ORDER BY sent_at DESC LIMIT ?",
        (user_id, limit),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def create_marriage(
    db: aiosqlite.Connection,
    chat_id: int,
    u1_id: int,
    u1_name: str,
    u2_id: int,
    u2_name: str,
    *,
    proposal_id: int | None = None,
) -> int:
    """Create a global marriage and claim both accounts atomically.

    ``marriage_members.user_id`` is the final authority, so two simultaneous
    accepts involving the same account cannot create two marriages.  The
    registry is installed only by the reviewed operator migration; failing
    closed here is safer than falling back to the legacy unconstrained table.
    """
    if int(u1_id) == int(u2_id):
        raise MarriageConflict("Нельзя заключить брак с самим собой.")
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT user_id FROM marriage_members WHERE user_id IN (?, ?) FOR UPDATE",
                (u1_id, u2_id),
            ) as cursor:
                if await cursor.fetchone():
                    raise MarriageConflict("Один из игроков уже состоит в браке.")
            async with db.execute(
                "INSERT INTO marriages (chat_id, user1_id, user1_name, user2_id, user2_name) "
                "VALUES (?, ?, ?, ?, ?) RETURNING id",
                (chat_id, u1_id, u1_name, u2_id, u2_name),
            ) as cursor:
                marriage_id = int((await cursor.fetchone())[0])
            await db.execute(
                "INSERT INTO marriage_members (user_id, marriage_id) VALUES (?, ?), (?, ?)",
                (u1_id, marriage_id, u2_id, marriage_id),
            )
            if proposal_id is not None:
                async with db.execute(
                    "UPDATE marriage_proposals SET status = 'accepted' "
                    "WHERE id = ? AND status = 'pending' RETURNING id",
                    (proposal_id,),
                ) as cursor:
                    if not await cursor.fetchone():
                        raise MarriageConflict("Предложение уже обработано.")
        return marriage_id
    except UniqueViolationError as exc:
        raise MarriageConflict("Один из игроков уже состоит в браке.") from exc
    except UndefinedTableError as exc:
        raise RuntimeError(
            "Реестр браков ещё не мигрирован; создание новых браков остановлено безопасно."
        ) from exc


async def delete_marriage(db: aiosqlite.Connection, user_id: int) -> bool:
    """Close, never delete, the active marriage of ``user_id``.

    Family-wallet and payment records retain the marriage ID forever.  We only
    release the two active membership claims after verifying that no property
    is still attached to that family.  This is deliberately defensive even
    though bot/API adapters perform the same user-facing check.
    """
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT m.id, COALESCE(m.family_balance, 0), "
                "COALESCE(m.family_balance_diamonds, 0), "
                "COALESCE(m.family_balance_dark_mora, 0), "
                "COALESCE(m.family_balance_zarniki, 0) "
                "FROM marriage_members mm JOIN marriages m ON m.id = mm.marriage_id "
                "WHERE mm.user_id = ? AND m.ended_at IS NULL FOR UPDATE",
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()
            if not row:
                return False
            marriage_id = int(row[0])
            if any(float(value or 0) > 0 for value in row[1:]):
                raise MarriageConflict("Семейный кошелёк необходимо урегулировать до развода.")
            async with db.execute(
                "SELECT 1 FROM pets WHERE marriage_id = ? LIMIT 1 FOR SHARE", (marriage_id,)
            ) as cursor:
                if await cursor.fetchone():
                    raise MarriageConflict("Семейных питомцев необходимо урегулировать до развода.")
            try:
                async with db.execute(
                    "SELECT mora, diamonds, dark_mora, zarniki FROM family_wallet_balances "
                    "WHERE marriage_id = ? FOR UPDATE",
                    (marriage_id,),
                ) as cursor:
                    custody = await cursor.fetchone()
                if custody and any(float(value or 0) > 0 for value in custody):
                    raise MarriageConflict("Семейный кошелёк необходимо урегулировать до развода.")
            except UndefinedTableError:
                # Pre-ledger installations are protected by the legacy balance
                # check above; migration itself remains deployable in stages.
                pass
            await db.execute("UPDATE marriages SET ended_at = NOW() WHERE id = ?", (marriage_id,))
            await db.execute("DELETE FROM marriage_members WHERE marriage_id = ?", (marriage_id,))
        return True
    except UndefinedTableError as exc:
        raise RuntimeError("Реестр браков ещё не мигрирован; развод остановлен безопасно.") from exc


async def get_all_marriages(db: aiosqlite.Connection, chat_id: int) -> list[dict]:
    async with db.execute(
        "SELECT * FROM marriages WHERE chat_id = ? AND ended_at IS NULL ORDER BY marriage_date DESC",
        (chat_id,),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


# ── Marriage proposals ─────────────────────────────────────────────────────────

async def create_proposal(db, chat_id: int, proposer_id: int, target_id: int) -> int:
    """Insert a pending proposal (24h TTL). Expires any existing pending proposal first."""
    # Expire stale pending proposals between same pair in same chat
    await db.execute(
        "UPDATE marriage_proposals SET status = 'expired' "
        "WHERE chat_id = ? AND proposer_id = ? AND target_id = ? AND status = 'pending'",
        (chat_id, proposer_id, target_id),
    )
    async with db.execute(
        "INSERT INTO marriage_proposals (chat_id, proposer_id, target_id, expires_at) "
        "VALUES (?, ?, ?, NOW() + INTERVAL '24 hours') RETURNING id",
        (chat_id, proposer_id, target_id),
    ) as c:
        row = await c.fetchone()
    return row[0] if row else 0


async def update_proposal_status(
    db, chat_id: int, proposer_id: int, target_id: int, status: str
) -> None:
    """Update the most recent pending proposal between two users in a chat."""
    await db.execute(
        "UPDATE marriage_proposals SET status = ? "
        "WHERE chat_id = ? AND proposer_id = ? AND target_id = ? AND status = 'pending'",
        (status, chat_id, proposer_id, target_id),
    )
