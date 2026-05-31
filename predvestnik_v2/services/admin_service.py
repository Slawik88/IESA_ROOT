from infrastructure.repositories import economy
from infrastructure.repositories import chat as chat_repo
from core.registry import ITEMS_REGISTRY


async def give_resource(db, user_id: int, chat_id: int, r_type: str, amount: int, item_id: str = None):
    if r_type == "mora":
        await economy.add_balance(db, user_id, float(amount), 0)
        return True, f"Добавлено {amount} 🪙"

    elif r_type == "diamond":
        await economy.add_balance(db, user_id, 0, float(amount))
        return True, f"Добавлено {amount} 💎"

    elif r_type == "xp":
        await chat_repo.add_xp(db, user_id, chat_id, amount)
        return True, f"Добавлено {amount} XP"

    elif r_type == "item":
        if not item_id or item_id not in ITEMS_REGISTRY:
            return False, f"Предмет {item_id} не найден"
        await economy.add_item(db, user_id, item_id, amount)
        return True, f"Выдано {amount} шт. {ITEMS_REGISTRY[item_id]['name']}"

    return False, "Неизвестный тип для выдачи"


async def set_resource(db, user_id: int, chat_id: int, r_type: str, value: int):
    if r_type == "mora":
        curr = await economy.get_balance(db, user_id)
        await economy.set_balance(db, user_id, float(value), curr['user_balance_diamonds'])
        return True, f"Мора установлена в {value}"

    elif r_type == "diamond":
        curr = await economy.get_balance(db, user_id)
        await economy.set_balance(db, user_id, curr['user_balance_mora'], float(value))
        return True, f"Алмазы установлены в {value}"

    elif r_type == "lvl":
        await db.execute(
            "UPDATE user_chat_stats SET user_level = ?, user_xp = 0 WHERE user_tg_id = ? AND chat_tg_id = ?",
            (value, user_id, chat_id)
        )
        await db.commit()
        return True, f"Установлен {value} уровень"

    elif r_type == "xp":
        await db.execute(
            "UPDATE user_chat_stats SET user_xp = ? WHERE user_tg_id = ? AND chat_tg_id = ?",
            (value, user_id, chat_id)
        )
        await db.commit()
        return True, f"Опыт установлен в {value}"

    return False, "Неизвестный тип для установки"
