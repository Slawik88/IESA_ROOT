"""
api/checkin.py — daily check-in operations.

All functions are async; the mini app wraps them with async_to_sync.
"""


async def get_checkin_status(uid: int, chat_id: int) -> dict:
    """Return current check-in status for uid in chat.  No side effects.

    Returns {streak, total_days, last_checkin, checkpoint, today_done}.
    """
    from database.db import get_daily_checkin
    from datetime import datetime, timezone

    data = await get_daily_checkin(uid, chat_id)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    return {
        "streak":       data["streak"],
        "total_days":   data["total_days"],
        "last_checkin": data["last_checkin"],
        "checkpoint":   data["checkpoint"],
        "today_done":   data["last_checkin"] == today,
    }


async def do_checkin(uid: int, chat_id: int) -> dict:
    """Perform the daily check-in and credit the mora reward.

    Calls perform_checkin() to update the daily_checkin row, then
    calls add_mora() to credit the reward — matching the handler behaviour.

    Returns {already_done, streak, total_days} if the user already checked in
    today, otherwise {ok, already_done, mora, streak, total_days,
    is_checkpoint, free_gacha}.
    """
    from database.db import perform_checkin, add_mora

    result = await perform_checkin(uid, chat_id)
    if result.get("already_done"):
        return result

    await add_mora(uid, chat_id, result["mora"])
    return result
