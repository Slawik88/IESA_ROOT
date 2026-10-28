"""Limits and result types for the read-only chat inactivity list."""
from dataclasses import dataclass

DAY_SECONDS = 86400
DEFAULT_SECONDS = DAY_SECONDS
MAX_DAYS = 36500
PAGE_SIZE = 15
QUERY_TIMEOUT_SECONDS = 8
MAX_PAGE = 2_000_000_000
MAX_PERIOD_LENGTH = 128
QUICK_PERIODS = (("1 день", DAY_SECONDS), ("7 дней", 7 * DAY_SECONDS),
                 ("30 дней", 30 * DAY_SECONDS), ("1 год", 365 * DAY_SECONDS))


@dataclass(frozen=True)
class InactiveMember:
    user_id: int
    username: str | None
    name: str | None
    seconds: int
    never_spoke: bool
    rejoined: bool


@dataclass(frozen=True)
class InactivePage:
    items: tuple[InactiveMember, ...]
    total: int
    unknown: int
    page: int
    pages: int
