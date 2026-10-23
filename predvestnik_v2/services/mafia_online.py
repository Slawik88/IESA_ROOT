"""Independent cross-chat rooms: transactionally reserve seats and accept role moves."""
import secrets
import hashlib
import json

from core import mafia_online as rules
from core.mafia_v1 import validate_settings
from infrastructure.repositories import mafia_online as repo
from services import mafia_online_phases as engine, mafia_online_views as views


async def person(db, user, seat):
    name = " ".join(str(user.get(k) or "") for k in ("first_name", "last_name")).strip()
    name = name or user.get("username") or await repo.profile_name(db, int(user["id"])) or f"Игрок {seat}"
    return {"id": int(user["id"]), "name": " ".join(str(name).split())[:60], "seat": seat, "role": None,
            "alive": True, "left": False, "muted": False, "checks": [], "seen": await repo.now(db)}


def settings(seats=8, tempo="normal", roles_auto=True, roles=(), vote_mode="secret", visibility="public"):
    if tempo not in ("fast", "normal", "slow") or visibility not in ("public", "invite"):
        raise rules.OnlineError("Выберите темп и доступ к столу.")
    try:
        # In auto mode the deck is chosen from the actual player count at start.
        # Inactive manual checkboxes must not prevent shrinking an automatic table.
        validate_settings(max_players=seats, enabled_roles=() if roles_auto else roles, vote_mode=vote_mode)
    except ValueError:
        raise rules.OnlineError("Выберите от 4 до 20 мест и подходящие роли.") from None
    return dict(seats=seats, tempo=tempo, roles_auto=roles_auto, roles=list(roles), vote_mode=vote_mode, visibility=visibility)


async def locked(db, room_id):
    state = await repo.load(db, room_id, lock=True)
    if not state:
        raise rules.OnlineError("Стол не найден.", 404)
    await engine.advance(db, state, await repo.now(db))
    return state


async def active_room(db, user_id):
    """Recover expired seats even while the background scheduler is restarting."""
    async with db.connection.transaction():
        await repo.user_lock(db, user_id)
        room_id = await repo.current(db, user_id)
        if room_id:
            await locked(db, room_id)
        return await repo.current(db, user_id)


async def hub(db, user_id):
    active = await active_room(db, user_id)
    now = await repo.now(db)
    rooms = []
    for room_id in await repo.candidates(db):
        row = await repo.load(db, room_id)
        if row and row["visibility"] == "public" and row["phase"] == "lobby" and row.get("deadline") and len(row["players"]) < row["seats"] and row["deadline"] > now:
            rooms.append(views.summary(row))
    history = [views.summary(row) for row in await repo.history(db, user_id)]
    return {"user_id": user_id, "active": active, "rooms": rooms, "history": history, "launch_url": views.launch_url(), "server_time": await repo.now(db)}


async def create(db, user, **options):
    config = settings(**options)
    async with db.connection.transaction():
        await repo.user_lock(db, int(user["id"]))
        active = await active_room(db, int(user["id"]))
        if active:
            return active
        now = await repo.now(db)
        state = {**config, "host": int(user["id"]), "invite": secrets.token_hex(8), "players": [await person(db, user, 1)],
                 "phase": "lobby", "phase_number": 0, "round": 0, "version": 1, "actions": {},
                 "deadline": now + rules.LOBBY_TTL, "created": now, "next_seat": 2}
        room_id = await repo.create(db, state)
        await repo.take_seat(db, room_id, int(user["id"]))
        await engine.notice(db, state, "Город ждёт игроков. Можно начинать от четырёх.")
        return room_id


async def join(db, room_id, user, invite=""):
    uid = int(user["id"])
    # Commit stale-seat recovery before locking the destination room. Keeping
    # both room locks can deadlock two players following each other's old link.
    await active_room(db, uid)
    async with db.connection.transaction():
        await repo.user_lock(db, uid)
        active = await repo.current(db, uid)
        if active and active != room_id:
            raise rules.OnlineError("Вы уже за другим столом. Вернитесь в свою партию.")
        state = await locked(db, room_id)
        if rules.player(state, uid) and not rules.player(state, uid).get("left"):
            return room_id
        if state["visibility"] == "invite" and not secrets.compare_digest(invite.encode(), state["invite"].encode()):
            raise rules.OnlineError("За этот стол входят по приглашению.", 403)
        if state["phase"] != "lobby":
            raise rules.OnlineError("Партия уже началась. Выберите другой стол.")
        if len(state["players"]) >= state["seats"]:
            raise rules.OnlineError("Последнее место уже заняли. Выберите другой стол.")
        seat = state.get("next_seat", max((p.get("seat", i + 1) for i, p in enumerate(state["players"])), default=0) + 1)
        newcomer = await person(db, user, seat)
        newcomer.update(state.get("restrictions", {}).get(str(uid), {}))
        state["players"].append(newcomer)
        state["next_seat"] = seat + 1
        state["deadline"] = await repo.now(db) + rules.LOBBY_TTL
        await repo.take_seat(db, room_id, uid)
        await engine.notice(db, state, f"{rules.label(newcomer)} за столом.")
        if len(state["players"]) == state["seats"]:
            await engine.start(db, state, await repo.now(db))
        await repo.save(db, state)
        return room_id


