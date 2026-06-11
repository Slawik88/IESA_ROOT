# services/economy.py
# Platform-agnostic economy engine.
# This service is the single place that owns discount logic, price calculation,
# and purchase orchestration. It knows nothing about Telegram or Django.
import aiosqlite

from core.constants import TURTLE_BONUSES
from core.registry import ITEMS_REGISTRY
from infrastructure.repositories.economy import buy_item as _repo_buy_item


async def _get_turtle_shop_discount(db: aiosqlite.Connection, user_id: int) -> float:
    """Returns the shop discount fraction (0.0..1.0) from the user's active/passive turtle.
    0.0 if no turtle in nursery or it's exhausted."""
    async with db.execute(
        "SELECT COALESCE(pet_level, 1) FROM pets "
        "WHERE owner_id = ? AND placement IN ('active', 'passive') "
        "AND species_id = 'turtle' AND fatigue < 100 LIMIT 1",
        (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        return 0.0
    return TURTLE_BONUSES.get(max(1, min(10, row[0])), {}).get("shop_discount", 0.0)


class EconomyService:
    """All economy operations for a single database connection."""

    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    # ── Discount ──────────────────────────────────────────────────────────────

    async def has_turtle_discount(self, user_id: int) -> bool:
        """Legacy flag: True if turtle gives any discount. Kept for callers
        that still rely on the bool return."""
        return await _get_turtle_shop_discount(self._db, user_id) > 0.0

    async def get_turtle_discount(self, user_id: int) -> float:
        """Preferred accessor — returns the discount fraction directly."""
        return await _get_turtle_shop_discount(self._db, user_id)

    def apply_discount(self, price: int | float, has_discount: bool) -> int:
        """Return final integer price after applying turtle discount if applicable.
        For legacy callers using the boolean flag, defaults to the Lv5 value (5% off)
        to preserve behaviour; new callers should use get_turtle_discount + multiply manually."""
        if not has_discount:
            return int(price)
        return int(price * (1.0 - TURTLE_BONUSES[5]["shop_discount"]))

    def apply_discount_fraction(self, price: int | float, discount: float) -> int:
        """New API: explicit discount fraction."""
        return int(price * (1.0 - discount))

    # ── Pricing ───────────────────────────────────────────────────────────────

    async def get_item_prices(
        self, item_id: str, user_id: int, *, has_discount: bool | None = None
    ) -> dict:
        """
        Return final prices for an item for a given user.

        Pass has_discount=True/False to reuse a value already fetched (avoids
        an extra DB round-trip when rendering a full shop listing).
        """
        item = ITEMS_REGISTRY.get(item_id)
        if not item:
            return {"mora": 0, "diamonds": 0, "discount_active": False}

        if has_discount is None:
            has_discount = await self.has_turtle_discount(user_id)

        return {
            "mora": self.apply_discount(item.get("price_mora", 0), has_discount),
            "diamonds": self.apply_discount(item.get("price_diamonds", 0), has_discount),
            "discount_active": has_discount,
        }

    # ── Purchase ──────────────────────────────────────────────────────────────

    async def purchase_item(
        self, user_id: int, item_id: str, quantity: int = 1
    ) -> tuple[bool, str]:
        """
        Complete purchase flow: resolve discount → check balance → deduct → add to inventory.
        Returns (success, message).
        """
        item = ITEMS_REGISTRY.get(item_id)
        if not item:
            return False, "Предмет не найден."

        has_discount = await self.has_turtle_discount(user_id)
        mora_unit = self.apply_discount(item.get("price_mora", 0), has_discount)
        dia_unit = self.apply_discount(item.get("price_diamonds", 0), has_discount)
        zar_unit = item.get("price_zarniki", 0)

        if mora_unit <= 0 and dia_unit <= 0 and zar_unit <= 0:
            return False, "Этот предмет нельзя купить."

        return await _repo_buy_item(
            self._db, user_id, item_id, mora_unit, dia_unit, quantity, p_zarniki=zar_unit
        )
