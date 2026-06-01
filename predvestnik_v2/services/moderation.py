# services/moderation.py
# Platform-agnostic moderation permission checks.
# developer_id is passed as a parameter so this module has zero config imports.
import aiosqlite

from infrastructure.repositories.chat import get_chat_stats


async def check_mod_rights(
    db: aiosqlite.Connection,
    chat_id: int,
    admin_id: int,
    target_id: int,
    min_rank: int = 1,
    developer_id: int = 0,
    bot_id: int = 0,
) -> tuple[bool, str]:
    """Return (allowed, error_message). Empty string means allowed."""
    if admin_id == target_id:
        return False, "🤡 <b>Ошибка:</b> Нельзя применить это к самому себе."
    if developer_id and target_id == developer_id:
        return False, "🛡 <b>Ошибка:</b> На этого пользователя не действуют законы смертных."
    if bot_id and target_id == bot_id:
        return False, "🤖 <b>Ошибка:</b> Нельзя применять меры воздействия к боту."

    admin_stats = await get_chat_stats(db, admin_id, chat_id)
    target_stats = await get_chat_stats(db, target_id, chat_id)
    admin_rank = admin_stats.get("local_rank", 0)
    target_rank = target_stats.get("local_rank", 0)

    if not (developer_id and admin_id == developer_id):
        if admin_rank < min_rank:
            return False, "❌ <b>Ошибка:</b> Недостаточно прав для этого действия."
        if target_rank >= admin_rank:
            return False, "⚠️ <b>Ошибка:</b> Вы не можете наказать того, чей ранг равен вашему или выше."

    return True, ""


async def check_admin_rights(
    db: aiosqlite.Connection,
    chat_id: int,
    user_id: int,
    min_rank: int = 1,
    developer_id: int = 0,
) -> tuple[bool, str]:
    """Check that user has at least min_rank (no target comparison)."""
    if developer_id and user_id == developer_id:
        return True, ""
    user_stats = await get_chat_stats(db, user_id, chat_id)
    if user_stats.get("local_rank", 0) < min_rank:
        return False, "❌ <b>Ошибка:</b> У вас недостаточно прав для этого действия."
    return True, ""