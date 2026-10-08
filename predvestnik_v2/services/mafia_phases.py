"""Phase engine for chat Mafia v1: closing a phase exactly once, early close, abandonment.

Every function that changes a match runs in one row-locked transaction.  Side effects
for Telegram are *not* performed here: the outcome is stored as ``pending_event_json``
inside the same transaction, so a crash between commit and delivery cannot lose the
"dawn" message or a player's night buttons.
"""
from __future__ import annotations

from core import mafia_v1 as rules
from infrastructure.repositories import mafia_v1 as repo
from infrastructure.repositories import mafia_v1_ops as ops
from services import achievements_v1 as achievements
from services import quests_v1 as quests
from services.mafia_common import MafiaConflict, MafiaForbidden, deadline_after, may_control, phase_deadline, public_view

_TIMED = ("night", "discussion", "voting")


def _role_of(players: list[dict], user_id: int) -> str:
    return next((str(p["role"]) for p in players if int(p["user_id"]) == int(user_id)), "")


async def _close_night(db, row: dict, players: list[dict]) -> dict:
    actions = await repo.actions(db, match_id=int(row["id"]), phase_number=int(row["phase_number"]))
    votes = [rules.NightVote(_role_of(players, a["user_id"]), a["target_user_id"], a["created_at"])
             for a in actions if a["action_type"] == "mafia_target"]
    target = rules.resolve_night_kill(votes)
    saved = next((a["target_user_id"] for a in actions if a["action_type"] == "doctor_save"), None)
    killed = target if target is not None and target != saved else None
    if killed is not None:
        await repo.kill_player(db, match_id=int(row["id"]), user_id=killed)
    checks = []
    for action in actions:
        checked = next((p for p in players if int(p["user_id"]) == int(action["target_user_id"] or 0)), None)
        if action["action_type"] == "detective_check" and checked:
            checks.append({"user_id": int(action["user_id"]), "target_user_id": int(checked["user_id"]),
                           "is_mafia": rules.faction(checked["role"]) == "mafia"})
    return {"eliminated_user_id": killed, "private_checks": checks, "idle": not actions}


async def _close_voting(db, row: dict, players: list[dict]) -> dict:
    actions = await repo.actions(db, match_id=int(row["id"]), phase_number=int(row["phase_number"]))
    ballots = [a for a in actions if a["action_type"] == "vote"]
    eliminated = rules.resolve_vote(a["target_user_id"] for a in ballots)
    if eliminated is not None:
        await repo.kill_player(db, match_id=int(row["id"]), user_id=eliminated)
    return {"eliminated_user_id": eliminated, "private_checks": [], "idle": not ballots}


_NEXT = {"night": "discussion", "voting": "night"}
_WIN_REASON = {"night": "night_win", "voting": "vote_win"}


async def _move_on(db, row: dict, outcome: dict) -> None:
    """Persist the next phase: win, abandonment, or the following timed phase."""
    match_id, number, phase = int(row["id"]), int(row["phase_number"]), row["phase"]
    players = await repo.players(db, match_id=match_id)
    won = rules.winner(p["role"] for p in players if p["alive"])
    idle = int(row.get("idle_phases") or 0) + 1 if outcome.pop("idle") else 0
    await ops.set_idle_phases(db, match_id=match_id, value=idle)
    if won:
        await repo.update_match(db, match_id=match_id, phase="finished", phase_number=number, deadline=None,
                                winner=won, finished_reason=_WIN_REASON[phase])
    elif idle >= rules.IDLE_PHASES_TO_ABANDON:
        outcome["abandoned"] = True
        await repo.update_match(db, match_id=match_id, phase="cancelled", phase_number=number, deadline=None,
                                finished_reason="abandoned")
    else:
        await repo.update_match(db, match_id=match_id, phase=_NEXT[phase], phase_number=number + 1,
                                deadline=phase_deadline(row, _NEXT[phase]))


async def _record_terminal(db, row: dict, players: list[dict]) -> None:
    """One idempotent quest/achievement receipt per seat (match id is immutable)."""
    match_id = int(row["id"])
    for player in sorted(players, key=lambda item: int(item["user_id"])):
        event_id, user_id = f"mafia:{match_id}", int(player["user_id"])
        sources = await quests.available_sources(db, user_id=user_id)
        for metric in ("game_completed", "mafia_completed"):
            await quests.record_metric(db, user_id=user_id, metric=metric, event_id=event_id,
                                       vip_active=False, sources=sources)
        if rules.faction(str(player["role"])) == str(row["winner"]):
            await quests.record_metric(db, user_id=user_id, metric="mafia_win", event_id=event_id,
                                       vip_active=False, sources=sources)
        await achievements.record_terminal(db, user_id=user_id, metric="mafia_completed",
                                           source_event_id=str(match_id), source_snapshot={"match_id": match_id})


