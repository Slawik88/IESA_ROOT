# services/leveling.py
import aiosqlite
from datetime import datetime, timedelta, timezone

from core.constants import (
    XP_PER_MESSAGE, XP_PER_LEVEL, MORA_PER_LEVEL, DIAMONDS_PER_LEVEL,
    get_pet_bonus,
)
from infrastructure.repositories import chat as chat_repo
from infrastructure.repositories import economy as eco_repo
from infrastructure.repositories import zoo as zoo_repo


def calculate_level(xp: int) -> int:
    return (xp // XP_PER_LEVEL) + 1


def _is_weekend_in_tz(timezone_offset: str) -> bool:
    """Returns True if 'now' is Saturday or Sunday in the chat's timezone.
    Parses '+3 hours' / '-5 hours' style strings."""
    try:
        parts = timezone_offset.strip().split()
        hours = int(parts[0])
    except (ValueError, IndexError):
        hours = 0
    now = datetime.now(timezone.utc) + timedelta(hours=hours)
    return now.weekday() >= 5


async def process_message_xp(
    db: aiosqlite.Connection,
    user_id: int,
    chat_id: int,
    timezone_offset: str = "+3 hours",
) -> tuple[bool, int]:
    """Award XP for a single message. Apply owl bonus if applicable.

    The owl bonus depends on the owl's level (trigger_every_n_msg, bonus_xp, weekend_double).
    Counter for the every-N-th message is the user's accumulated message count.
    """
    stats = await chat_repo.increment_stats_and_get_xp(db, user_id, chat_id, timezone_offset)

    new_xp = stats["user_xp"]
    old_xp = new_xp - XP_PER_MESSAGE
    msg_count = stats.get("user_messages_count_all_time", 0)

    # study_notes: +50% XP if buff active
    try:
        async with db.execute(
            "SELECT expires_at, value FROM player_buffs "
            "WHERE user_id = ? AND buff_type = 'study_xp' AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)",
            (user_id,),
        ) as _sb:
            _sbrow = await _sb.fetchone()
        if _sbrow:
            study_bonus = int(round(XP_PER_MESSAGE * float(_sbrow["value"] or 0.5)))
            if study_bonus > 0:
                await chat_repo.add_xp(db, user_id, chat_id, study_bonus)
                new_xp += study_bonus
    except Exception:
        pass

    # Block 12: бонус Совы масштабируется по слоту (passive → bonus_xp ×0.5,
    # weekend_double off; trigger_every_n_msg структурное — не масштабируется)
    owl = await zoo_repo.get_species_bonus(db, user_id, "owl")
    if owl:
        every_n = owl.get("trigger_every_n_msg", 1)
        if every_n > 0 and msg_count % every_n == 0:
            bonus = owl.get("bonus_xp", 0.0)
            if owl.get("weekend_double") and _is_weekend_in_tz(timezone_offset):
                bonus *= 2.0
            bonus_int = int(round(bonus))
            if bonus_int > 0:
                await chat_repo.add_xp(db, user_id, chat_id, bonus_int)
                new_xp += bonus_int

    old_lvl = calculate_level(old_xp)
    new_lvl = calculate_level(new_xp)

    if new_lvl > old_lvl:
        await chat_repo.update_level(db, user_id, chat_id, new_lvl)
        await eco_repo.add_balance(db, user_id, mora=MORA_PER_LEVEL, diamonds=DIAMONDS_PER_LEVEL)
        return True, new_lvl

    return False, new_lvl
