"""Transactional lifecycle for the approved group-chat Mafia v1: lobby, start, moves, control."""
from __future__ import annotations

import secrets
from datetime import timedelta

from core import mafia_v1 as rules
from infrastructure.repositories import mafia_v1 as repo
from infrastructure.repositories import mafia_v1_ops as ops
from services.mafia_common import (  # noqa: F401  (re-exported for handlers and tests)
    MafiaConflict, MafiaError, MafiaForbidden, enabled_roles as _enabled, may_control, phase_deadline, public_view as _public,
)
from services.mafia_phases import (  # noqa: F401
    abort_match, advance_due_match, close_early_if_complete, expire_stale_lobbies, skip_discussion,
)

_SETTING_ERRORS = {
    "choose from 4 to 20 seats": "Выбери от 4 до 20 мест.",
    "Don requires at least 8 seats and an ordinary Mafia member": "Дон появляется только в играх от 8 человек. Выбери 8 мест или больше — или выключи Дона.",
    "not enough civilian seats for selected roles": "Для выбранных ролей не хватает мест. Добавь места или выключи часть ролей.",
    "unknown optional role": "Выбрана неизвестная роль.",
    "unknown vote mode": "Выбран неизвестный тип голосования.",
}


def _validate_settings(*, max_players: int, enabled_roles: tuple[str, ...], vote_mode: str, tempo: str = rules.DEFAULT_TEMPO) -> tuple[str, ...]:
    """Translate pure-rule failures before they reach a Telegram player."""
    if tempo not in rules.TEMPOS:
        raise MafiaConflict("Выбран неизвестный темп игры.")
    try:
        return rules.validate_settings(max_players=max_players, enabled_roles=enabled_roles, vote_mode=vote_mode)
    except rules.MafiaRuleError as exc:
        raise MafiaConflict(_SETTING_ERRORS.get(str(exc), "Эти настройки партии не подходят друг к другу.")) from exc


async def create_lobby(db, *, chat_id: int, topic_id: int | None, initiator_id: int,
                       username: str | None, display_name: str, max_players: int = rules.DEFAULT_SEATS,
                       enabled_roles: tuple[str, ...] = (), vote_mode: str = "secret", tempo: str = rules.DEFAULT_TEMPO,
                       roles_auto: bool | None = None) -> dict:
    roles_auto = (not enabled_roles) if roles_auto is None else roles_auto
    enabled = _validate_settings(max_players=max_players, enabled_roles=enabled_roles, vote_mode=vote_mode, tempo=tempo)
    await repo.ensure_tables(db)
    async with db.connection.transaction():
        await repo.lock_chat(db, chat_id=chat_id, topic_id=topic_id)
        if await repo.purge_active(db, chat_id=chat_id):
            raise MafiaConflict("Нельзя начать Мафию, пока в чате идёт чистка.")
        if await repo.active_match(db, chat_id=chat_id, topic_id=topic_id, for_update=True):
            raise MafiaConflict("В этой группе уже идёт партия Мафии. Её хозяин или админ чата может написать «бот мафия стоп».")
        row = await repo.create_match(
            db, chat_id=chat_id, topic_id=topic_id, initiator_id=initiator_id, max_players=max_players,
            enabled_roles=enabled, vote_mode=vote_mode, ruleset_version=rules.RULESET_VERSION, tempo=tempo,
            roles_auto=roles_auto,
        )
        await repo.add_player(db, match_id=row["id"], user_id=initiator_id, username=username, display_name=display_name)
        await repo.audit(db, match_id=row["id"], event_type="created", actor_id=initiator_id)
        players = await repo.players(db, match_id=row["id"])
    return _public(row, players)


