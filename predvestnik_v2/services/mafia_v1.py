"""Transactional lifecycle for the approved group-chat Mafia v1."""
from __future__ import annotations

from datetime import timedelta
import secrets

from core import mafia_v1 as rules
from infrastructure.repositories import mafia_v1 as repo
from services import achievements_v1 as achievements
from services import quests_v1 as quests


class MafiaError(Exception):
    pass


class MafiaForbidden(MafiaError):
    pass


class MafiaConflict(MafiaError):
    pass


def _validate_settings(*, max_players: int, enabled_roles: tuple[str, ...], vote_mode: str) -> tuple[str, ...]:
    """Translate pure-rule failures before they reach a Telegram player."""
    try:
        return rules.validate_settings(max_players=max_players, enabled_roles=enabled_roles, vote_mode=vote_mode)
    except rules.MafiaRuleError as exc:
        messages = {
            "choose from 4 to 20 seats": "Выбери от 4 до 20 мест.",
            "Don requires at least 8 seats and an ordinary Mafia member": "Дон доступен только при 8 игроках или больше.",
            "not enough civilian seats for selected roles": "Для выбранных ролей нужно больше мест в партии.",
            "unknown optional role": "Выбрана неизвестная роль.",
            "unknown vote mode": "Выбран неизвестный тип голосования.",
        }
        raise MafiaConflict(messages.get(str(exc), "Эти настройки партии не подходят друг к другу.")) from exc


def _enabled(row: dict) -> tuple[str, ...]:
    return tuple(repo.load(row["enabled_roles_json"]) or [])


def _deadline(row: dict, seconds: int):
    return row["server_now"] + timedelta(seconds=int(seconds))


def _public(row: dict, players: list[dict]) -> dict:
    alive = [player for player in players if player["alive"]]
    return {
        "match_id": int(row["id"]), "chat_id": int(row["chat_id"]), "topic_id": row["topic_id"],
        "initiator_id": int(row["initiator_id"]), "ruleset_version": row["ruleset_version"],
        "phase": row["phase"], "phase_number": int(row["phase_number"]), "state_version": int(row["state_version"]),
        "phase_deadline": row["phase_deadline"], "max_players": int(row["max_players"]),
        "enabled_roles": _enabled(row), "vote_mode": row["vote_mode"], "winner": row["winner"],
        "finished_reason": row["finished_reason"], "lobby_message_id": row["lobby_message_id"],
        "phase_message_id": row["phase_message_id"], "lobby_human_messages": int(row["lobby_human_messages"]),
        "players": [{"user_id": int(player["user_id"]), "username": player["username"],
                     "display_name": player["display_name"], "alive": bool(player["alive"]),
                     "join_order": int(player["join_order"])} for player in players],
        "alive_count": len(alive), "server_time": row.get("server_now"),
    }


