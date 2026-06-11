"""services/inventory_resolve.py — единая резолюция legacy numeric item_id.

Старый баг: в таблицу inventory мог попасть числовой item_id (хэш Python,
нестабильный между процессами) вместо настоящего ID предмета. Реальный
item_id восстанавливается через auction_lots.item_name = "Название||real_item_id".
Используется и ботом, и сайтом — единая логика парсинга и самовосстановления.
No bot/FastAPI imports.
"""
from core.registry import ITEMS_REGISTRY


async def resolve_item_id(db, raw_id: str) -> str:
    """Вернуть настоящий item_id. Если raw_id уже валиден или резолюция не
    удалась — вернуть raw_id без изменений."""
    raw_id = str(raw_id)
    if raw_id in ITEMS_REGISTRY or not raw_id.isdigit():
        return raw_id
    try:
        async with db.execute(
            "SELECT item_name FROM auction_lots "
            "WHERE item_id_or_pet_id = ? AND item_type = 'inventory' LIMIT 1",
            (int(raw_id),),
        ) as c:
            row = await c.fetchone()
        if row and row[0]:
            parts = row[0].split("||", 1)
            if len(parts) > 1:
                real = parts[1].strip()
                if real in ITEMS_REGISTRY:
                    return real
    except Exception:
        pass
    return raw_id


async def resolve_and_migrate_item_id(db, user_id: int, raw_id: str) -> str:
    """resolve_item_id + перенос строки inventory на настоящий item_id (self-heal).
    Коммитит только если была выполнена миграция."""
    raw_id = str(raw_id)
    real_id = await resolve_item_id(db, raw_id)
    if real_id != raw_id:
        try:
            await db.execute(
                "INSERT INTO inventory (user_id, item_id, quantity) "
                "SELECT user_id, ?, quantity FROM inventory WHERE user_id = ? AND item_id = ? "
                "ON CONFLICT (user_id, item_id) DO UPDATE SET quantity = inventory.quantity + EXCLUDED.quantity",
                (real_id, user_id, raw_id),
            )
            await db.execute(
                "DELETE FROM inventory WHERE user_id = ? AND item_id = ?",
                (user_id, raw_id),
            )
            await db.commit()
        except Exception:
            pass
    return real_id


def item_display_name(item_id: str) -> str:
    """Имя предмета для вывода; фоллбек для нераспознанных legacy ID."""
    return ITEMS_REGISTRY.get(str(item_id), {}).get("name", f"❓ Предмет #{item_id}")