async def join_lobby(db, *, match_id: int, chat_id: int, topic_id: int | None, user_id: int,
                     username: str | None, display_name: str) -> dict:
    async with db.connection.transaction():
        row = await repo.lock_match(db, match_id=match_id)
        if not row or int(row["chat_id"]) != int(chat_id) or (row["topic_id"] or None) != (topic_id or None):
            raise MafiaConflict("Это лобби больше не активно.")
        if row["phase"] != "lobby":
            raise MafiaConflict("Партия уже началась — подожди следующую.")
        players = await repo.players(db, match_id=match_id, for_update=True)
        if not any(int(player["user_id"]) == int(user_id) for player in players):
            if len(players) >= int(row["max_players"]):
                raise MafiaConflict(f"В лобби заняты все {row['max_players']} мест. Хозяин может добавить места в «⚙️ Настройки».")
            if not await repo.add_player(db, match_id=match_id, user_id=user_id, username=username, display_name=display_name):
                raise MafiaConflict("Не удалось занять место в лобби.")
            await repo.audit(db, match_id=match_id, event_type="joined", actor_id=user_id)
            await ops.touch_activity(db, match_id=match_id)
            players = await repo.players(db, match_id=match_id)
    return _public(row, players)


async def join_lobby_by_id(db, *, match_id: int, user_id: int, username: str | None, display_name: str) -> dict:
    """Deep-link join from the private chat: the lobby is located by its id."""
    row = await repo.get_match(db, match_id=match_id)
    if not row or row["phase"] != "lobby":
        raise MafiaConflict("Это лобби уже закрыто или игра началась.")
    return await join_lobby(db, match_id=match_id, chat_id=int(row["chat_id"]), topic_id=row["topic_id"],
                            user_id=user_id, username=username, display_name=display_name)


async def leave_lobby(db, *, match_id: int, chat_id: int, user_id: int) -> dict:
    async with db.connection.transaction():
        row = await repo.lock_match(db, match_id=match_id)
        if not row or int(row["chat_id"]) != int(chat_id) or row["phase"] != "lobby":
            raise MafiaConflict("Это лобби больше не активно.")
        if int(row["initiator_id"]) == int(user_id):
            raise MafiaForbidden("Хозяин лобби не может выйти, но может отменить его кнопкой «Отменить лобби».")
        if not await repo.remove_player(db, match_id=match_id, user_id=user_id):
            raise MafiaConflict("Тебя уже нет в этом лобби.")
        await repo.audit(db, match_id=match_id, event_type="left_lobby", actor_id=user_id)
        await ops.touch_activity(db, match_id=match_id)
        players = await repo.players(db, match_id=match_id)
    return _public(row, players)


async def change_settings(db, *, match_id: int, chat_id: int, topic_id: int | None, actor_id: int, max_players: int,
                          enabled_roles: tuple[str, ...], vote_mode: str, tempo: str | None = None,
                          roles_auto: bool = False) -> dict:
    async with db.connection.transaction():
        row = await repo.lock_match(db, match_id=match_id)
        if (not row or int(row["chat_id"]) != int(chat_id) or (row["topic_id"] or None) != (topic_id or None)
                or row["phase"] != "lobby"):
            raise MafiaConflict("Настройки лобби уже нельзя менять.")
        if int(row["initiator_id"]) != int(actor_id):
            raise MafiaForbidden("Настройки меняет только хозяин лобби.")
        tempo = tempo or row.get("tempo") or rules.DEFAULT_TEMPO
        enabled = _validate_settings(max_players=max_players, enabled_roles=enabled_roles, vote_mode=vote_mode, tempo=tempo)
        players = await repo.players(db, match_id=match_id, for_update=True)
        if len(players) > int(max_players):
            raise MafiaConflict("Нельзя поставить меньше мест, чем уже занято.")
        await repo.update_settings(db, match_id=match_id, max_players=max_players, enabled_roles=enabled,
                                   vote_mode=vote_mode, tempo=tempo, roles_auto=roles_auto)
        await repo.audit(db, match_id=match_id, event_type="settings_changed", actor_id=actor_id,
                         payload={"max_players": max_players, "enabled_roles": list(enabled), "vote_mode": vote_mode,
                                  "tempo": tempo, "roles_auto": roles_auto})
        row = await repo.lock_match(db, match_id=match_id)
    return _public(row, players)


