# infrastructure/repositories/shadow_merchant.py — БЛОК 13.X/24.A: Теневой Торговец.
# Ивенты (пророчество в чате), победители-ваучеры, покупка Теневых реликвий.
# Только SQL — логика слова/текстов в services/shadow_merchant.py.
from datetime import datetime, timezone

from core.registry import SHADOW_RELICS
from core.economy_contract import IdempotencyConflict, InsufficientBalance
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories.economy_ledger import apply_balance_change, find_balance_replay


# ── События ───────────────────────────────────────────────────────────────────

async def get_active_event(db: PGAdapter, chat_id: int) -> dict | None:
    async with db.execute(
        "SELECT id, chat_id, keyword, posted_at, expires_at FROM shadow_merchant_events "
        "WHERE chat_id = ? AND status = 'active' AND expires_at > NOW() "
        "ORDER BY id DESC LIMIT 1",
        (chat_id,),
    ) as c:
        r = await c.fetchone()
    return dict(r) if r else None


async def any_active(db: PGAdapter) -> bool:
    async with db.execute(
        "SELECT 1 FROM shadow_merchant_events WHERE status = 'active' AND expires_at > NOW() LIMIT 1"
    ) as c:
        return (await c.fetchone()) is not None


async def last_posted_at(db: PGAdapter) -> datetime | None:
    async with db.execute(
        "SELECT MAX(posted_at) FROM shadow_merchant_events"
    ) as c:
        r = await c.fetchone()
    val = r[0] if r else None
    if isinstance(val, str):
        val = datetime.fromisoformat(val.replace(" ", "T"))
    if val is not None and val.tzinfo is None:
        val = val.replace(tzinfo=timezone.utc)
    return val


async def create_event(db: PGAdapter, chat_id: int, keyword: str, minutes: int) -> int:
    async with db.execute(
        "INSERT INTO shadow_merchant_events (chat_id, keyword, expires_at, status) "
        "VALUES (?, ?, NOW() + make_interval(mins => ?), 'active') RETURNING id",
        (chat_id, keyword, minutes),
    ) as c:
        r = await c.fetchone()
    return int(r[0])


async def get_expired_active(db: PGAdapter) -> list[dict]:
    async with db.execute(
        "SELECT id, chat_id, keyword FROM shadow_merchant_events "
        "WHERE status = 'active' AND expires_at <= NOW()"
    ) as c:
        rows = await c.fetchall()
    return [dict(r) for r in rows]


async def close_event(db: PGAdapter, event_id: int, status: str = "done") -> None:
    await db.execute(
        "UPDATE shadow_merchant_events SET status = ? WHERE id = ?", (status, event_id)
    )


async def winners_count(db: PGAdapter, event_id: int) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM shadow_merchant_winners WHERE event_id = ?", (event_id,)
    ) as c:
        r = await c.fetchone()
    return int(r[0] or 0)


async def add_winner(db: PGAdapter, event_id: int, user_id: int, max_winners: int,
                     reward_by_position: dict[int, int]) -> tuple[int, float] | None:
    """Атомарно добавляет победителя. Возвращает (позиция, награда 🌑) либо None,
    если места кончились или юзер уже победитель. Победная строка (redeemed=FALSE)
    одновременно является ваучером на покупку Теневой реликвии."""
    async with db.connection.transaction():
        # Лок события — сериализуем гонку «двое угадали одновременно»
        async with db.execute(
            "SELECT id FROM shadow_merchant_events WHERE id = ? AND status = 'active' FOR UPDATE",
            (event_id,),
        ) as c:
            if not await c.fetchone():
                return None
        async with db.execute(
            "SELECT COUNT(*), COUNT(*) FILTER (WHERE user_id = ?) "
            "FROM shadow_merchant_winners WHERE event_id = ?",
            (user_id, event_id),
        ) as c:
            row = await c.fetchone()
        taken, already = int(row[0] or 0), int(row[1] or 0)
        if already or taken >= max_winners:
            return None
        position = taken + 1
        reward = float(reward_by_position.get(position, 0))
        await db.execute(
            "INSERT INTO shadow_merchant_winners (event_id, user_id, position, reward) "
            "VALUES (?, ?, ?, ?)",
            (event_id, user_id, position, reward),
        )
        if position >= max_winners:
            await db.execute(
                "UPDATE shadow_merchant_events SET status = 'done' WHERE id = ?", (event_id,)
            )
    return position, reward


