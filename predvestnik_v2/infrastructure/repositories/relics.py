"""Archive relic ownership and spend-only settlement.

Relics keep collection history but no longer multiply gameplay rewards.
"""
from core.registry import RELICS
from core.economy_contract import IdempotencyConflict, InsufficientBalance
from infrastructure.repositories.economy_ledger import apply_balance_change, find_balance_replay

# колонка баланса для каждой валюты цены (whitelisted)
_PRICE_COLS = {
    "mora": "user_balance_mora",
    "diamonds": "user_balance_diamonds",
    "dark_mora": "user_balance_dark_mora",
}
_PRICE_ICON = {"mora": "🪙", "diamonds": "💎", "dark_mora": "🌑"}


def price_str(price: dict) -> str:
    return " + ".join(f"{int(v)} {_PRICE_ICON.get(k, k)}" for k, v in price.items())


async def list_owned(db, user_id: int) -> set[str]:
    async with db.execute(
        "SELECT relic_id FROM user_relics WHERE user_id = ?", (user_id,)
    ) as c:
        return {r[0] for r in await c.fetchall()}


async def get_expedition_mora_bonus(db, user_id: int) -> float:
    """Legacy compatibility: archive relics no longer modify gameplay income."""
    return 0.0


async def buy_relic(
    db, user_id: int, relic_id: str, *, idempotency_key: str | None = None,
) -> tuple[bool, str]:
    """Купить архивную реликвию за старую Тёмную Мору ровно один раз."""
    relic = RELICS.get(relic_id)
    if not relic:
        return False, "Неизвестная реликвия."
    price = float(relic["price"].get("dark_mora", 0))
    if price <= 0 or not idempotency_key:
        return False, "Не удалось подтвердить покупку. Обновите страницу и повторите."
    delta = {"dark_mora": -price}
    try:
        async with db.connection.transaction():
            await db.execute(
                "INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (user_id,)
            )
            replay = await find_balance_replay(
                db, user_id, delta, reason_code="shadow_relic",
                idempotency_key=idempotency_key, source_type="legacy_archive",
                reference_type="relic", reference_id=relic_id,
            )
            if replay:
                return True, "Эта покупка уже была обработана."
            async with db.execute(
                "SELECT 1 FROM user_relics WHERE user_id = ? AND relic_id = ?",
                (user_id, relic_id),
            ) as c:
                if await c.fetchone():
                    return False, "Эта реликвия уже в вашей коллекции."

            await apply_balance_change(
                db, user_id, delta, reason_code="shadow_relic",
                idempotency_key=idempotency_key, source_type="legacy_archive",
                reference_type="relic", reference_id=relic_id,
                metadata={"relic_id": relic_id, "archive_only": True},
                note=relic_id,
            )
            await db.execute(
                "INSERT INTO user_relics (user_id, relic_id) VALUES (?, ?)",
                (user_id, relic_id),
            )
        return True, f"🏛 Реликвия получена: {relic['name']}!"
    except InsufficientBalance:
        return False, f"Недостаточно Тёмной Моры: нужно {price:.0f} 🌑."
    except IdempotencyConflict:
        return False, "Этот ключ запроса уже использован для другой покупки."
    except Exception:
        return False, "Покупка не выполнена. Баланс и коллекция не изменены."
