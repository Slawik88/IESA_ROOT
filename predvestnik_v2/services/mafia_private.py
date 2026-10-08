"""Role-private projections: a player's own role/team and the mafia coordination board.

Nothing here is ever rendered into a group message; callers deliver it in DMs or in a
callback popup that only the pressing player can see.
"""
from __future__ import annotations

from core import mafia_v1 as rules
from infrastructure.repositories import mafia_v1 as repo


def target_label(player: dict) -> str:
    return f"#{player['join_order']} {player['display_name']}"


def _is_mafia_side(player: dict) -> bool:
    return bool(player.get("role")) and rules.faction(player["role"]) == "mafia"


async def private_view(db, *, match_id: int, user_id: int) -> dict | None:
    """The asking player's own role plus, for the mafia side, their teammates."""
    row = await repo.get_match(db, match_id=match_id)
    players = await repo.players(db, match_id=match_id)
    me = next((p for p in players if int(p["user_id"]) == int(user_id)), None)
    if not row or not me:
        return None
    team = [p for p in players if _is_mafia_side(p) and int(p["user_id"]) != int(user_id)] if _is_mafia_side(me) else []
    return {"role": me["role"], "alive": bool(me["alive"]), "phase": row["phase"],
            "teammates": [(p["display_name"], p["role"]) for p in team], "players": players}


async def team_board(db, *, match_id: int, phase_number: int) -> tuple[list[tuple[str, str, str | None]], str | None]:
    """(rows, leading label): what each living mafioso picked tonight and the current outcome."""
    players = await repo.players(db, match_id=match_id)
    actions = [a for a in await repo.actions(db, match_id=match_id, phase_number=phase_number)
               if a["action_type"] == "mafia_target"]
    by_id = {int(p["user_id"]): p for p in players}
    picks = {int(a["user_id"]): a for a in actions}
    rows = []
    for p in players:
        if not (_is_mafia_side(p) and p["alive"]):
            continue
        pick = picks.get(int(p["user_id"]))
        target = by_id.get(int(pick["target_user_id"])) if pick and pick["target_user_id"] is not None else None
        rows.append((p["display_name"], p["role"], target_label(target) if target else None))
    votes = [rules.NightVote(by_id[uid]["role"], a["target_user_id"], a["created_at"])
             for uid, a in picks.items() if uid in by_id]
    lead = rules.resolve_night_kill(votes)
    return rows, (target_label(by_id[lead]) if lead in by_id else None)