async def start_match(db, *, match_id: int, chat_id: int, actor_id: int) -> tuple[dict, dict[int, str]]:
    """Assign private roles and begin the first night. Caller delivers DMs after commit."""
    async with db.connection.transaction():
        row = await repo.lock_match(db, match_id=match_id)
        if not row or int(row["chat_id"]) != int(chat_id) or row["phase"] != "lobby":
            raise MafiaConflict("Эта партия уже не ожидает старта.")
        if int(row["initiator_id"]) != int(actor_id):
            raise MafiaForbidden("Начать партию может только хозяин лобби.")
        players = await repo.players(db, match_id=match_id, for_update=True)
        if len(players) < rules.MIN_PLAYERS:
            raise MafiaConflict(f"Для старта нужно минимум {rules.MIN_PLAYERS} игрока, сейчас {len(players)}. Позови ещё людей.")
        # Private-message reachability is verified live by the Telegram adapter (see the
        # lobby start button); a stored "I am ready" flag is not a reliable signal.
        chosen = rules.auto_roles(len(players)) if row.get("roles_auto", True) else _enabled(row)
        try:
            enabled = _validate_settings(max_players=len(players), enabled_roles=chosen, vote_mode=row["vote_mode"])
        except MafiaConflict as exc:
            raise MafiaConflict(f"Сейчас в лобби {len(players)} игроков. {exc}") from exc
        deck = list(rules.role_deck(player_count=len(players), enabled_roles=enabled))
        secrets.SystemRandom().shuffle(deck)
        roles_by_user = {int(player["user_id"]): role for player, role in zip(players, deck)}
        await repo.set_roles(db, match_id=match_id, by_user=roles_by_user)
        await repo.update_match(db, match_id=match_id, phase="night", phase_number=1,
                                deadline=phase_deadline(row, "night"), started=True)
        await repo.audit(db, match_id=match_id, event_type="started", actor_id=actor_id)
        row = await repo.lock_match(db, match_id=match_id)
        players = await repo.players(db, match_id=match_id)
    return _public(row, players), roles_by_user


async def confirm_dm_ready(db, *, user_id: int) -> None:
    await repo.ensure_tables(db)
    await repo.mark_dm_ready(db, user_id=user_id)


async def submit_action(db, *, match_id: int, chat_id: int, user_id: int, phase_number: int,
                        action_type: str, target_user_id: int | None, source_message_id: int | None = None) -> dict:
    async with db.connection.transaction():
        row = await repo.lock_match(db, match_id=match_id)
        if not row or int(row["chat_id"]) != int(chat_id):
            raise MafiaConflict("Партия не найдена.")
        if source_message_id is not None and int(row["phase_message_id"] or 0) != int(source_message_id):
            raise MafiaConflict("Эта карточка устарела — нажми кнопки на самом свежем сообщении игры.")
        if row["phase"] not in ("night", "voting") or int(row["phase_number"]) != int(phase_number):
            raise MafiaConflict("Этот этап уже закончился.")
        if row["phase_deadline"] <= row["server_now"]:
            raise MafiaConflict("Время этого этапа вышло.")
        actor = await repo.player(db, match_id=match_id, user_id=user_id, for_update=True)
        target = await repo.player(db, match_id=match_id, user_id=target_user_id, for_update=True) if target_user_id is not None else None
        if not actor or not actor["alive"]:
            raise MafiaForbidden("Ты не можешь ходить в этой партии: ты не участвуешь или уже выбыл.")
        if target_user_id is not None and (not target or not target["alive"]):
            raise MafiaConflict("Этот игрок уже выбыл — выбери другого.")
        _check_move_allowed(row["phase"], actor["role"], action_type, target, user_id)
        await repo.upsert_action(db, match_id=match_id, phase_number=int(row["phase_number"]), user_id=user_id,
                                 action_type=action_type, target_user_id=target_user_id)
        await repo.audit(db, match_id=match_id, event_type="action_changed", actor_id=user_id,
                         payload={"phase": row["phase"], "action": action_type})
        closes_in = await close_early_if_complete(db, row=row, players=await repo.players(db, match_id=match_id))
    return {"match_id": int(match_id), "phase_number": int(phase_number), "action_type": action_type,
            "target_user_id": target_user_id, "closes_in": closes_in}


