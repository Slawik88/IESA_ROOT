"""Room chat: membership/phase checks inside the lock, idempotent sends and moderation."""
from core import mafia_online as rules
from infrastructure.repositories import mafia_online as repo
from services.mafia_online import locked


async def send(db, room_id, uid, channel, text, nonce, reply_to=None):
    text = text.strip()
    if not text or len(text) > rules.MAX_CHAT or any(ord(c) < 32 and c not in "\n\t" for c in text):
        raise rules.OnlineError("Сообщение — от 1 до 600 знаков.", 422)
    async with db.connection.transaction():
        state = await locked(db, room_id)
        me = rules.player(state, uid)
        if not me or me.get("left"):
            raise rules.OnlineError("Разговор доступен участникам этого стола.", 403)
        previous = await repo.duplicate(db, room_id, uid, nonce)
        if previous:
            return {"id": previous, "replayed": True}
        if channel not in rules.channels(state, me) or not rules.can_write(state, me, channel):
            raise rules.OnlineError("Сейчас в этом разговоре писать нельзя.", 403)
        now = await repo.now(db)
        last = await repo.last_message_at(db, uid)
        if last and now - last < 1.5:
            raise rules.OnlineError("Секунду — дайте другим ответить.", 429)
        if reply_to:
            parent = await repo.get_message(db, reply_to)
            if not parent or parent["room_id"] != room_id or parent["channel"] != channel or parent["hidden"]:
                raise rules.OnlineError("Это сообщение больше недоступно для ответа.")
        msg_id = await repo.message(db, room_id, channel, text, user_id=uid, name=me["name"], nonce=nonce, reply_to=reply_to, seat=me.get("seat"))
        return {"id": msg_id, "replayed": False}


async def moderate(db, room_id, uid, kind, target=None, message_id=None, reason="", staff=False):
    async with db.connection.transaction():
        state = await locked(db, room_id)
        me = rules.player(state, uid)
        msg = await repo.get_message(db, message_id) if message_id else None
        if message_id and (not msg or msg["room_id"] != room_id):
            raise rules.OnlineError("Сообщение не найдено.", 404)
        if kind == "report":
            if not me or not msg or msg["channel"] not in rules.channels(state, me) or msg["user_id"] is None:
                raise rules.OnlineError("Это сообщение недоступно.", 403)
            await repo.report(db, message_id, uid, reason.strip()[:200] or "Нарушение в разговоре")
            return
        if not staff and (not me or me.get("left") or uid != state["host"]):
            raise rules.OnlineError("Разговором управляет хозяин стола.", 403)
        if kind == "hide" and msg:
            if msg["user_id"] is None:
                raise rules.OnlineError("Системные сообщения скрывать нельзя.")
            if not staff and msg["channel"] not in rules.channels(state, me):
                raise rules.OnlineError("Этот разговор недоступен.", 403)
            await repo.hide(db, message_id)
            state["redactions"] = state.get("redactions", 0) + 1
        elif kind in ("mute", "unmute") and (rules.player(state, target) or str(target) in state.get("restrictions", {})):
            person = rules.player(state, target) or state["restrictions"][str(target)]
            if not staff and kind == "unmute" and person.get("staff_muted"):
                raise rules.OnlineError("Это ограничение снимает персонал бота.", 403)
            person["staff_muted" if staff else "muted"] = kind == "mute"
            if staff and kind == "unmute":
                person["muted"] = False
            state.setdefault("restrictions", {})[str(target)] = {k: bool(person.get(k)) for k in ("muted", "staff_muted")}
        else:
            raise rules.OnlineError("Выберите сообщение или игрока.")
        await repo.save(db, state)
