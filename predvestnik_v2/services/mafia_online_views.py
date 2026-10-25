"""Explicit public/private allowlists: hidden roles never reach another player's browser."""
from core import mafia_online as rules
from core.miniapp_links import miniapp_url
from infrastructure.repositories import mafia_online as repo


def summary(state):
    return {"id": state["id"], "phase": state["phase"], "count": len(state["players"]), "seats": state["seats"],
            "host": next((p["name"] for p in state["players"] if p["id"] == state["host"]), "Город"),
            "tempo": state["tempo"], "round": state["round"], "winner": state.get("winner"),
            "visibility": state["visibility"], "vote_mode": state["vote_mode"],
            "living_count": sum(p["alive"] and not p.get("left") for p in state["players"]),
            "created_at": state["created"], "finished_at": state.get("finished_at"), "finish_reason": state.get("reason")}


def action_details(state, me):
    """Targets depend only on my known role/team, never expose anybody else's role."""
    kind = ("vote" if state["phase"] == "voting" else rules.night_action_for(me.get("role"))
            if state["phase"] == "night" else None)
    can_act = bool(kind and me["alive"] and not me.get("left"))
    targets = []
    if can_act:
        for p in state["players"]:
            if not p["alive"] or p.get("left"):
                continue
            if kind in ("vote", "detective_check") and p["id"] == me["id"]:
                continue
            if kind == "mafia_target" and p["role"] in ("mafia", "don"):
                continue
            targets.append(p["id"])
    hints = {"vote": "Выберите подозреваемого или никого. Голос можно изменить до конца этапа.",
             "mafia_target": "Выберите жертву. Обсудите решение в чате мафии.",
             "doctor_save": "Выберите, кого спасти. Можно выбрать себя.",
             "detective_check": "Выберите, кого проверить. Ответ появится утром."}
    return {"can_act": can_act, "action_kind": kind if can_act else None,
            "action_targets": targets, "action_hint": hints.get(kind, "") if can_act else ""}


async def snapshot(db, state, user_id, channel="table", after=0, before=0):
    me = rules.player(state, user_id)
    if not me:
        raise rules.OnlineError("Сначала зайдите за этот стол.", 403)
    now = await repo.now(db)
    allowed = rules.channels(state, me)
    if channel not in allowed:
        raise rules.OnlineError("Этот разговор вам недоступен.", 403)
    ended = state["phase"] in rules.TERMINAL
    public = [{"id": p["id"], "name": p["name"], "seat": p.get("seat", i + 1), "alive": p["alive"], "left": p.get("left", False),
               "muted": bool(p.get("muted") or p.get("staff_muted")), "staff_muted": bool(p.get("staff_muted")), "host": p["id"] == state["host"],
               "online": not p.get("left") and now - p.get("seen", 0) <= rules.PRESENCE_TTL,
               **({"role": p["role"]} if ended and p.get("role") else {})} for i, p in enumerate(state["players"])]
    action = state["actions"].get(str(user_id))
    team = [{"id": p["id"], "name": p["name"], "seat": p.get("seat", i + 1), "alive": p["alive"]} for i, p in enumerate(state["players"])
            if p.get("role") in ("mafia", "don")] if me.get("role") in ("mafia", "don") else []
    rows = await repo.messages(db, state["id"], channel, after, before)
    for row in rows:
        if row["hidden"]:
            row["body"] = "Сообщение скрыто"
            # A removed message must not keep displaying its quoted sensitive content.
            row.update(reply_to=None, reply_name=None, reply_seat=None, reply_body=None, reply_hidden=None)
        row["can_reply"] = bool(not row["hidden"] and rules.can_write(state, me, channel, now))
        row["can_report"] = bool(not me.get("left") and row["user_id"] is not None)
        row["can_hide"] = bool(not me.get("left") and user_id == state["host"] and row["user_id"] is not None and not row["hidden"])
    my = {"id": user_id, "role": me.get("role"), "alive": me["alive"], "left": me.get("left", False),
          "muted": bool(me.get("muted") or me.get("staff_muted")), "action": action, "checks": me.get("checks", []), "team": team,
          "choice_reset": me.get("choice_reset") == state["phase_number"],
          "can_write": rules.can_write(state, me, channel, now), "seat": me.get("seat"),
          "write_reason": rules.write_reason(state, me, channel, now), **action_details(state, me)}
    if me["alive"] and me.get("role") in ("mafia", "don") and state["phase"] == "night":
        my["team_choices"] = [{"id": p["id"], "name": p["name"], "target": state["actions"].get(str(p["id"]), {}).get("target")}
                              for p in team if p["alive"]]
    votes = {}
    if state["phase"] == "voting" and state["vote_mode"] == "open":
        votes = {uid: a["target"] for uid, a in state["actions"].items()}
    latest = await repo.channel_latest(db, state["id"], allowed)
    channel_state = {name: {"latest_id": latest.get(name, 0), "can_write": rules.can_write(state, me, name, now),
                            "write_reason": rules.write_reason(state, me, name, now)} for name in allowed}
    host = rules.player(state, state["host"])
    claim_at = rules.host_claim_at(state)
    phase = state.get("paused", state["phase"]) if state["phase"] == "paused" else state["phase"]
    duration = rules.phase_seconds(state["tempo"], phase) if phase in ("night", "discussion", "voting") else rules.LOBBY_TTL if phase == "lobby" else None
    return {**summary(state), "redactions": state.get("redactions", 0), "launch_url": launch_url(), "version": state["version"], "phase_number": state["phase_number"],
            "deadline": state.get("deadline"), "server_time": now, "players": public, "me": my,
            "chat_until": state.get("finished_at", 0) + rules.POSTGAME_CHAT_TTL if state["phase"] == "finished" else None,
            "channels": allowed, "channel_state": channel_state, "channel": channel, "messages": rows, "host_id": state["host"],
            "online_count": sum(p["online"] for p in public), "host_online": bool(host and not host.get("left") and now - host.get("seen", 0) <= rules.PRESENCE_TTL),
            "claim_available_at": claim_at if state["host"] != user_id and state["phase"] in rules.ACTIVE and me["alive"] and not me.get("left") else None,
            "phase_started": state.get("phase_started", state["created"]), "phase_duration": duration,
            "paused_phase": state.get("paused") if state["phase"] == "paused" else None,
            "phase_remaining": state.get("remaining") if state["phase"] == "paused" else None,
            "voting_progress": {"submitted": sum(1 for uid, a in state["actions"].items() if a["kind"] == "vote" and (rules.player(state, int(uid)) or {}).get("alive")),
                                "total": sum(p["alive"] for p in state["players"])} if state["phase"] == "voting" else None,
            "invite": state["invite"], "visibility": state["visibility"], "vote_mode": state["vote_mode"],
            "roles_auto": state["roles_auto"], "roles": state["roles"], "votes": votes,
            "can_claim": state["phase"] in rules.ACTIVE and state["host"] != user_id and not me.get("left") and me["alive"]
                and now > claim_at,
            "phase_name": rules.PHASE_NAMES[state["phase"]]}


def launch_url():
    return miniapp_url("mfo_START").replace("mfo_START", "{start}")