def _check_move_allowed(phase: str, role: str, action_type: str, target: dict | None, user_id: int) -> None:
    allowed = {
        ("voting", "vote"): True,
        ("night", "mafia_target"): role in ("mafia", "don"),
        ("night", "doctor_save"): role == "doctor",
        ("night", "detective_check"): role == "detective",
    }
    if not allowed.get((phase, action_type), False):
        raise MafiaForbidden("Такой ход сейчас недоступен твоей роли.")
    if action_type != "vote" and target is None:
        raise MafiaConflict("Выбери игрока из списка.")
    if action_type == "mafia_target" and target is not None and rules.faction(target["role"]) == "mafia":
        raise MafiaConflict("Мафия не может выбрать целью своего.")
    if action_type == "detective_check" and target is not None and int(target["user_id"]) == int(user_id):
        raise MafiaConflict("Детектив не проверяет самого себя.")


async def message_gate(db, *, chat_id: int, topic_id: int | None, user_id: int) -> str:
    """Return allow/suppress before ordinary activity metrics count a message.

    Built for big chats (say 40 members, 7 playing): onlookers are never silenced.
    Living players are quiet only at night (so the mafia cannot plot in public);
    eliminated players are quiet only while the town argues and votes.
    """
    row = await repo.active_match(db, chat_id=chat_id, topic_id=topic_id)
    if not row or row["phase"] not in rules.QUIET_PHASES:
        return "allow"
    player = await repo.player(db, match_id=int(row["id"]), user_id=user_id)
    if player is None:
        return "allow"
    if row["phase"] == "night":
        return "suppress" if player["alive"] else "allow"
    return "allow" if player["alive"] else "suppress"


async def note_chat_message(db, *, chat_id: int, topic_id: int | None) -> dict | None:
    """Count a human message; returns the match view when its card should be brought back down."""
    row = await repo.note_chat_message(db, chat_id=chat_id, topic_id=topic_id)
    if not row:
        return None
    need = rules.LOBBY_REPOST_EVERY_MESSAGES if row["phase"] == "lobby" else rules.GAME_CARD_BUMP_EVERY_MESSAGES
    if int(row["lobby_human_messages"]) < need:
        return None
    if not await ops.claim_bump(db, match_id=int(row["id"]), gap_seconds=rules.CARD_BUMP_MIN_GAP_SECONDS):
        return None
    return await current_view(db, match_id=int(row["id"]))


async def current_view(db, *, match_id: int) -> dict | None:
    row = await repo.get_match(db, match_id=match_id)
    if not row:
        return None
    players = await repo.players(db, match_id=match_id)
    view = _public(row, players)
    if row["phase"] == "voting":
        actions = [a for a in await repo.actions(db, match_id=match_id, phase_number=int(row["phase_number"]))
                   if a["action_type"] == "vote"]
        view["votes_cast"], view["votes_needed"] = len(actions), view["alive_count"]
        if row["vote_mode"] == "open":
            view["open_votes"] = _open_votes(players, actions)
    return view


def _open_votes(players: list[dict], actions: list[dict]) -> list[dict]:
    """Open mode shows only current public vote choices, never roles or night moves."""
    names = {int(p["user_id"]): p["display_name"] for p in players}
    grouped: dict[int, list[str]] = {}
    for action in actions:
        if action["target_user_id"] is not None:
            grouped.setdefault(int(action["target_user_id"]), []).append(names.get(int(action["user_id"]), "Игрок"))
    return [{"target_user_id": tid, "target_name": names.get(tid, "Игрок"), "voters": voters}
            for tid, voters in sorted(grouped.items())]


