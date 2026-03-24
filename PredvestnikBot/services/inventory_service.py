"""
Inventory service — handles item equipping.

Two equip systems co-exist:
  * Legendary display equip  — sets gacha_display on user profile (gacha.py bot handler).
  * RPG slot equip           — places item in weapon/armor/artifact slot (Mini App).

Usage:
    # Bot command (legendary display):
    from services.inventory_service import equip_legendary
    await equip_legendary(user_id, chat_id, item_id)

    # Mini App endpoint (RPG slot):
    from services.inventory_service import equip_rpg_slot
    item_name = await equip_rpg_slot(user_id, chat_id, item_id, slot)
"""
from database.db import equip_gacha_item, equip_item
from .exceptions import ItemNotFoundError


async def equip_legendary(user_id: int, chat_id: int, item_id: int) -> None:
    """Equip a legendary gacha item for profile display.

    Raises
    ------
    ItemNotFoundError  If the item doesn't exist, doesn't belong to the user,
                       or isn't legendary rarity.
    """
    ok = await equip_gacha_item(user_id, chat_id, item_id)
    if not ok:
        raise ItemNotFoundError("Предмет не найден, не принадлежит тебе или не является легендарным")


async def equip_rpg_slot(user_id: int, chat_id: int, item_id: int, slot: str) -> str:
    """Equip a gacha item into an RPG slot (weapon / armor / artifact).

    Parameters
    ----------
    slot : One of ``"weapon"``, ``"armor"``, ``"artifact"``.

    Returns
    -------
    str  The equipped item's name (for confirmation messages).

    Raises
    ------
    ValueError         If *slot* is not one of the three valid values.
    ItemNotFoundError  If the item doesn't exist or doesn't belong to the user.
    """
    if slot not in ("weapon", "armor", "artifact"):
        raise ValueError(f"Invalid slot '{slot}'. Must be weapon/armor/artifact.")
    item_name = await equip_item(user_id, chat_id, item_id, slot)
    if item_name is None:
        raise ItemNotFoundError("Предмет не найден или не принадлежит тебе")
    return item_name
