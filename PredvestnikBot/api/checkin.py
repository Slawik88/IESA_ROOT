import logging
_log = logging.getLogger(__name__)
"""
api/checkin.py — daily check-in operations.

All functions are async; the mini app wraps them with async_to_sync.
"""


async def get_checkin_status(uid: int, chat_id: int) -> dict:
    """Return current check-in status for uid in chat.  No side effects.

    Returns {streak, total_days, last_checkin, checkpoint, today_done}.
    """
    from database.db import get_daily_checkin
    from utils.helpers import bot_today

    data = await get_daily_checkin(uid, chat_id)
    today = bot_today()

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
    from database.db import perform_checkin, add_mora, is_isolated_chat_db

    # Block checkin in isolated (admin / test) chats
    if chat_id and await is_isolated_chat_db(chat_id):
        return {"ok": False, "error": "isolated_chat", "already_done": False}

    result = await perform_checkin(uid, chat_id)
    if result.get("already_done"):
        return result

    mora = result["mora"]

    # Talent: checkin_mora_bonus — extra mora per talent level
    try:
        from database.db import get_talent_effect as _gte
        _checkin_bonus = await _gte(uid, "checkin_mora_bonus")
        if _checkin_bonus > 0:
            mora += _checkin_bonus
            result["mora"] = mora
    except Exception as _e:
        _log.debug("checkin_mora_bonus: %s", _e)

    # VIP bonus: +15% to checkin reward
    try:
        from database.db import get_vip
        if await get_vip(uid, chat_id):
            mora = int(mora * 1.15)
            result["mora"] = mora
            result["vip_bonus"] = True
    except Exception as _e:
        _log.debug("%s", _e)
    await add_mora(uid, chat_id, mora)

    # Log to wallet ledger
    try:
        from api.economy import log_wallet_tx
        streak = result.get("streak", 1)
        await log_wallet_tx(uid, chat_id, "income", mora, "checkin",
                            f"Стрик {streak} {'день' if streak == 1 else 'дней'}")
    except Exception as _e:
        _log.debug("%s", _e)
    # Check streak achievements (fire-and-forget)
    try:
        from api.achievements import check_and_award as _ach
        await _ach(uid, chat_id, "checkin_streak", result.get("streak", 1))
    except Exception as _e:
        _log.debug("%s", _e)

    return result