# ── Ваучеры и Теневые реликвии ────────────────────────────────────────────────

async def voucher_count(db: PGAdapter, user_id: int) -> int:
    """Непогашенные победы = право купить столько Теневых реликвий."""
    async with db.execute(
        "SELECT COUNT(*) FROM shadow_merchant_winners "
        "WHERE user_id = ? AND COALESCE(redeemed, FALSE) = FALSE",
        (user_id,),
    ) as c:
        r = await c.fetchone()
    return int(r[0] or 0)


async def owned_shadow_relics(db: PGAdapter, user_id: int) -> list[str]:
    async with db.execute(
        "SELECT relic_id FROM user_shadow_relics WHERE user_id = ?", (user_id,)
    ) as c:
        rows = await c.fetchall()
    return [r[0] for r in rows]


async def get_gates_dark_bonus(db: PGAdapter, user_id: int) -> float:
    """Compatibility surface: archive relics no longer modify any reward."""
    del db, user_id
    return 0.0


async def buy_shadow_relic(
    db: PGAdapter, user_id: int, relic_id: str, *, idempotency_key: str,
) -> tuple[bool, str]:
    """Покупка Теневой реликвии: 1 непогашенный ваучер + цена в 🌑 (атомарно)."""
    relic = SHADOW_RELICS.get(relic_id)
    if not relic:
        return False, "Нет такой реликвии."
    price = float(relic["price_dark"])
    try:
        async with db.connection.transaction():
            delta = {"dark_mora": -price}
            replay = await find_balance_replay(
                db, user_id, delta,
                reason_code="shadow_relic", idempotency_key=idempotency_key,
                source_type="legacy_archive", reference_type="shadow_relic",
                reference_id=relic_id,
            )
            if replay:
                return True, f"{relic['name']} — уже в архиве; повторного списания нет."
            # уже владеет?
            async with db.execute(
                "SELECT 1 FROM user_shadow_relics WHERE user_id = ? AND relic_id = ?",
                (user_id, relic_id),
            ) as c:
                if await c.fetchone():
                    raise ValueError("Эта реликвия уже в вашей коллекции.")
            # лочим один непогашенный ваучер
            async with db.execute(
                "SELECT event_id FROM shadow_merchant_winners "
                "WHERE user_id = ? AND COALESCE(redeemed, FALSE) = FALSE "
                "ORDER BY won_at LIMIT 1 FOR UPDATE",
                (user_id,),
            ) as c:
                voucher = await c.fetchone()
            if not voucher:
                raise ValueError(
                    "Нужна победа в ивенте «Теневой Торговец» — право покупки даёт только она."
                )
            await apply_balance_change(
                db, user_id, delta,
                reason_code="shadow_relic", idempotency_key=idempotency_key,
                source_type="legacy_archive", reference_type="shadow_relic",
                reference_id=relic_id,
                metadata={"relic_id": relic_id, "archive_only": True, "no_power": True},
                note=relic_id,
            )
            await db.execute(
                "UPDATE shadow_merchant_winners SET redeemed = TRUE "
                "WHERE user_id = ? AND event_id = ?",
                (user_id, voucher[0]),
            )
            await db.execute(
                "INSERT INTO user_shadow_relics (user_id, relic_id) VALUES (?, ?)",
                (user_id, relic_id),
            )
    except ValueError as e:
        return False, str(e)
    except InsufficientBalance:
        return False, f"Недостаточно Тёмной Моры: нужно {price:.0f} 🌑."
    except IdempotencyConflict:
        return False, "Этот запрос уже использован для другой покупки."
    return True, f"{relic['name']} — ваша! Списано {price:.0f} 🌑, ваучер погашен."
