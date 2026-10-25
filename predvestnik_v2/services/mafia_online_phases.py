"""Web-only phase engine. Caller holds the online room lock; never calls Telegram."""
import secrets

from core import mafia_online as rules
from infrastructure.repositories import mafia_online as repo


async def notice(db, state, text):
    await repo.message(db, state["id"], "table", text)


async def finish(db, state, winner=None, reason="victory"):
    state.update(phase="finished" if winner else "cancelled", winner=winner, reason=reason,
                 deadline=None, finished_at=await repo.now(db))
    await repo.release(db, state["id"])
    text = {"town": "Мирные победили. Город может спать спокойно.", "mafia": "Мафия победила. Город остался в тени.",
            "draw": "Ничья. Город затих."}.get(winner, "Партия закрыта.")
    await notice(db, state, text)


async def start(db, state, now):
    roles = rules.auto_roles(len(state["players"])) if state["roles_auto"] else tuple(state["roles"])
    try:
        deck = list(rules.role_deck(player_count=len(state["players"]), enabled_roles=roles))
    except ValueError:
        raise rules.OnlineError("Для этих ролей нужно больше игроков. Выберите роли автоматически.") from None
    secrets.SystemRandom().shuffle(deck)
    for p, role in zip(state["players"], deck):
        p.update(role=role, alive=True, checks=[])
    state.update(phase="night", phase_number=1, round=1, phase_started=now,
                 deadline=now + rules.phase_seconds(state["tempo"], "night"),
                 phase_deadline=now + rules.phase_seconds(state["tempo"], "night"), actions={}, idle=0)
    await notice(db, state, "Ночь 1. Город засыпает. Ваша роль — в карточке над разговором.")


async def advance(db, state, now):
    if state["phase"] in rules.TERMINAL or not state.get("deadline") or state["deadline"] > now:
        return False
    phase = state["phase"]
    if phase in ("lobby", "paused"):
        await finish(db, state, reason="idle")
        await repo.save(db, state)
        return True
    by_id = {p["id"]: p for p in state["players"]}
    actions = {uid: a for uid, a in state["actions"].items() if by_id[int(uid)]["alive"]
               and (a["target"] is None or by_id.get(a["target"], {}).get("alive"))}
    if phase == "night":
        votes = [rules.NightVote(by_id[int(uid)]["role"], a["target"], a["time"])
                 for uid, a in actions.items() if a["kind"] == "mafia_target"]
        target = rules.resolve_night_kill(votes)
        saved = {a["target"] for a in actions.values() if a["kind"] == "doctor_save"}
        for uid, action in actions.items():
            if action["kind"] == "detective_check" and action["target"] in by_id:
                by_id[int(uid)]["checks"].append({"round": state["round"], "target": action["target"],
                    "name": by_id[action["target"]]["name"], "seat": by_id[action["target"]].get("seat"),
                    "mafia": rules.faction(by_id[action["target"]]["role"]) == "mafia"})
        killed = by_id.get(target) if target not in saved else None
        if killed:
            killed["alive"] = False
        await notice(db, state, f"Утро {state['round']}. {rules.label(killed)} выбыл." if killed else f"Утро {state['round']}. Все живы.")
        next_phase = "discussion"
    elif phase == "discussion":
        next_phase = "voting"
        await notice(db, state, "Голосование. Выберите игрока или «Никого».")
    else:
        target = rules.resolve_day_vote(a["target"] for a in actions.values())
        if target in by_id:
            by_id[target]["alive"] = False
            await notice(db, state, f"Город решил: {rules.label(by_id[target])} выбывает.")
        else:
            await notice(db, state, "Город никого не выбрал.")
        next_phase = "night"
        state["round"] += 1
    if phase != "discussion":
        state["idle"] = 0 if actions else state.get("idle", 0) + 1
    winner = rules.winner(p["role"] for p in state["players"] if p["alive"])
    if not winner and (state["idle"] >= 4 or state["round"] > rules.MAX_ROUNDS):
        winner = "draw"
    if winner:
        await finish(db, state, winner)
    else:
        state.update(phase=next_phase, phase_number=state["phase_number"] + 1, phase_started=now,
                     deadline=now + rules.phase_seconds(state["tempo"], next_phase),
                     phase_deadline=now + rules.phase_seconds(state["tempo"], next_phase), actions={})
        if next_phase == "night":
            await notice(db, state, f"Ночь {state['round']}. Город засыпает.")
    await repo.save(db, state)
    return True


def shorten(state, now):
    people = [(p["id"], p["role"], p["alive"]) for p in state["players"]]
    acted = [(int(uid), a["kind"]) for uid, a in state["actions"].items()]
    if rules.is_phase_complete(state["phase"], people, acted):
        state["deadline"] = min(state["deadline"], max(now + 5, state["phase_started"] + 15))