async def advance_due_match(db, *, match_id: int) -> dict | None:
    """Advance one expired phase exactly once; returns the stored delivery event."""
    async with db.connection.transaction():
        row = await repo.lock_match(db, match_id=match_id)
        if not row or row["phase"] not in _TIMED or row["phase_deadline"] > row["server_now"]:
            return None
        players = await repo.players(db, match_id=match_id, for_update=True)
        event = {"kind": "phase", "match_id": int(match_id), "previous_phase": row["phase"],
                 "previous_number": int(row["phase_number"]), "private_checks": [], "eliminated_user_id": None, "done": []}
        if row["phase"] == "discussion":
            await repo.update_match(db, match_id=match_id, phase="voting", phase_number=int(row["phase_number"]) + 1,
                                    deadline=phase_deadline(row, "voting"))
        else:
            closer = _close_night if row["phase"] == "night" else _close_voting
            outcome = await closer(db, row, players)
            event.update(outcome)
            await _move_on(db, row, event)
        await repo.audit(db, match_id=match_id, event_type="phase_advanced", actor_id=None, payload=event)
        await ops.set_pending_event(db, match_id=match_id, event=event)
        row = await repo.lock_match(db, match_id=match_id)
        players = await repo.players(db, match_id=match_id)
        if row["phase"] == "finished":
            await _record_terminal(db, row, players)
    return {**event, "view": public_view(row, players)}


async def close_early_if_complete(db, *, row: dict, players: list[dict]) -> int | None:
    """Shorten the phase once everyone it waits for has moved; returns seconds left."""
    if row["phase"] not in ("night", "voting"):
        return None
    done = await ops.acted_pairs(db, match_id=int(row["id"]), phase_number=int(row["phase_number"]))
    if not rules.is_phase_complete(row["phase"], [(int(p["user_id"]), p["role"], bool(p["alive"])) for p in players], done):
        return None
    floor = rules.NIGHT_MIN_SECONDS if row["phase"] == "night" else rules.VOTING_MIN_SECONDS
    started = row.get("phase_started_at") or row["server_now"]
    elapsed = max(0.0, (row["server_now"] - started).total_seconds())
    wait = max(float(rules.EARLY_CLOSE_GRACE_SECONDS), floor - elapsed)
    target = deadline_after(row, int(wait))
    if target < row["phase_deadline"] and await ops.shorten_deadline(db, match_id=int(row["id"]), deadline=target):
        return int(wait)
    return None


async def skip_discussion(db, *, chat_id: int, topic_id: int | None, actor_id: int, is_admin: bool = False) -> dict:
    """Host/admin ends the talking early; the caller then advances the due phase."""
    async with db.connection.transaction():
        row = await repo.active_match(db, chat_id=chat_id, topic_id=topic_id, for_update=True)
        if not row or row["phase"] != "discussion":
            raise MafiaConflict("Сейчас не время обсуждения — пропускать нечего.")
        if not may_control(row, actor_id, is_admin):
            raise MafiaForbidden("Перейти к голосованию может хозяин игры или админ чата.")
        await ops.shorten_deadline(db, match_id=int(row["id"]), deadline=row["server_now"])
        await repo.audit(db, match_id=int(row["id"]), event_type="discussion_skipped", actor_id=actor_id)
        return public_view(await repo.lock_match(db, match_id=int(row["id"])), await repo.players(db, match_id=int(row["id"])))


async def expire_stale_lobbies(db, *, idle_seconds: int = rules.LOBBY_IDLE_SECONDS) -> list[int]:
    """Close lobbies nobody touched for ``idle_seconds`` so a chat is never blocked forever."""
    closed: list[int] = []
    for match_id in await ops.stale_lobby_ids(db, idle_seconds=idle_seconds):
        async with db.connection.transaction():
            row = await repo.lock_match(db, match_id=match_id)
            if not row or row["phase"] != "lobby":
                continue
            await repo.update_match(db, match_id=match_id, phase="cancelled", phase_number=0, deadline=None,
                                    finished_reason="lobby_expired")
            event = {"kind": "lobby_expired", "match_id": match_id, "done": []}
            await ops.set_pending_event(db, match_id=match_id, event=event)
            await repo.audit(db, match_id=match_id, event_type="lobby_expired", actor_id=None)
        closed.append(match_id)
    return closed


async def abort_match(db, *, match_id: int, reason: str) -> None:
    """System-side cancel (e.g. a private role could not be delivered) with a stored notice."""
    async with db.connection.transaction():
        row = await repo.lock_match(db, match_id=match_id)
        if not row or row["phase"] not in ("lobby", "night", "discussion", "voting", "paused"):
            return
        await repo.update_match(db, match_id=match_id, phase="cancelled", phase_number=int(row["phase_number"]),
                                deadline=None, finished_reason=str(reason))
        await ops.set_pending_event(db, match_id=match_id, event={"kind": "cancelled", "match_id": match_id, "done": []})
        await repo.audit(db, match_id=match_id, event_type="aborted", actor_id=None, payload={"reason": reason})