async def create_lobby(db, *, chat_id: int, topic_id: int | None, initiator_id: int,
                       username: str | None, display_name: str, max_players: int = 8,
                       enabled_roles: tuple[str, ...] = (), vote_mode: str = "secret") -> dict:
    enabled = _validate_settings(max_players=max_players, enabled_roles=enabled_roles, vote_mode=vote_mode)
    await repo.ensure_tables(db)
    async with db.connection.transaction():
        await repo.lock_chat(db, chat_id=chat_id, topic_id=topic_id)
        if await repo.purge_active(db, chat_id=chat_id):
            raise MafiaConflict("Нельзя начать Мафию, пока в чате идёт чистка.")
        if await repo.active_match(db, chat_id=chat_id, topic_id=topic_id, for_update=True):
            raise MafiaConflict("В этой группе уже идёт партия Мафии.")
        row = await repo.create_match(
            db, chat_id=chat_id, topic_id=topic_id, initiator_id=initiator_id, max_players=max_players,
            enabled_roles=enabled, vote_mode=vote_mode, ruleset_version=rules.RULESET_VERSION,
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
            raise MafiaConflict("Лобби этой партии больше не активно.")
        if row["phase"] != "lobby":
            raise MafiaConflict("Партия уже началась.")
        players = await repo.players(db, match_id=match_id, for_update=True)
        if not any(int(player["user_id"]) == int(user_id) for player in players):
            if len(players) >= int(row["max_players"]):
                raise MafiaConflict("В лобби уже нет свободных мест.")
            if not await repo.add_player(db, match_id=match_id, user_id=user_id, username=username, display_name=display_name):
                raise MafiaConflict("Не удалось занять место в лобби.")
            await repo.audit(db, match_id=match_id, event_type="joined", actor_id=user_id)
            players = await repo.players(db, match_id=match_id)
    return _public(row, players)


async def leave_lobby(db, *, match_id: int, chat_id: int, user_id: int) -> dict:
    async with db.connection.transaction():
        row = await repo.lock_match(db, match_id=match_id)
        if not row or int(row["chat_id"]) != int(chat_id) or row["phase"] != "lobby":
            raise MafiaConflict("Лобби этой партии больше не активно.")
        if int(row["initiator_id"]) == int(user_id):
            raise MafiaForbidden("Создатель лобби может отменить партию, но не выйти из неё.")
        if not await repo.remove_player(db, match_id=match_id, user_id=user_id):
            raise MafiaConflict("Тебя уже нет в этом лобби.")
        await repo.audit(db, match_id=match_id, event_type="left_lobby", actor_id=user_id)
        players = await repo.players(db, match_id=match_id)
    return _public(row, players)


async def change_settings(db, *, match_id: int, chat_id: int, topic_id: int | None, actor_id: int, max_players: int,
                          enabled_roles: tuple[str, ...], vote_mode: str) -> dict:
    enabled = _validate_settings(max_players=max_players, enabled_roles=enabled_roles, vote_mode=vote_mode)
    async with db.connection.transaction():
        row = await repo.lock_match(db, match_id=match_id)
        if (not row or int(row["chat_id"]) != int(chat_id) or (row["topic_id"] or None) != (topic_id or None)
                or row["phase"] != "lobby"):
            raise MafiaConflict("Настройки лобби уже нельзя менять.")
        if int(row["initiator_id"]) != int(actor_id):
            raise MafiaForbidden("Настройки меняет только создатель лобби.")
        players = await repo.players(db, match_id=match_id, for_update=True)
        if len(players) > int(max_players):
            raise MafiaConflict("Нельзя установить меньше мест, чем уже занято.")
        await repo.update_settings(db, match_id=match_id, max_players=max_players, enabled_roles=enabled, vote_mode=vote_mode)
        await repo.audit(db, match_id=match_id, event_type="settings_changed", actor_id=actor_id,
                         payload={"max_players": max_players, "enabled_roles": list(enabled), "vote_mode": vote_mode})
        row = await repo.lock_match(db, match_id=match_id)
    return _public(row, players)


async def start_match(db, *, match_id: int, chat_id: int, actor_id: int) -> tuple[dict, dict[int, str]]:
    """Assign private roles and begin the first night. Caller delivers DMs after commit."""
    async with db.connection.transaction():
        row = await repo.lock_match(db, match_id=match_id)
        if not row or int(row["chat_id"]) != int(chat_id) or row["phase"] != "lobby":
            raise MafiaConflict("Эта партия уже не ожидает старта.")
        if int(row["initiator_id"]) != int(actor_id):
            raise MafiaForbidden("Начать партию может только её создатель.")
        players = await repo.players(db, match_id=match_id, for_update=True)
        if len(players) < rules.MIN_PLAYERS:
            raise MafiaConflict("Для старта нужны минимум 4 игрока.")
        ready = await repo.dm_ready_users(db, user_ids=[int(player["user_id"]) for player in players])
        if len(ready) != len(players):
            missing = ", ".join(str(player["display_name"]) for player in players if int(player["user_id"]) not in ready)
            raise MafiaConflict(f"Личку с ботом ещё не подтвердили: {missing}. Пусть откроют бота и нажмут «Я готов».")
        # The host can leave seats empty; legality is based on actual players,
        # not on the lobby capacity selected when the card was created.
        enabled = _validate_settings(max_players=len(players), enabled_roles=_enabled(row), vote_mode=row["vote_mode"])
        deck = list(rules.role_deck(player_count=len(players), enabled_roles=enabled))
        secrets.SystemRandom().shuffle(deck)
        roles_by_user = {int(player["user_id"]): role for player, role in zip(players, deck)}
        await repo.set_roles(db, match_id=match_id, by_user=roles_by_user)
        await repo.update_match(db, match_id=match_id, phase="night", phase_number=1,
                                deadline=_deadline(row, rules.NIGHT_SECONDS), started=True)
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
            raise MafiaConflict("Эта карточка голосования уже устарела.")
        if row["phase"] not in ("night", "voting") or int(row["phase_number"]) != int(phase_number):
            raise MafiaConflict("Эта фаза уже завершена.")
        if row["phase_deadline"] <= row["server_now"]:
            raise MafiaConflict("Время этой фазы истекло.")
        actor = await repo.player(db, match_id=match_id, user_id=user_id, for_update=True)
        target = await repo.player(db, match_id=match_id, user_id=target_user_id, for_update=True) if target_user_id is not None else None
        if not actor or not actor["alive"]:
            raise MafiaForbidden("Ты не можешь делать ход в этой партии.")
        if target_user_id is not None and (not target or not target["alive"]):
            raise MafiaConflict("Эта цель уже недоступна.")
        role = actor["role"]
        allowed = {
            ("voting", "vote"): True,
            ("night", "mafia_target"): role in ("mafia", "don"),
            ("night", "doctor_save"): role == "doctor",
            ("night", "detective_check"): role == "detective",
        }
        if not allowed.get((row["phase"], action_type), False):
            raise MafiaForbidden("Такой ход сейчас недоступен твоей роли.")
        if action_type == "mafia_target" and target is not None and rules.faction(target["role"]) == "mafia":
            raise MafiaConflict("Мафия не может выбрать целью союзника.")
        if action_type == "detective_check" and int(target_user_id or 0) == int(user_id):
            raise MafiaConflict("Детектив не проверяет самого себя.")
        await repo.upsert_action(db, match_id=match_id, phase_number=int(row["phase_number"]), user_id=user_id,
                                 action_type=action_type, target_user_id=target_user_id)
        await repo.audit(db, match_id=match_id, event_type="action_changed", actor_id=user_id,
                         payload={"phase": row["phase"], "action": action_type})
    return {"match_id": int(match_id), "phase_number": int(phase_number), "action_type": action_type,
            "target_user_id": target_user_id}


async def advance_due_match(db, *, match_id: int) -> dict | None:
    """Advance one expired phase exactly once; callers publish the returned event after commit."""
    async with db.connection.transaction():
        row = await repo.lock_match(db, match_id=match_id)
        if not row or row["phase"] not in ("night", "discussion", "voting") or row["phase_deadline"] > row["server_now"]:
            return None
        players = await repo.players(db, match_id=match_id, for_update=True)
        event: dict = {"match_id": int(match_id), "previous_phase": row["phase"], "private_checks": []}
        if row["phase"] == "night":
            actions = await repo.actions(db, match_id=match_id, phase_number=int(row["phase_number"]))
            mafia_target = rules.resolve_vote(action["target_user_id"] for action in actions if action["action_type"] == "mafia_target")
            saved = next((action["target_user_id"] for action in actions if action["action_type"] == "doctor_save"), None)
            killed = mafia_target if mafia_target is not None and mafia_target != saved else None
            if killed is not None:
                await repo.kill_player(db, match_id=match_id, user_id=killed)
            for action in actions:
                if action["action_type"] == "detective_check" and action["target_user_id"] is not None:
                    checked = next((p for p in players if int(p["user_id"]) == int(action["target_user_id"])), None)
                    if checked:
                        event["private_checks"].append({"user_id": int(action["user_id"]), "target_user_id": int(checked["user_id"]), "is_mafia": rules.faction(checked["role"]) == "mafia"})
            players = await repo.players(db, match_id=match_id)
            won = rules.winner(player["role"] for player in players if player["alive"])
            event["eliminated_user_id"] = killed
            if won:
                await repo.update_match(db, match_id=match_id, phase="finished", phase_number=int(row["phase_number"]), deadline=None,
                                        winner=won, finished_reason="night_win")
            else:
                await repo.update_match(db, match_id=match_id, phase="discussion", phase_number=int(row["phase_number"]) + 1,
                                        deadline=_deadline(row, rules.DISCUSSION_SECONDS))
        elif row["phase"] == "discussion":
            await repo.update_match(db, match_id=match_id, phase="voting", phase_number=int(row["phase_number"]) + 1,
                                    deadline=_deadline(row, rules.VOTING_SECONDS))
        else:
            actions = await repo.actions(db, match_id=match_id, phase_number=int(row["phase_number"]))
            eliminated = rules.resolve_vote(action["target_user_id"] for action in actions if action["action_type"] == "vote")
            if eliminated is not None:
                await repo.kill_player(db, match_id=match_id, user_id=eliminated)
            players = await repo.players(db, match_id=match_id)
            won = rules.winner(player["role"] for player in players if player["alive"])
            event["eliminated_user_id"] = eliminated
            if won:
                await repo.update_match(db, match_id=match_id, phase="finished", phase_number=int(row["phase_number"]), deadline=None,
                                        winner=won, finished_reason="vote_win")
            else:
                await repo.update_match(db, match_id=match_id, phase="night", phase_number=int(row["phase_number"]) + 1,
                                        deadline=_deadline(row, rules.NIGHT_SECONDS))
        await repo.audit(db, match_id=match_id, event_type="phase_advanced", actor_id=None, payload=event)
        row = await repo.lock_match(db, match_id=match_id)
        players = await repo.players(db, match_id=match_id)
        if row["phase"] == "finished":
            # Every seat receives one terminal-activity event.  Match id is
            # immutable, so scheduler retries and concurrent due checks cannot
            # increase a participant's progress twice.
            for player in sorted(players, key=lambda item: int(item["user_id"])):
                event_id = f"mafia:{match_id}"
                user_id = int(player["user_id"])
                sources = await quests.available_sources(db, user_id=user_id)
                for metric in ("game_completed", "mafia_completed"):
                    await quests.record_metric(db, user_id=user_id, metric=metric,
                                               event_id=event_id, vip_active=False, sources=sources)
                if rules.faction(str(player["role"])) == str(row["winner"]):
                    await quests.record_metric(db, user_id=user_id, metric="mafia_win",
                                               event_id=event_id, vip_active=False, sources=sources)
                await achievements.record_terminal(
                    db, user_id=user_id, metric="mafia_completed", source_event_id=str(match_id),
                    source_snapshot={"match_id": int(match_id)},
                )
    event["view"] = _public(row, players)
    return event


async def message_gate(db, *, chat_id: int, topic_id: int | None, user_id: int) -> str:
    """Return allow/suppress before ordinary activity metrics count a message."""
    row = await repo.active_match(db, chat_id=chat_id, topic_id=topic_id)
    if not row or row["phase"] in ("lobby", "paused"):
        return "allow"
    player = await repo.player(db, match_id=int(row["id"]), user_id=user_id)
    is_alive_player = bool(player and player["alive"])
    is_registered_player = player is not None
    if row["phase"] == "discussion":
        return "allow" if is_alive_player else "suppress"
    if row["phase"] in ("night", "voting"):
        return "suppress" if is_registered_player else "allow"
    return "allow"


async def note_lobby_human_message(db, *, chat_id: int, topic_id: int | None) -> dict | None:
    row = await repo.note_lobby_message(db, chat_id=chat_id, topic_id=topic_id)
    if not row or int(row["lobby_human_messages"]) < rules.LOBBY_REPOST_EVERY_MESSAGES:
        return None
    players = await repo.players(db, match_id=int(row["id"]))
    return _public(row, players)


async def current_view(db, *, match_id: int) -> dict | None:
    row = await repo.get_match(db, match_id=match_id)
    if not row:
        return None
    players = await repo.players(db, match_id=match_id)
    view = _public(row, players)
    # "Open" must be observably different from secret voting.  Only the
    # current public vote choices are exposed; private roles and night actions
    # never enter this projection.
    if row["phase"] == "voting" and row["vote_mode"] == "open":
        names = {int(player["user_id"]): player["display_name"] for player in players}
        grouped: dict[int, list[str]] = {}
        for action in await repo.actions(db, match_id=match_id, phase_number=int(row["phase_number"])):
            if action["action_type"] == "vote" and action["target_user_id"] is not None:
                grouped.setdefault(int(action["target_user_id"]), []).append(names.get(int(action["user_id"]), "Игрок"))
        view["open_votes"] = [
            {"target_user_id": target_id, "target_name": names.get(target_id, "Игрок"), "voters": voters}
            for target_id, voters in sorted(grouped.items())
        ]
    return view


async def player_history(db, *, user_id: int) -> dict:
    """Personal, role-safe Mini App projection; never a chat game control."""
    rows = await repo.player_history(db, user_id=int(user_id))
    finished = [row for row in rows if row["phase"] == "finished"]
    wins = sum(
        1 for row in finished
        if (row["winner"] == "mafia" and rules.faction(row["role"]) == "mafia")
        or (row["winner"] == "town" and rules.faction(row["role"]) == "town")
    )
    return {
        "version": "mafia-v1-stats",
        "stats": {"played": len(finished), "wins": wins, "active_or_cancelled": len(rows) - len(finished)},
        "matches": [
            {
                "match_id": int(row["id"]), "chat_id": int(row["chat_id"]), "phase": row["phase"],
                "winner": row["winner"], "finished_reason": row["finished_reason"],
                "role": row["role"], "started_at": row["started_at"], "finished_at": row["finished_at"],
            }
            for row in rows
        ],
    }


async def cancel_match(db, *, chat_id: int, topic_id: int | None, actor_id: int, reason: str = "cancelled_by_host") -> dict:
    async with db.connection.transaction():
        row = await repo.active_match(db, chat_id=chat_id, topic_id=topic_id, for_update=True)
        if not row:
            raise MafiaConflict("Активной партии в этом чате нет.")
        if int(row["initiator_id"]) != int(actor_id):
            raise MafiaForbidden("Остановить партию может только её создатель.")
        await repo.update_match(db, match_id=int(row["id"]), phase="cancelled", phase_number=int(row["phase_number"]), deadline=None,
                                finished_reason=str(reason))
        await repo.audit(db, match_id=int(row["id"]), event_type="cancelled", actor_id=actor_id, payload={"reason": reason})
        row = await repo.lock_match(db, match_id=int(row["id"]))
        players = await repo.players(db, match_id=int(row["id"]))
    return _public(row, players)


async def pause_for_moderation_intervention(db, *, match_id: int) -> None:
    await pause_match(db, match_id=match_id, reason="moderation_intervention")


async def pause_match(db, *, match_id: int, reason: str) -> None:
    async with db.connection.transaction():
        row = await repo.lock_match(db, match_id=match_id)
        if not row or row["phase"] not in ("night", "discussion", "voting"):
            return
        remaining = max(0, int((row["phase_deadline"] - row["server_now"]).total_seconds()))
        await repo.update_match(db, match_id=match_id, phase="paused", phase_number=int(row["phase_number"]), deadline=None,
                                finished_reason=str(reason), paused_phase=row["phase"], paused_remaining_seconds=remaining)
        await repo.audit(db, match_id=match_id, event_type="paused", actor_id=None, payload={"reason": str(reason)})


async def resume_match(db, *, chat_id: int, topic_id: int | None, actor_id: int) -> dict:
    """Resume only the host's safely-paused match with its stored time left."""
    async with db.connection.transaction():
        row = await repo.active_match(db, chat_id=chat_id, topic_id=topic_id, for_update=True)
        if not row or row["phase"] != "paused":
            raise MafiaConflict("В этом чате нет приостановленной партии Мафии.")
        if int(row["initiator_id"]) != int(actor_id):
            raise MafiaForbidden("Продолжить партию может только её создатель.")
        if await repo.purge_active(db, chat_id=chat_id):
            raise MafiaConflict("Сначала дождитесь окончания чистки чата.")
        phase = row["paused_phase"]
        if phase not in ("night", "discussion", "voting"):
            raise MafiaConflict("Не удалось восстановить фазу партии. Отмените её и создайте новую.")
        deadline = row["server_now"] + timedelta(seconds=max(1, int(row["paused_remaining_seconds"] or 0)))
        await repo.update_match(db, match_id=int(row["id"]), phase=phase, phase_number=int(row["phase_number"]), deadline=deadline,
                                finished_reason=None, paused_phase=None, paused_remaining_seconds=None)
        await repo.audit(db, match_id=int(row["id"]), event_type="resumed", actor_id=int(actor_id))
        row = await repo.lock_match(db, match_id=int(row["id"]))
        players = await repo.players(db, match_id=int(row["id"]))
    return _public(row, players)
