"""Read-only inactivity within one group, independent of Telegram delivery."""
from core.chat_inactivity import DAY_SECONDS, MAX_DAYS, MAX_PAGE, InactivePage
from infrastructure.repositories import stats
from services import chat_bots


async def list_inactive(db, chat_id: int, seconds: int, page: int = 0, *,
                        bot_id: int, timezone_seconds: int = 0) -> InactivePage:
    if chat_id >= 0 or not DAY_SECONDS <= seconds <= MAX_DAYS * DAY_SECONDS:
        raise ValueError("invalid inactivity scope or period")
    excluded = sorted(chat_bots.SERVICE_IDS | {int(bot_id)})
    return await stats.get_inactive_users(db, int(chat_id), int(seconds),
                                         max(0, min(int(page), MAX_PAGE)),
                                         excluded_ids=excluded, timezone_seconds=timezone_seconds)
