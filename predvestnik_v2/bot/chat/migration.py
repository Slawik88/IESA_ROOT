"""Группа стала супергруппой: Telegram выдаёт ей новый ID, и всё, что бот знал про старый, надо перенести."""
from __future__ import annotations

from aiogram.types import Message
from asyncpg.exceptions import UniqueViolationError
from loguru import logger

# (таблица, колонка с ID чата): настройки, ранги, статистика, санкции, браки. История начислений не переносится.
STATE_TABLES = (
    ("chat_settings", "chat_id"),
    ("user_chat_stats", "chat_tg_id"),
    ("daily_user_stats", "chat_id"),
    ("chat_rank_rights", "chat_id"),
    ("chat_blacklist", "chat_id"),
    ("user_warnings", "chat_id"),
    ("moderation_logs", "chat_id"),
    ("bot_feature_switches", "chat_id"),
    ("marriages", "chat_id"),
    ("daily_login", "chat_id"),
    ("daily_quests", "chat_id"),
    ("chat_onboarding", "chat_id"),
    ("member_tag_history", "chat_id"),
)


async def _move(db, table: str, column: str, old: int, new: int) -> int:
    async with db.execute(f"UPDATE {table} SET {column} = ? WHERE {column} = ? RETURNING 1", (new, old)) as cur:
        return len(await cur.fetchall())


async def migrate_chat(db, old: int, new: int) -> dict[str, int]:
    """Перенести данные старого чата на новый ID. Что успели записать в новом чате до переноса (первые сообщения),
    уступает старым данным. Одна таблица не удалась — остальные переносятся. Возвращает {таблица: строк}."""
    moved: dict[str, int] = {}
    if not old or not new or old == new:
        return moved
    for table, column in STATE_TABLES:
        try:
            async with db.connection.transaction():
                try:
                    async with db.connection.transaction():   # свой savepoint: после ошибки уникальности внешний продолжает работу
                        count = await _move(db, table, column, old, new)
                except UniqueViolationError:
                    await db.execute(f"DELETE FROM {table} WHERE {column} = ?", (new,))
                    count = await _move(db, table, column, old, new)
            if count:
                moved[table] = count
        except Exception as exc:  # noqa: BLE001 - остальные таблицы всё равно переносим
            logger.warning(f"chat migration {old} -> {new}: {table} not moved: {exc}")
    return moved


async def on_migrated(message: Message, bot, db) -> None:
    """Служебное сообщение «группа стала супергруппой» (приходит в старый чат). Подключено в bot.chat раньше общего обработчика."""
    old, new = int(message.chat.id), int(message.migrate_to_chat_id)
    moved = await migrate_chat(db, old, new)
    try:
        await db.commit()
    except Exception:  # noqa: BLE001 - соединение могло уже работать в автокоммите
        pass
    logger.info(f"chat {old} became supergroup {new}: moved {moved}")
    if moved:
        try:
            await bot.send_message(new, "🔁 Группа стала супергруппой. Настройки, ранги, статистика и санкции перенесены.")
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"migration notice not sent: {exc}")
