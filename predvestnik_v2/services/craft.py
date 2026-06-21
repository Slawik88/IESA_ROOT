"""
services/craft.py
Crafting business logic. No bot.* imports.
"""
from core.registry import CRAFT_RECIPES, ITEMS_REGISTRY
from infrastructure.repositories.economy import get_item_quantity, add_item, remove_item


async def get_craftable_list(db, user_id: int) -> list[dict]:
    """Return all recipes annotated with current ingredient counts and craftable qty."""
    result = []
    for recipe_id, recipe in CRAFT_RECIPES.items():
        ingredients_status = []
        can_craft_times = None  # how many times user can craft this right now

        for item_id, needed in recipe["ingredients"]:
            have = await get_item_quantity(db, user_id, item_id)
            item_name = ITEMS_REGISTRY.get(item_id, {}).get("name", item_id)
            ingredients_status.append({
                "item_id": item_id,
                "item_name": item_name,
                "needed": needed,
                "have": have,
                "ok": have >= needed,
            })
            times = have // needed
            can_craft_times = times if can_craft_times is None else min(can_craft_times, times)

        result.append({
            **recipe,
            "recipe_id": recipe_id,
            "ingredients_status": ingredients_status,
            "can_craft": (can_craft_times or 0) > 0,
            "can_craft_times": can_craft_times or 0,
        })

    return result


async def craft(db, user_id: int, recipe_id: str) -> dict:
    """
    Execute one craft. Returns:
      {"ok": True, "name": str, "qty": int}
      {"ok": False, "reason": str}
    No commit — caller must commit.
    """
    recipe = CRAFT_RECIPES.get(recipe_id)
    if not recipe:
        return {"ok": False, "reason": "Рецепт не найден."}

    # Check all ingredients first
    for item_id, needed in recipe["ingredients"]:
        have = await get_item_quantity(db, user_id, item_id)
        item_name = ITEMS_REGISTRY.get(item_id, {}).get("name", item_id)
        if have < needed:
            return {
                "ok": False,
                "reason": f"Недостаточно {item_name}: нужно {needed}, есть {have}.",
            }

    # M8: списание ингредиентов + выдача результата — атомарно. Раньше при
    # нехватке 2-го ингредиента (параллельный крафт) 1-й уже был безвозвратно
    # списан. Теперь нехватка вызывает rollback всей операции.
    class _Insufficient(Exception):
        pass
    try:
        async with db.connection.transaction():
            for item_id, needed in recipe["ingredients"]:
                if not await remove_item(db, user_id, item_id, needed, commit=False):
                    raise _Insufficient()
            await add_item(db, user_id, recipe["result_item"], recipe["result_qty"])
    except _Insufficient:
        return {"ok": False, "reason": "Ошибка списания ингредиентов. Попробуй ещё раз."}

    return {
        "ok": True,
        "name": recipe["name"],
        "qty": recipe["result_qty"],
        "recipe_id": recipe_id,
    }