async def quick(db, user):
    # Serialize only automatic selection/creation, so simultaneous arrivals build one table.
    async with db.connection.transaction():
        await repo.matchmaking_lock(db)
        return await _quick_locked(db, user)


async def _quick_locked(db, user):
    active = await active_room(db, int(user["id"]))
    if active:
        return active
    for room_id in await repo.candidates(db):
        try:
            return await join(db, room_id, user)
        except rules.OnlineError:
            if await repo.current(db, int(user["id"])):
                return await repo.current(db, int(user["id"]))
    return await create(db, user)


async def get(db, room_id, uid, channel="table", after=0, before=0):
    async with db.connection.transaction():
        state = await locked(db, room_id)
        me = rules.player(state, uid)
        now = await repo.now(db)
        if me and now - me.get("seen", 0) > 15:
            me["seen"] = now
            await repo.save(db, state, bump=False)
        return await views.snapshot(db, state, uid, channel, after, before)


async def control(db, room_id, uid, command, phase_number=None, nonce=None, expected_version=None, **options):
    digest = hashlib.sha256(json.dumps([command, phase_number, expected_version, options], sort_keys=True).encode()).hexdigest()
    async with db.connection.transaction():
        # Same order as join to serialize a leaving player with entry to another room.
        await repo.user_lock(db, uid)
        state = await locked(db, room_id)
        if nonce:
            previous = await repo.command_receipt(db, room_id, uid, nonce)
            if previous:
                if previous["digest"] != digest:
                    raise rules.OnlineError("Этот запрос уже использован для другого действия.")
                return {**previous["result"], "replayed": True}
        me = rules.player(state, uid)
        if not me or me.get("left"):
            raise rules.OnlineError("Вы уже вышли из партии.", 403)
        if state["phase"] in rules.TERMINAL:
            raise rules.OnlineError("Эта партия уже закончилась.")
        me["seen"] = await repo.now(db)
        if command == "settings" and expected_version is not None and expected_version != state["version"]:
            raise rules.OnlineError("Стол изменился. Проверьте его и повторите действие.")
        if command not in ("leave", "claim") and phase_number is not None and phase_number != state["phase_number"]:
            raise rules.OnlineError("Этап уже сменился. Проверьте стол перед действием.")
        if command == "claim":
            host = rules.player(state, state["host"])
            now = await repo.now(db)
            if not me["alive"] or now - (host or {}).get("seen", state["created"]) <= 90:
                raise rules.OnlineError("Хозяин ещё за столом.")
            state["host"] = uid
            me["seen"] = now
            await engine.notice(db, state, f"{rules.label(me)} теперь хозяин стола.")
            await repo.save(db, state)
            result = {"ok": True, "replayed": False}
            if nonce:
                await repo.remember_command(db, room_id, uid, nonce, digest, result)
            return result
        if command == "leave":
            await repo.release(db, room_id, uid)
            if state["phase"] == "lobby":
                state.setdefault("restrictions", {})[str(uid)] = {k: bool(me.get(k)) for k in ("muted", "staff_muted")}
                state["players"] = [p for p in state["players"] if p["id"] != uid]
            else:
                me.update(left=True, alive=False)
                state["actions"].pop(str(uid), None)
                invalidated = [actor for actor, action in state["actions"].items() if action["target"] == uid]
                for actor in invalidated:
                    state["actions"].pop(actor)
                    rules.player(state, int(actor))["choice_reset"] = state["phase_number"]
                if invalidated:
                    if state["phase"] == "paused":
                        state["remaining"] = min(state.get("phase_remaining", state["remaining"]), max(state["remaining"], 15))
                    else:
                        now = await repo.now(db)
                        full_deadline = state.get("phase_deadline", state["phase_started"] + rules.phase_seconds(state["tempo"], state["phase"]))
                        state["deadline"] = min(full_deadline, max(state["deadline"], now + 15))
            if not state["players"]:
                await engine.finish(db, state, reason="empty")
            elif state["phase"] not in rules.TERMINAL:
                if uid == state["host"]:
                    state["host"] = next((p["id"] for p in state["players"] if not p.get("left")), uid)
                    successor = rules.player(state, state["host"])
                    if successor:
                        successor["seen"] = await repo.now(db)
                await engine.notice(db, state, f"{rules.label(me)} покинул стол.")
                if state["phase"] != "lobby":
                    winner = rules.winner(p["role"] for p in state["players"] if p["alive"])
                    if winner:
                        await engine.finish(db, state, winner)
        else:
            if uid != state["host"]:
                raise rules.OnlineError("Это действие доступно хозяину стола.", 403)
            now = await repo.now(db)
            if command == "start" and state["phase"] == "lobby":
                if len(state["players"]) < 4:
                    raise rules.OnlineError("Нужно ещё игроков — за столом должно быть хотя бы четверо.")
                await engine.start(db, state, now)
            elif command == "settings" and state["phase"] == "lobby":
                config = settings(**options)
                if config["seats"] < len(state["players"]):
                    raise rules.OnlineError("Мест не может быть меньше, чем игроков за столом.")
                state.update(config)
            elif command == "cancel" and state["phase"] in rules.ACTIVE:
                await engine.finish(db, state, reason="host")
            elif command == "pause" and state["phase"] in ("night", "discussion", "voting"):
                full_deadline = state.get("phase_deadline", state["phase_started"] + rules.phase_seconds(state["tempo"], state["phase"]))
                state["phase_remaining"] = max(1, full_deadline - now)
                state.update(paused=state["phase"], remaining=max(1, state["deadline"] - now), phase="paused", deadline=now + 1200)
                await engine.notice(db, state, "Хозяин поставил игру на паузу.")
            elif command == "resume" and state["phase"] == "paused":
                state["phase_deadline"] = now + state.pop("phase_remaining", state["remaining"])
                state["phase_started"] = state["phase_deadline"] - rules.phase_seconds(state["tempo"], state["paused"])
                state.update(phase=state.pop("paused"), deadline=now + state.pop("remaining"))
                await engine.notice(db, state, "Игра продолжается.")
            elif command == "skip" and state["phase"] == "discussion" and phase_number == state["phase_number"]:
                state["deadline"] = now
                await engine.advance(db, state, now)
            else:
                raise rules.OnlineError("Этот этап уже изменился. Обновите стол.")
        await repo.save(db, state)
        result = {"ok": True, "replayed": False}
        if nonce:
            await repo.remember_command(db, room_id, uid, nonce, digest, result)
        return result


