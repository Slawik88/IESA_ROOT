# infrastructure/repositories/marriages.py
from datetime import datetime, timedelta
import aiosqlite
from infrastructure.repositories.wallet_log import log_wallet

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
        "FROM marriages WHERE user1_id = ? OR user2_id = ? "
        "ORDER BY marriage_date DESC LIMIT 1",
        (user_id, user_id),
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else None


async def family_bank_transaction(
    db: aiosqlite.Connection,
    marriage_id: int,
    user_id: int,
    amount: float,
    action: str,
    currency: str = "mora",
) -> tuple[bool, str]:
    """Депозит/вывод любой из 4 валют между личным балансом и семейным кошельком.
    Любой супруг может тратить ВСЮ сумму семейного кошелька (общий пул)."""
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


async def purchase_partner_gift(db, buyer_id: int, partner_id: int, gift_id: str):
    """Купить подарок партнёру (Block 5.4). Оплата с личного баланса дарителя,
    бафф-подарки накладывают study_xp на ПАРТНЁРА. Returns (ok, msg, gift)."""
    from core.registry import PARTNER_GIFTS
    gift = PARTNER_GIFTS.get(gift_id)
    if not gift:
        return False, "Неизвестный подарок.", None

    col = delta_field = icon = None
    amount = 0.0
    for price_key, (c, d, ic) in _GIFT_PRICE_FIELDS.items():
        if gift.get(price_key):
            col, delta_field, icon, amount = c, d, ic, float(gift[price_key])
            break
    if not col:
        return False, "У подарка не задана цена.", None

    try:
        async with db.connection.transaction():
            async with db.execute(
                f"SELECT COALESCE({col}, 0) FROM users WHERE user_tg_id = ? FOR UPDATE",
                (buyer_id,),
            ) as c:
                row = await c.fetchone()
            if not row or float(row[0]) < amount:
                return False, f"Недостаточно средств ({icon}).", None
            await db.execute(
                f"UPDATE users SET {col} = COALESCE({col}, 0) - ? WHERE user_tg_id = ?",
                (amount, buyer_id),
            )
            await log_wallet(db, buyer_id, **{delta_field: -amount},
                             source="partner_gift", target_id=partner_id, note=gift_id)

            if gift.get("kind") == "buff":
                expires = (datetime.utcnow() + timedelta(hours=gift["buff_hours"])).strftime("%Y-%m-%d %H:%M:%S")
                await db.execute(
                    "INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING",
                    (partner_id,),
                )
                await db.execute(
                    "INSERT INTO player_buffs (user_id, buff_type, uses_left, expires_at, value) "
                    "VALUES (?, 'study_xp', 1, ?, ?) "
                    "ON CONFLICT(user_id, buff_type) DO UPDATE SET "
                    "expires_at = GREATEST(player_buffs.expires_at, EXCLUDED.expires_at), "
                    "value = GREATEST(player_buffs.value, EXCLUDED.value)",
                    (partner_id, expires, gift["buff_value"]),
                )

            await db.execute(
                "INSERT INTO partner_gifts_log (sender_id, receiver_id, gift_id) VALUES (?, ?, ?)",
                (buyer_id, partner_id, gift_id),
            )
        return True, gift["msg"], gift
    except Exception as e:
        return False, f"Ошибка: {e}", None


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
):
    await db.execute(
        "INSERT INTO marriages (chat_id, user1_id, user1_name, user2_id, user2_name) "
        "VALUES (?, ?, ?, ?, ?)",
        (chat_id, u1_id, u1_name, u2_id, u2_name),
    )
    await db.commit()


async def delete_marriage(db: aiosqlite.Connection, user_id: int):
    await db.execute(
        "DELETE FROM marriages WHERE user1_id = ? OR user2_id = ?",
        (user_id, user_id),
    )
    await db.commit()


async def get_all_marriages(db: aiosqlite.Connection, chat_id: int) -> list[dict]:
    async with db.execute(
        "SELECT * FROM marriages WHERE chat_id = ? ORDER BY marriage_date DESC",
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
