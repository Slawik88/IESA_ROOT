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
    bot_id: int = 0,
) -> tuple[bool, str]:
    """Check that user has at least min_rank (no target comparison)."""
    if developer_id and user_id == developer_id:
        return True, ""
    user_stats = await get_chat_stats(db, user_id, chat_id)
    if user_stats.get("local_rank", 0) < min_rank:
        return False, "❌ <b>Ошибка:</b> У вас недостаточно прав для этого действия."
    return True, ""

async def chat_sanctions_map(db, chat_id: int, user_ids: list[int]) -> dict[int, dict]:
    """Статусы модерации участников чата ОДНИМ проходом — для списков участников
    в админке сайта и dev-консоли («Сайт == бот»: бот-команды бан/кик пишут те же
    moderation_logs, глобальный ЧС — global_sanctions).

    banned     — активный бан чата (разбан удаляет строку — см. remove_ban_log);
    kicked     — кикали (история: после кика можно вернуться);
    global_ban — активный глобальный бан бота."""
    out: dict[int, dict] = {
        int(u): {"banned": False, "kicked": False, "global_ban": False}
        for u in user_ids
    }
    if not out:
        return out
    ids = list(out)
    ph = ",".join(["?"] * len(ids))
    async with db.execute(
        "SELECT user_id, action FROM moderation_logs "
        f"WHERE chat_id = ? AND action IN ('ban','kick') AND user_id IN ({ph})",
        [chat_id, *ids],
    ) as c:
        for r in await c.fetchall():
            key = "banned" if r["action"] == "ban" else "kicked"
            out[int(r["user_id"])][key] = True
    async with db.execute(
        "SELECT DISTINCT target_id FROM global_sanctions "
        "WHERE target_type = 'user' AND sanction_type = 'ban' AND revoked_at IS NULL "
        f"AND (expires_at IS NULL OR expires_at > NOW()) AND target_id IN ({ph})",
        ids,
    ) as c:
        for r in await c.fetchall():
            out[int(r[0])]["global_ban"] = True
    return out
