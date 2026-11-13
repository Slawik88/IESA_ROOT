"""«Гонка за Пропуском» (owner, 05.11.2026, S28b): the first players to close the season pass get Telegram Stars.

Money is the owner's red line, so the race is OFF until the owner switches it on (admin «Функции»), and the payout is
manual: the owner sends a gift from the owner's own account and presses «выплачено».  The bot never pays.

Rules (the player's version is the Guide topic «pass-race»):
 - the moment the owner switches the race on is its start; only the season of that moment counts; switching off is a
   pause: a pass closed while the race is off never counts, the start and the places stay;
 - a place goes to a player whose pass crosses level LEVEL after the start; the time is the server's clock at the
   moment the crossing is recorded (not the «Забрать» button).  A player already at LEVEL before the start never
   crosses again in that season, so that player is outside the race;
 - PLACES places, ordered by that time; a rejected player (failed the owner's check) frees the place for the next one;
 - the owner may refuse a place on a suspicion of cheating (twin accounts, unchecked phone-timed results, a ban).
"""
from __future__ import annotations

from typing import Final

from core import league_pass

FLAG: Final = "pass_race_v1"          # system_flags key: off by default, the admin switch sets it
SWITCH: Final = "event:pass_race"      # the row in admin «Функции»
LEVEL: Final = league_pass.LEVELS      # 40: the whole main path of the pass
PLACES: Final = 4
PRIZE_STARS: Final = 50

PENDING, VERIFIED, PAID, REJECTED = "pending", "verified", "paid", "rejected"
STATUSES: Final = (PENDING, VERIFIED, PAID, REJECTED)
STATUS_LABELS: Final = {PENDING: "ждёт проверки", VERIFIED: "проверен", PAID: "выплачено", REJECTED: "отклонён"}
# Which change the owner may make from each status.  «Выплачено» is final: a payout cannot be taken back in the bot.
TRANSITIONS: Final = {PENDING: (VERIFIED, REJECTED), VERIFIED: (PAID, REJECTED), PAID: (), REJECTED: ()}


class RaceRuleError(ValueError):
    pass


def crossed(xp_before: int, xp_after: int) -> bool:
    """This experience gain moved the pass onto LEVEL (only once a season: later gains start above it)."""
    return league_pass.level_of(xp_before) < LEVEL <= league_pass.level_of(xp_after)


def seated(entries: list[dict]) -> list[dict]:
    """Holders of the places, at most PLACES, each with «place» (1 = earliest, ties by player id).

    A checked or paid player keeps the place whatever is recorded later (a recovered crossing with an earlier time, a
    clock step): only waiting ones can be pushed into the queue, so there is never a fifth payout."""
    key = lambda e: (e["reached_at"], int(e["user_id"]))   # noqa: E731
    held = sorted((e for e in entries if e["status"] in (VERIFIED, PAID)), key=key)
    waiting = sorted((e for e in entries if e["status"] == PENDING), key=key)
    chosen = sorted(held + waiting[:max(0, PLACES - len(held))], key=key)
    return [{**e, "place": n} for n, e in enumerate(chosen, start=1)]


def places_left(entries: list[dict]) -> int:
    return PLACES - len(seated(entries))


def check_transition(current: str, new: str) -> None:
    if new not in STATUSES:
        raise RaceRuleError("Такого статуса нет.")
    if new not in TRANSITIONS[current]:
        raise RaceRuleError(f"Из статуса «{STATUS_LABELS[current]}» нельзя перейти в «{STATUS_LABELS[new]}».")
