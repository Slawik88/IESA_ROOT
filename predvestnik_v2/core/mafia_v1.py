"""Pure, versioned rules for the approved chat-native Mafia v1."""
from __future__ import annotations

from collections import Counter
from typing import Final, Iterable, Literal


RULESET_VERSION: Final = "mafia-v1"
MIN_PLAYERS: Final = 4
MAX_PLAYERS: Final = 20
LOBBY_REPOST_EVERY_MESSAGES: Final = 10
NIGHT_SECONDS: Final = 60
DISCUSSION_SECONDS: Final = 180
VOTING_SECONDS: Final = 60

Role = Literal["citizen", "mafia", "don", "doctor", "detective"]
Phase = Literal["lobby", "night", "discussion", "voting", "paused", "finished", "cancelled"]
VoteMode = Literal["open", "secret"]

OPTIONAL_ROLES: Final = ("don", "doctor", "detective")
ALL_ROLES: Final = ("citizen", "mafia", *OPTIONAL_ROLES)
OPEN_PHASES: Final = frozenset({"lobby", "discussion"})
CLOSED_PLAYER_PHASES: Final = frozenset({"night", "voting"})


class MafiaRuleError(ValueError):
    pass


def mafia_slots(player_count: int) -> int:
    if not MIN_PLAYERS <= int(player_count) <= MAX_PLAYERS:
        raise MafiaRuleError("party size is outside the approved range")
    return max(1, int(player_count) // 4)


def validate_settings(*, max_players: int, enabled_roles: Iterable[str], vote_mode: str) -> tuple[str, ...]:
    if not MIN_PLAYERS <= int(max_players) <= MAX_PLAYERS:
        raise MafiaRuleError("choose from 4 to 20 seats")
    enabled = tuple(sorted(set(enabled_roles)))
    if any(role not in OPTIONAL_ROLES for role in enabled):
        raise MafiaRuleError("unknown optional role")
    if vote_mode not in ("open", "secret"):
        raise MafiaRuleError("unknown vote mode")
    # Optional faction roles cannot replace the only mafia seat: a game must
    # always include at least one ordinary Mafia role as approved by the owner.
    if "don" in enabled and mafia_slots(max_players) < 2:
        raise MafiaRuleError("Don requires at least 8 seats and an ordinary Mafia member")
    citizen_slots = int(max_players) - mafia_slots(max_players) - (1 if "don" in enabled else 0)
    if sum(role in enabled for role in ("doctor", "detective")) > citizen_slots:
        raise MafiaRuleError("not enough civilian seats for selected roles")
    return enabled


def role_deck(*, player_count: int, enabled_roles: Iterable[str]) -> tuple[Role, ...]:
    enabled = validate_settings(max_players=player_count, enabled_roles=enabled_roles, vote_mode="secret")
    mafia_count = mafia_slots(player_count)
    # Don is a Mafia-faction seat, not an extra adversary.  At eight seats the
    # two faction seats become one ordinary Mafia member plus the Don.
    deck: list[Role] = ["mafia"] * (mafia_count - (1 if "don" in enabled else 0))
    if "don" in enabled:
        deck.append("don")
    if "doctor" in enabled:
        deck.append("doctor")
    if "detective" in enabled:
        deck.append("detective")
    deck.extend(["citizen"] * (int(player_count) - len(deck)))
    if len(deck) != int(player_count) or deck.count("mafia") < 1:
        raise MafiaRuleError("invalid role deck")
    return tuple(deck)


def faction(role: str) -> str:
    if role in ("mafia", "don"):
        return "mafia"
    if role in ("citizen", "doctor", "detective"):
        return "town"
    raise MafiaRuleError("unknown role")


def winner(roles: Iterable[str]) -> str | None:
    alive = [role for role in roles if role]
    mafia = sum(faction(role) == "mafia" for role in alive)
    town = len(alive) - mafia
    if mafia == 0:
        return "town"
    if mafia >= town:
        return "mafia"
    return None


def resolve_vote(votes: Iterable[int | None]) -> int | None:
    valid = [int(target) for target in votes if target is not None]
    if not valid:
        return None
    counts = Counter(valid)
    maximum = max(counts.values())
    leaders = [target for target, count in counts.items() if count == maximum]
    return leaders[0] if len(leaders) == 1 else None


def public_role_name(role: str) -> str:
    return {
        "citizen": "Мирный житель", "mafia": "Мафия", "don": "Дон",
        "doctor": "Доктор", "detective": "Детектив",
    }.get(role, "Неизвестная роль")
