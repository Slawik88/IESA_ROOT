import math
from datetime import datetime, timedelta, timezone
from services.formatting import parse_dt

from core.constants import (
    STREAK_BLOCK_SIZE,
    STREAK_BASE_MORA_REWARD,
    STREAK_BASE_DIAMONDS_REWARD,
    STREAK_BLOCK_BONUS_MULT,
    STREAK_RECOVERY_DIAMONDS,
    STREAK_RECOVERY_MORA,
    STREAK_RECOVERY_WINDOW_HOURS,
)


def get_today_in_tz(tz_offset: int) -> datetime:
    """Return midnight datetime for today in the given UTC offset (naive)."""
    now_utc = datetime.now(timezone.utc)
    adjusted = now_utc + timedelta(hours=tz_offset)
    return adjusted.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)


def _to_date(v) -> "datetime | None":
    """Normalise datetime / date-string / None to a naive datetime."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    if hasattr(v, "year"):          # datetime.date object
        return datetime(v.year, v.month, v.day)
    s = str(v)[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        return None


def days_between(a, b) -> int:
    """Return (b - a) in calendar days. Positive means b is after a."""
    da = _to_date(a)
    db = _to_date(b)
    if da is None or db is None:
        return 0
    return (db.date() - da.date()).days


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


def recovery_expires_dt() -> datetime:
    """Return datetime when the recovery window closes."""
    return datetime.now() + timedelta(hours=STREAK_RECOVERY_WINDOW_HOURS)


# Keep old name as alias so existing callers don't break
def recovery_expires_str() -> str:
    return recovery_expires_dt().strftime("%Y-%m-%d %H:%M:%S")


def is_recovery_valid(recovery_expires) -> bool:
    """True if the recovery window has not yet expired. Accepts datetime or str."""
    if not recovery_expires:
        return False
    if isinstance(recovery_expires, datetime):
        return datetime.now() < recovery_expires.replace(tzinfo=None)
    try:
        expires = parse_dt(str(recovery_expires))
        return datetime.now() < expires
    except (ValueError, TypeError):
        return False


def _same_day(a, b) -> bool:
    """Compare two values (datetime / date / str / None) by calendar date."""
    da = _to_date(a)
    db = _to_date(b)
    if da is None or db is None:
        return False
    return da.date() == db.date()


def process_daily_login(streak_row: dict, today: datetime) -> dict:
    """Pure business logic for handling a user's first message of the day.

    `today` should be a naive datetime at midnight (from get_today_in_tz).
    `streak_row` values last_login / last_notified may be datetime objects
    (TIMESTAMP columns) or None.

    result keys:
        is_new_day: bool
        already_notified: bool
        new_streak: int
        reward: dict | None
        missed_days: int
        penalty_applied: bool
        recovery_streak: int
        recovery_missed_days: int
        recovery_expires: datetime | None
    """
    last_login = streak_row.get("last_login")
    last_notified = streak_row.get("last_notified")
    old_streak = streak_row.get("streak", 0)

    # Not a new day yet (already logged in today)
    if _same_day(last_login, today):
        return {
            "is_new_day": False,
            "already_notified": _same_day(last_notified, today),
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
            recovery_expires_val = recovery_expires_dt()
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
