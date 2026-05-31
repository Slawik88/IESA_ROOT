# services/marriage.py
# Business rules for marriage proposals. No platform dependencies.
import aiosqlite

from infrastructure.repositories.marriages import get_user_marriage


async def check_marriage_proposal(
    db: aiosqlite.Connection,
    chat_id: int,
    initiator_id: int,
    target_id: int,
    is_target_bot: bool,
) -> tuple[bool, str]:
    """Return (allowed, error_message)."""
    if initiator_id == target_id:
        return False, "🤡 <b>Ошибка:</b> Нельзя заключить брак с самим собой!"
    if is_target_bot:
        return False, "🤖 <b>Ошибка:</b> Боты созданы для работы, а не для любви."
    if await get_user_marriage(db, chat_id, initiator_id):
        return False, "💔 <b>Ошибка:</b> Вы уже состоите в браке в этом чате!"
    if await get_user_marriage(db, chat_id, target_id):
        return False, "💔 <b>Ошибка:</b> Этот пользователь уже состоит в браке!"
    return True, ""
