"""Pure, versioned rules for the approved chat-native Mafia v1."""
from __future__ import annotations

from collections import Counter
from typing import Final, Iterable, Literal, NamedTuple


RULESET_VERSION: Final = "mafia-v1"
MIN_PLAYERS: Final = 4
MAX_PLAYERS: Final = 20
# Seats of a fresh lobby: a table of friends should never hit "lobby full" before the host finds settings.
DEFAULT_SEATS: Final = 12
# A busy chat buries the card: bring it back after this many human messages, but never more
# often than CARD_BUMP_MIN_GAP_SECONDS (a 40-person chat writes 10 messages in a minute).
LOBBY_REPOST_EVERY_MESSAGES: Final = 25
GAME_CARD_BUMP_EVERY_MESSAGES: Final = 30
CARD_BUMP_MIN_GAP_SECONDS: Final = 90
NIGHT_SECONDS: Final = 60
DISCUSSION_SECONDS: Final = 180
VOTING_SECONDS: Final = 60
# Game tempo presets: (night, discussion, voting) seconds.  "normal" equals the
# historical constants so an existing lobby behaves exactly as before.
TEMPOS: Final = {"fast": (40, 90, 40), "normal": (NIGHT_SECONDS, DISCUSSION_SECONDS, VOTING_SECONDS), "slow": (90, 300, 90)}
DEFAULT_TEMPO: Final = "normal"
# A phase ends early once every required player has acted.  The floors hide
# which roles exist (a night never ends instantly) and the grace window lets the
# last player fix a misclick.
EARLY_CLOSE_GRACE_SECONDS: Final = 5
NIGHT_MIN_SECONDS: Final = 20
VOTING_MIN_SECONDS: Final = 15
# Abandoned-game safety nets.
LOBBY_IDLE_SECONDS: Final = 30 * 60
IDLE_PHASES_TO_ABANDON: Final = 4
# Group-card edit pacing (Telegram allows ~20 messages/min per group).
CARD_REFRESH_SECONDS: Final = 8
CARD_EVENT_GAP_SECONDS: Final = 1.5

Role = Literal["citizen", "mafia", "don", "doctor", "detective"]
Phase = Literal["lobby", "night", "discussion", "voting", "paused", "finished", "cancelled"]
VoteMode = Literal["open", "secret"]

OPTIONAL_ROLES: Final = ("don", "doctor", "detective")
ALL_ROLES: Final = ("citizen", "mafia", *OPTIONAL_ROLES)
OPEN_PHASES: Final = frozenset({"lobby", "discussion"})
CLOSED_PLAYER_PHASES: Final = frozenset({"night", "voting"})
# Phases in which some participants are asked to keep out of the chat (see services.message_gate).
QUIET_PHASES: Final = frozenset({"night", "discussion", "voting"})


class MafiaRuleError(ValueError):
    pass


class NightVote(NamedTuple):
    """One mafia-side night choice; ``order`` is any sortable "chosen at" key."""

    role: str
    target: int | None
    order: object


def phase_seconds(tempo: str, phase: str) -> int:
    night, discussion, voting = TEMPOS.get(tempo, TEMPOS[DEFAULT_TEMPO])
    return {"night": night, "discussion": discussion, "voting": voting}[phase]


def round_number(phase_number: int) -> int:
    """Night 1/Day 1 share round 1: phases cycle night, discussion, voting."""
    return (max(1, int(phase_number)) - 1) // 3 + 1


def resolve_night_kill(votes: Iterable[NightVote]) -> int | None:
    """Mafia plurality; a tie goes to the Don, otherwise to the earliest choice."""
    cast = [vote for vote in votes if vote.target is not None]
    if not cast:
        return None
    counts = Counter(int(vote.target) for vote in cast)
    top = max(counts.values())
    leaders = {target for target, count in counts.items() if count == top}
    if len(leaders) == 1:
        return next(iter(leaders))
    for vote in cast:
        if vote.role == "don" and int(vote.target) in leaders:
            return int(vote.target)
    return int(min((vote for vote in cast if int(vote.target) in leaders), key=lambda vote: vote.order).target)


_NIGHT_ACTION = {"mafia": "mafia_target", "don": "mafia_target", "doctor": "doctor_save", "detective": "detective_check"}


def night_action_for(role: str) -> str | None:
    return _NIGHT_ACTION.get(role)


def is_phase_complete(phase: str, players: Iterable[tuple[int, str, bool]], acted: Iterable[tuple[int, str]]) -> bool:
    """True when every living player the phase waits for has submitted a move.

    ``players``: (user_id, role, alive); ``acted``: (user_id, action_type).
    """
    done = set(acted)
    alive = [(uid, role) for uid, role, is_alive in players if is_alive]
    if phase == "voting":
        return bool(alive) and all((uid, "vote") in done for uid, _ in alive)
    if phase == "night":
        waiting = [(uid, night_action_for(role)) for uid, role in alive if night_action_for(role)]
        return bool(waiting) and all((uid, action) in done for uid, action in waiting)
    return False


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


def auto_roles(player_count: int) -> tuple[str, ...]:
    """Optional roles a game gets when the host leaves the setting on «авто» (no configuring)."""
    count = int(player_count)
    if count < 6:
        return ()
    return ("detective", "doctor") if count < 8 else ("detective", "doctor", "don")


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


def resolve_day_vote(votes: Iterable[int | None]) -> int | None:
    """Day vote where «Никого» is a real option: a player leaves only with MORE votes than every
    rival *and* than the abstentions (one vote against five «Никого» removes nobody)."""
    cast = list(votes)
    abstain = sum(vote is None for vote in cast)
    leader = resolve_vote(cast)
    if leader is None:
        return None
    return leader if sum(int(vote) == leader for vote in cast if vote is not None) > abstain else None


def public_role_name(role: str) -> str:
    return {
        "citizen": "Мирный житель", "mafia": "Мафия", "don": "Дон",
        "doctor": "Доктор", "detective": "Детектив",
    }.get(role, "Неизвестная роль")
