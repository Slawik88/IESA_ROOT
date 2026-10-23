"""Explicit public/private allowlists: hidden roles never reach another player's browser."""
from core import mafia_online as rules
from core.miniapp_links import miniapp_url
from infrastructure.repositories import mafia_online as repo


def summary(state):
    return {"id": state["id"], "phase": state["phase"], "count": len(state["players"]), "seats": state["seats"],
            "host": next((p["name"] for p in state["players"] if p["id"] == state["host"]), "Город"),
            "tempo": state["tempo"], "round": state["round"], "winner": state.get("winner")}


async def snapshot(db, state, user_id, channel="table", after=0, before=0):
    me = rules.player(state, user_id)
    if not me:
        raise rules.OnlineError("Сначала зайдите за этот стол.", 403)
    allowed = rules.channels(state, me)
    if channel not in allowed:
        raise rules.OnlineError("Этот разговор вам недоступен.", 403)
    ended = state["phase"] in rules.TERMINAL
    public = [{"id": p["id"], "name": p["name"], "seat": p.get("seat", i + 1), "alive": p["alive"], "left": p.get("left", False),
               "muted": bool(p.get("muted") or p.get("staff_muted")), "staff_muted": bool(p.get("staff_muted")), "host": p["id"] == state["host"],
               **({"role": p["role"]} if ended and p.get("role") else {})} for i, p in enumerate(state["players"])]
    action = state["actions"].get(str(user_id))
    team = [{"id": p["id"], "name": p["name"], "seat": p.get("seat", i + 1), "alive": p["alive"]} for i, p in enumerate(state["players"])
            if p.get("role") in ("mafia", "don")] if me.get("role") in ("mafia", "don") else []
    rows = await repo.messages(db, state["id"], channel, after, before)
    for row in rows:
        if row["hidden"]:
            row["body"] = "Сообщение скрыто"
    my = {"id": user_id, "role": me.get("role"), "alive": me["alive"], "left": me.get("left", False),
          "muted": bool(me.get("muted") or me.get("staff_muted")), "action": action, "checks": me.get("checks", []), "team": team,
          "choice_reset": me.get("choice_reset") == state["phase_number"],
          "can_write": rules.can_write(state, me, channel)}
    if me["alive"] and me.get("role") in ("mafia", "don") and state["phase"] == "night":
        my["team_choices"] = [{"id": p["id"], "name": p["name"], "target": state["actions"].get(str(p["id"]), {}).get("target")}
                              for p in team if p["alive"]]
    votes = {}
    if state["phase"] == "voting" and state["vote_mode"] == "open":
        votes = {uid: a["target"] for uid, a in state["actions"].items()}
    return {**summary(state), "redactions": state.get("redactions", 0), "launch_url": launch_url(), "version": state["version"], "phase_number": state["phase_number"],
            "deadline": state.get("deadline"), "server_time": await repo.now(db), "players": public, "me": my,
            "channels": allowed, "channel": channel, "messages": rows, "host_id": state["host"],
            "invite": state["invite"], "visibility": state["visibility"], "vote_mode": state["vote_mode"],
            "roles_auto": state["roles_auto"], "roles": state["roles"], "votes": votes,
            "can_claim": state["phase"] in rules.ACTIVE and state["host"] != user_id and not me.get("left") and me["alive"]
                and (await repo.now(db)) - (rules.player(state, state["host"]) or {}).get("seen", state["created"]) > 90,
            "phase_name": rules.PHASE_NAMES[state["phase"]]}


def launch_url():
    return miniapp_url("mfo_START").replace("mfo_START", "{start}")
