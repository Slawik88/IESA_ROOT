# services/economy.py
# Platform-agnostic economy engine.
# This service is the single place that owns discount logic, price calculation,
# and purchase orchestration. It knows nothing about Telegram or Django.
import aiosqlite

from core.registry import ITEMS_REGISTRY
from infrastructure.repositories.economy import buy_item as _repo_buy_item
from infrastructure.repositories.zoo import get_species_bonus


async def _get_turtle_bonus(db: aiosqlite.Connection, user_id: int) -> dict:
    """Полный бонус Черепахи (уровень + слот active/passive×0.5, «Блок 12») — {} если
    активной/пассивной некормлённой Черепахи нет. Общий источник для скидки магазина
    и гачи — раньше скидка магазина читала уровень напрямую из БД и схлопывала его в
    bool (всегда Lv5 = П2 BOT_AUDIT.md), без учёта слота (П4); теперь оба фикса решены
    переиспользованием того же аксессора, которым пользуются экспедиции/квесты/зоопарк."""
    return await get_species_bonus(db, user_id, "turtle")


class EconomyService:
    """All economy operations for a single database connection."""

    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    # ── Discount ──────────────────────────────────────────────────────────────

    async def get_turtle_discount(self, user_id: int) -> float:
        """Скидка магазина (доля 0..1) — уровень+слот-корректная."""
        return (await _get_turtle_bonus(self._db, user_id)).get("shop_discount", 0.0)

    async def get_turtle_gacha_discount(self, user_id: int) -> float:
        """Скидка на крутку гачи (доля 0..1) — Черепаха Lv8+ (П3 BOT_AUDIT.md)."""
        return (await _get_turtle_bonus(self._db, user_id)).get("gacha_daily_discount", 0.0)

    def apply_discount_fraction(self, price: int | float, discount: float) -> int:
        """Явная доля скидки (0.0..1.0) → итоговая цена."""
        return int(price * (1.0 - discount))

    # ── Pricing ───────────────────────────────────────────────────────────────

    async def get_item_prices(
        self, item_id: str, user_id: int, *, discount: float | None = None
    ) -> dict:
        """
        Return final prices for an item for a given user.

        Pass discount=<fraction> to reuse a value already fetched (avoids
        an extra DB round-trip when rendering a full shop listing).
        """
        item = ITEMS_REGISTRY.get(item_id)
        if not item:
            return {"mora": 0, "diamonds": 0, "discount_active": False}

        if discount is None:
            discount = await self.get_turtle_discount(user_id)

        return {
            "mora": self.apply_discount_fraction(item.get("price_mora", 0), discount),
            "diamonds": self.apply_discount_fraction(item.get("price_diamonds", 0), discount),
            "discount_active": discount > 0,
        }

    # ── Purchase ──────────────────────────────────────────────────────────────

    async def purchase_item(
        self, user_id: int, item_id: str, quantity: int = 1,
        idempotency_key: str | None = None,
    ) -> tuple[bool, str]:
        """
        Complete purchase flow: resolve discount → check balance → deduct → add to inventory.
        Автодоплаты валютой здесь нет: покупка использует только опубликованную цену.
        Returns (success, message).
        """
        item = ITEMS_REGISTRY.get(item_id)
        if not item:
            return False, "Предмет не найден."

        discount = await self.get_turtle_discount(user_id)
        mora_unit = self.apply_discount_fraction(item.get("price_mora", 0), discount)
        dia_unit = self.apply_discount_fraction(item.get("price_diamonds", 0), discount)
        zar_unit = item.get("price_zarniki", 0)

        if mora_unit <= 0 and dia_unit <= 0 and zar_unit <= 0:
            return False, "Этот предмет нельзя купить."

        return await _repo_buy_item(
            self._db, user_id, item_id, mora_unit, dia_unit, quantity,
            p_zarniki=zar_unit, idempotency_key=idempotency_key,
        )
