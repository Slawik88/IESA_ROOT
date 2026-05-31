import math
from datetime import datetime, timedelta, timezone

from core.constants import (
    STREAK_BLOCK_SIZE,
    STREAK_BASE_MORA_REWARD,
    STREAK_BASE_DIAMONDS_REWARD,
    STREAK_BLOCK_BONUS_MULT,
    STREAK_RECOVERY_DIAMONDS,
    STREAK_RECOVERY_MORA,
    STREAK_RECOVERY_WINDOW_HOURS,
)


def get_today_in_tz(tz_offset: int) -> str:
    """Return 'YYYY-MM-DD' for today in the given UTC offset."""
    now_utc = datetime.now(timezone.utc)
    adjusted = now_utc + timedelta(hours=tz_offset)
    return adjusted.strftime("%Y-%m-%d")


def days_between(date_str_a: str, date_str_b: str) -> int:
    """Return (b - a) in calendar days. Positive means b is after a."""
    a = datetime.strptime(date_str_a, "%Y-%m-%d")
    b = datetime.strptime(date_str_b, "%Y-%m-%d")
    return (b - a).days


def calc_new_streak(old_streak: int, missed_days: int) -> int:
    """Apply block-based penalty: miss N days = fall back N blocks.
    Formula: max(0, ((streak-1)//7 - (N-1)) * 7)"""
    if old_streak == 0 or missed_days == 0:
        return old_streak
    current_block = (old_streak - 1) // STREAK_BLOCK_SIZE
    new_block = max(0, current_block - (missed_days - 1))
    return new_block * STREAK_BLOCK_SIZE


def calc_streak_reward(streak: int) -> dict:
    """Logarithmic growth reward. Block-end day gets STREAK_BLOCK_BONUS_MULT bonus."""
    if streak <= 0:
        streak = 1
    cycle = (streak - 1) // STREAK_BLOCK_SIZE
    day_in_block = ((streak - 1) % STREAK_BLOCK_SIZE) + 1
    is_block_end = (day_in_block == STREAK_BLOCK_SIZE)

    log_mult = 1.0 + 0.5 * math.log(1.0 + cycle)
    block_mult = STREAK_BLOCK_BONUS_MULT if is_block_end else 1.0

    mora = round(STREAK_BASE_MORA_REWARD * log_mult * block_mult, 2)
    diamonds = round(STREAK_BASE_DIAMONDS_REWARD * log_mult * block_mult, 2)

    return {
        "mora": mora,
        "diamonds": diamonds,
        "day_in_block": day_in_block,
        "is_block_end": is_block_end,
        "cycle": cycle,
    }


def calc_recovery_cost(missed_days: int) -> dict:
    """Cost to undo the block-penalty from N missed days."""
    return {
        "diamonds": round(missed_days * STREAK_RECOVERY_DIAMONDS, 2),
        "mora": round(missed_days * STREAK_RECOVERY_MORA, 2),
        "missed_days": missed_days,
    }


def recovery_expires_str() -> str:
    """Return ISO datetime string for when the recovery window closes."""
    expires = datetime.now() + timedelta(hours=STREAK_RECOVERY_WINDOW_HOURS)
    return expires.strftime("%Y-%m-%d %H:%M:%S")


def is_recovery_valid(recovery_expires: str) -> bool:
    """True if the recovery window has not yet expired."""
    if not recovery_expires:
        return False
    try:
        expires = parse_dt(recovery_expires)
        return datetime.now() < expires
    except ValueError:
        return False


def process_daily_login(streak_row: dict, today: str) -> dict:
    """Pure business logic for handling a user's first message of the day.

    Returns a result dict with all the info needed by the middleware
    to update the DB and send notifications.

    result keys:
        is_new_day: bool
        already_notified: bool
        new_streak: int
        reward: dict | None
        missed_days: int
        penalty_applied: bool
        recovery_streak: int  — original streak before penalty (0 if no penalty)
        recovery_missed_days: int
        recovery_expires: str | None
    """
    last_login = streak_row.get("last_login")
    last_notified = streak_row.get("last_notified")
    old_streak = streak_row.get("streak", 0)

    # Not a new day yet (already logged in today)
    if last_login == today:
        return {
            "is_new_day": False,
            "already_notified": (last_notified == today),
            "new_streak": old_streak,
            "reward": None,
            "missed_days": 0,
            "penalty_applied": False,
            "recovery_streak": streak_row.get("recovery_streak", 0),
            "recovery_missed_days": streak_row.get("recovery_missed_days", 0),
            "recovery_expires": streak_row.get("recovery_expires"),
        }

    missed_days = 0
    penalty_applied = False
    recovery_streak = 0
    recovery_missed_days = 0
    recovery_expires_val = None

    if last_login is not None:
        delta = days_between(last_login, today)
        if delta > 1:
            missed_days = delta - 1
            recovery_streak = old_streak
            recovery_missed_days = missed_days
            recovery_expires_val = recovery_expires_str()
            old_streak = calc_new_streak(old_streak, missed_days)
            penalty_applied = True

    new_streak = old_streak + 1
    reward = calc_streak_reward(new_streak)

    return {
        "is_new_day": True,
        "already_notified": False,
        "new_streak": new_streak,
        "reward": reward,
        "missed_days": missed_days,
        "penalty_applied": penalty_applied,
        "recovery_streak": recovery_streak,
        "recovery_missed_days": recovery_missed_days,
        "recovery_expires": recovery_expires_val,
    }
