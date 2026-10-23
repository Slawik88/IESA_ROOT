"""Independent web Mafia contract. Local Mafia is imported read-only for pure rules."""
from core.mafia_v1 import (auto_roles, faction, is_phase_complete, night_action_for, phase_seconds,
                           public_role_name, resolve_day_vote, resolve_night_kill, role_deck, winner, NightVote)

ACTIVE = ("lobby", "night", "discussion", "voting", "paused")
TERMINAL = ("finished", "cancelled")
FLAG = "game_mafia_online"
MAX_CHAT = 600
LOBBY_TTL = 1200
MAX_ROUNDS = 30
PHASE_NAMES = {"lobby": "Сбор игроков", "night": "Ночь", "discussion": "Обсуждение", "voting": "Голосование",
               "paused": "Пауза", "finished": "Игра окончена", "cancelled": "Партия закрыта"}


class OnlineError(ValueError):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def player(state, user_id):
    return next((p for p in state["players"] if p["id"] == user_id), None)


def label(person):
    return f"{person['name']} · #{person['seat']}" if person.get("seat") else person["name"]


def channels(state, me):
    out = ["table"]
    if me and not me["alive"] and state["phase"] != "lobby":
        out.append("afterlife")
    if me and me["alive"] and me.get("role") in ("mafia", "don") and state["phase"] == "night":
        out.append("mafia")
    if state["phase"] in TERMINAL:
        out = ["table", "afterlife"]
    return out


def can_write(state, me, channel):
    if not me or me.get("left") or me.get("muted") or me.get("staff_muted") or state["phase"] in TERMINAL or state["phase"] == "paused":
        return False
    if channel == "afterlife":
        return not me["alive"] and state["phase"] != "lobby"
    if channel == "mafia":
        return channel in channels(state, me)
    return me["alive"] and state["phase"] in ("lobby", "discussion", "voting")