async def action(db, room_id, uid, phase_number, kind, target):
    async with db.connection.transaction():
        state = await locked(db, room_id)
        me = rules.player(state, uid)
        if not me or not me["alive"] or me.get("left"):
            raise rules.OnlineError("Этот ход доступен только живому участнику.", 403)
        if state["phase"] not in ("night", "voting") or state["phase_number"] != phase_number:
            raise rules.OnlineError("Этап уже закончился. Выберите действие заново.")
        expected = "vote" if state["phase"] == "voting" else rules.night_action_for(me["role"])
        if not expected or kind != expected:
            raise rules.OnlineError("У вашей роли сейчас нет такого действия.", 403)
        chosen = rules.player(state, target) if target else None
        if target is not None and (not chosen or not chosen["alive"]):
            raise rules.OnlineError("Этот игрок уже выбыл.")
        if target is None and kind != "vote":
            raise rules.OnlineError("Выберите игрока.")
        if chosen and ((kind == "mafia_target" and chosen["role"] in ("mafia", "don")) or
                       (kind in ("vote", "detective_check") and target == uid)):
            raise rules.OnlineError("Выберите другого игрока.")
        previous = state["actions"].get(str(uid))
        if previous and previous["kind"] == kind and previous["target"] == target:
            return  # A lost response must not change a tie-break timestamp for the same choice.
        state["actions"][str(uid)] = {"kind": kind, "target": target, "time": await repo.now(db)}
        me["seen"] = await repo.now(db)
        me.pop("choice_reset", None)
        engine.shorten(state, await repo.now(db))
        await repo.save(db, state)