async def player_history(db, *, user_id: int) -> dict:
    """Personal, role-safe Mini App projection; never a chat game control."""
    rows = await repo.player_history(db, user_id=int(user_id))
    finished = [row for row in rows if row["phase"] == "finished"]
    wins = sum(1 for row in finished if row["winner"] and rules.faction(row["role"]) == row["winner"])
    return {
        "version": "mafia-v1-stats",
        "stats": {"played": len(finished), "wins": wins, "active_or_cancelled": len(rows) - len(finished)},
        "matches": [
            {"match_id": int(row["id"]), "chat_id": int(row["chat_id"]), "phase": row["phase"],
             "winner": row["winner"], "finished_reason": row["finished_reason"],
             "role": row["role"], "started_at": row["started_at"], "finished_at": row["finished_at"]}
            for row in rows
        ],
    }


async def cancel_match(db, *, chat_id: int, topic_id: int | None, actor_id: int,
                       reason: str = "cancelled_by_host", is_admin: bool = False) -> dict:
    async with db.connection.transaction():
        row = await repo.active_match(db, chat_id=chat_id, topic_id=topic_id, for_update=True)
        if not row:
            raise MafiaConflict("В этом чате сейчас нет активной партии Мафии.")
        if not may_control(row, actor_id, is_admin):
            raise MafiaForbidden("Остановить партию может хозяин игры или админ чата.")
        mid = int(row["id"])
        await repo.update_match(db, match_id=mid, phase="cancelled", phase_number=int(row["phase_number"]), deadline=None,
                                finished_reason=str(reason))
        await repo.audit(db, match_id=mid, event_type="cancelled", actor_id=actor_id, payload={"reason": reason})
        await ops.set_pending_event(db, match_id=mid, event={"kind": "cancelled", "match_id": mid, "done": []})
        return _public(await repo.lock_match(db, match_id=mid), await repo.players(db, match_id=mid))


async def pause_for_moderation_intervention(db, *, match_id: int) -> None:
    await pause_match(db, match_id=match_id, reason="moderation_intervention")


async def pause_match(db, *, match_id: int, reason: str, detail: str | None = None) -> None:
    async with db.connection.transaction():
        row = await repo.lock_match(db, match_id=match_id)
        if not row or row["phase"] not in ("night", "discussion", "voting"):
            return
        remaining = max(0, int((row["phase_deadline"] - row["server_now"]).total_seconds()))
        await repo.update_match(db, match_id=match_id, phase="paused", phase_number=int(row["phase_number"]), deadline=None,
                                finished_reason=str(reason), paused_phase=row["phase"], paused_remaining_seconds=remaining,
                                keep_clock=True, pause_detail=detail)
        await repo.audit(db, match_id=match_id, event_type="paused", actor_id=None, payload={"reason": str(reason), "detail": detail})


async def resume_match(db, *, chat_id: int, topic_id: int | None, actor_id: int, is_admin: bool = False) -> dict:
    """Resume a safely-paused match with its stored phase and time left."""
    async with db.connection.transaction():
        row = await repo.active_match(db, chat_id=chat_id, topic_id=topic_id, for_update=True)
        if not row or row["phase"] != "paused":
            raise MafiaConflict("В этом чате нет приостановленной партии Мафии.")
        if not may_control(row, actor_id, is_admin):
            raise MafiaForbidden("Продолжить партию может хозяин игры или админ чата.")
        if await repo.purge_active(db, chat_id=chat_id):
            raise MafiaConflict("Сначала дождитесь окончания чистки чата.")
        phase = row["paused_phase"]
        if phase not in ("night", "discussion", "voting"):
            raise MafiaConflict("Не удалось восстановить фазу партии. Остановите её и создайте новую.")
        deadline = row["server_now"] + timedelta(seconds=max(1, int(row["paused_remaining_seconds"] or 0)))
        mid = int(row["id"])
        await repo.update_match(db, match_id=mid, phase=phase, phase_number=int(row["phase_number"]), deadline=deadline,
                                finished_reason=None, paused_phase=None, paused_remaining_seconds=None, keep_clock=True)
        await repo.audit(db, match_id=mid, event_type="resumed", actor_id=int(actor_id))
        return _public(await repo.lock_match(db, match_id=mid), await repo.players(db, match_id=mid))
