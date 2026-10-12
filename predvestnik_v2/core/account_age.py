"""Account-age rule for season rewards (pipeline ECO-01, owner's choice «14 дней в боте»).

An account counts from its first appearance in any chat the bot tracks.  An
account with no chat record is treated as new: it cannot receive season pass
or place rewards.  Pure functions; the lookup lives in
``infrastructure.repositories.account_age``.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Final, Iterable

MIN_ACCOUNT_AGE: Final = timedelta(days=14)


def _utc(value) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return None


def _day_start(value) -> datetime | None:
    try:
        return datetime.combine(date.fromisoformat(str(value)[:10]), datetime.min.time(), tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def first_seen(joined_at, membership_since, first_day) -> datetime | None:
    """Earliest known presence (UTC); naive timestamps are UTC, as in ``bot.chat.tracking``."""
    known = [x for x in (_utc(joined_at), _utc(membership_since), _day_start(first_day)) if x]
    return min(known) if known else None


def eligible_from(seen: datetime | None) -> datetime | None:
    return seen + MIN_ACCOUNT_AGE if seen else None


def is_eligible(seen: datetime | None, at: datetime) -> bool:
    """True when the account was in the bot for the full minimum age at ``at``."""
    start = eligible_from(seen)
    return bool(start) and start <= _utc(at)


def eligible_ids(first_seen_by_user: dict[int, datetime], user_ids: Iterable[int], at: datetime) -> set[int]:
    return {int(u) for u in user_ids if is_eligible(first_seen_by_user.get(int(u)), at)}
