"""Independent web Mafia contract. Local Mafia is imported read-only for pure rules."""
from core.mafia_v1 import (auto_roles, faction, is_phase_complete, night_action_for, phase_seconds,
                           public_role_name, resolve_day_vote, resolve_night_kill, role_deck, winner, NightVote)

ACTIVE = ("lobby", "night", "discussion", "voting", "paused")
TERMINAL = ("finished", "cancelled")
FLAG = "game_mafia_online"
MAX_CHAT = 600
LOBBY_TTL = 1200
MAX_ROUNDS = 30
POSTGAME_CHAT_TTL = 15 * 60
PRESENCE_TTL = 75
HOST_CLAIM_TTL = 90
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


def host_claim_at(state):
    host = player(state, state["host"])
    # A handoff grants time to accept control without pretending an offline person is online.
    return max((host or {}).get("seen", state["created"]), state.get("host_since", state["created"])) + HOST_CLAIM_TTL


def channels(state, me):
    out = ["table"]
    if me and not me["alive"] and state["phase"] != "lobby":
        out.append("afterlife")
    if me and me["alive"] and me.get("role") in ("mafia", "don") and state["phase"] == "night":
        out.append("mafia")
    if state["phase"] in TERMINAL:
        out = ["table", "afterlife"]
    return out


def can_write(state, me, channel, now=None):
    if channel not in channels(state, me):
        return False
    if not me or me.get("left") or me.get("muted") or me.get("staff_muted") or state["phase"] == "paused":
        return False
    if state["phase"] in TERMINAL:
        return bool(state["phase"] == "finished" and channel == "table" and now is not None
                    and state.get("finished_at") is not None and now < state["finished_at"] + POSTGAME_CHAT_TTL)
    if channel == "afterlife":
        return not me["alive"] and state["phase"] != "lobby"
    if channel == "mafia":
        return channel in channels(state, me)
    return me["alive"] and state["phase"] in ("lobby", "discussion", "voting")


def write_reason(state, me, channel, now):
    """Short UI hint follows the same access rules as send(), without role disclosures."""
    if can_write(state, me, channel, now):
        return ""
    if not me or me.get("left"):
        return "Вы покинули стол"
    if me.get("muted") or me.get("staff_muted"):
        return "Чат временно ограничен модератором"
    if state["phase"] == "paused":
        return "Разговор продолжится после паузы"
    if state["phase"] in TERMINAL:
        return "Разговор завершён"
    if channel == "table" and not me["alive"]:
        return "Для выбывших открыт отдельный разговор"
    if channel == "table" and state["phase"] == "night":
        return "Город спит — общий чат откроется утром"
    return "Этот разговор сейчас недоступен"
