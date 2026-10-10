"""Shared errors and the role-safe public projection of a Mafia match."""
from __future__ import annotations

from datetime import timedelta

from core import mafia_v1 as rules
from infrastructure.repositories import mafia_v1 as repo


class MafiaError(Exception):
    pass


class MafiaForbidden(MafiaError):
    pass


class MafiaConflict(MafiaError):
    pass


def enabled_roles(row: dict) -> tuple[str, ...]:
    return tuple(repo.load(row["enabled_roles_json"]) or [])


def deadline_after(row: dict, seconds: int):
    return row["server_now"] + timedelta(seconds=int(seconds))


def phase_deadline(row: dict, phase: str):
    """Deadline for ``phase`` using the match's chosen tempo."""
    return deadline_after(row, rules.phase_seconds(row.get("tempo") or rules.DEFAULT_TEMPO, phase))


def may_control(row: dict, actor_id: int, is_admin: bool = False) -> bool:
    """The host, or an administrator of the chat, controls a running match."""
    return bool(is_admin) or int(row["initiator_id"]) == int(actor_id)


def _reveal(players: list[dict]) -> list[dict]:
    return [{"user_id": int(p["user_id"]), "display_name": p["display_name"], "role": p["role"],
             "alive": bool(p["alive"]), "join_order": int(p["join_order"])} for p in players]


def public_view(row: dict, players: list[dict]) -> dict:
    """Everything a group card may show.  Roles appear only once the game is over."""
    alive = [player for player in players if player["alive"]]
    host = next((p["display_name"] for p in players if int(p["user_id"]) == int(row["initiator_id"])), None)
    view = {
        "match_id": int(row["id"]), "chat_id": int(row["chat_id"]), "topic_id": row["topic_id"],
        "initiator_id": int(row["initiator_id"]), "host_name": host, "ruleset_version": row["ruleset_version"],
        "phase": row["phase"], "phase_number": int(row["phase_number"]), "state_version": int(row["state_version"]),
        "round_number": rules.round_number(int(row["phase_number"])) if int(row["phase_number"]) > 0 else 0,
        "phase_deadline": row["phase_deadline"], "max_players": int(row["max_players"]),
        "enabled_roles": enabled_roles(row), "vote_mode": row["vote_mode"], "tempo": row.get("tempo") or rules.DEFAULT_TEMPO,
        "roles_auto": bool(row.get("roles_auto", True)),
        "winner": row["winner"], "finished_reason": row["finished_reason"], "pause_detail": row.get("pause_detail"),
        "lobby_message_id": row["lobby_message_id"], "phase_message_id": row["phase_message_id"],
        "lobby_human_messages": int(row["lobby_human_messages"]),
        "players": [{"user_id": int(p["user_id"]), "username": p["username"], "display_name": p["display_name"],
                     "alive": bool(p["alive"]), "join_order": int(p["join_order"])} for p in players],
        "alive_count": len(alive), "server_time": row.get("server_now"),
    }
    if row["phase"] == "finished":
        view["roles_reveal"] = _reveal(players)
    return view
