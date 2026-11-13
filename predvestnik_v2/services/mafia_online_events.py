"""Stable animation facts from an already authorized snapshot, never raw room state."""


def events_for(view: dict) -> list[dict]:
    room, phase, mine = view["id"], view["phase_number"], view["me"]
    prefix = f"{room}:{phase}"
    events = [{"id": f"{prefix}:phase:{view['phase']}", "kind": "phase",
               "phase": view["phase"], "phase_number": phase}]
    if mine.get("role"):
        events.append({"id": f"{room}:role:{mine['id']}", "kind": "role",
                       "player_id": mine["id"], "role": mine["role"]})
    for check in mine.get("checks", []):
        events.append({"id": f"{room}:check:{mine['id']}:{check['round']}:{check['target']}",
                       "kind": "check", "player_id": mine["id"],
                       "target": check["target"], "mafia": bool(check["mafia"])})
    for player in view["players"]:
        if not player["alive"] and not player["left"]:
            events.append({"id": f"{room}:out:{player['id']}", "kind": "death",
                           "player_id": player["id"]})
    progress = view.get("voting_progress")
    if progress:
        events.append({"id": f"{prefix}:votes:{progress['submitted']}", "kind": "vote",
                       "submitted": progress["submitted"]})
    if view["phase"] == "finished":
        events.append({"id": f"{room}:winner", "kind": "victory", "winner": view.get("winner")})
    return events


def phase_for(view: dict) -> dict:
    """Turn kind is public; individual night eligibility belongs only to the viewer."""
    phase = view["phase"]
    turn = {"lobby": "host", "night": "night_actions", "discussion": "discussion",
            "voting": "vote", "paused": "paused"}.get(phase, "none")
    started = (view["paused_at"] if phase == "paused" else view.get("finished_at")
               if phase in ("finished", "cancelled") else view["phase_started"])
    duration = (view["deadline"] - started if started and view["deadline"] else None) if phase == "paused" else view["phase_duration"]
    return {"phase": phase, "number": view["phase_number"], "started_at": started,
            "duration": duration, "deadline": view["deadline"], "actor_id": view["host_id"] if phase == "lobby" else None,
            "remaining": view["phase_remaining"], "paused_phase": view["paused_phase"],
            "turn": turn, "my_turn": view["me"]["can_act"]}
