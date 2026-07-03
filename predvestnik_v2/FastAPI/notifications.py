"""FastAPI/notifications.py — in-process notification queue for WebSocket clients.

Since bot and FastAPI run in the same asyncio event loop (same process),
a plain dict of Queues works as the pub/sub bus. No Redis needed.

Usage (from bot scheduler):
    from FastAPI.notifications import notify
    await notify(user_id, {"type": "expedition_done", "pet": "Хомяк", "mora": 420})

R5 «Молот Аукциона»: сюда же добавлены live-комнаты лотов (in-memory) и единая
ws_session() — ПОЛНЫЙ протокол WS-сессии (отправка событий + чтение команд
sub_lot/unsub_lot/lot_react). main.py и локальный тест-сервер используют одну
и ту же функцию, чтобы протокол не расползался между продом и тестами.
"""
import asyncio
import time

# user_id → asyncio.Queue
_queues: dict[int, asyncio.Queue] = {}

# R5: lot_id → set[user_id] — зрители live-комнаты финала лота
_lot_rooms: dict[int, set[int]] = {}
# (user_id, lot_id) → monotonic-время последней реакции (анти-спам жабы)
_react_last: dict[tuple[int, int], float] = {}
_REACT_MIN_INTERVAL_SEC = 2.0


async def notify(user_id: int, event: dict) -> bool:
    """Доставить событие подключённому WS-клиенту. Возвращает True, если клиент
    онлайн (событие отправлено), иначе False — вызывающий может сохранить его в
    web_notifications для показа при следующем входе (Welcome Back)."""
    q = _queues.get(user_id)
    if q:
        await q.put(event)
        return True
    return False


def register(user_id: int, q: asyncio.Queue) -> None:
    _queues[user_id] = q


def unregister(user_id: int) -> None:
    _queues.pop(user_id, None)


# ── R5: live-комнаты лотов ─────────────────────────────────────────────────────

def lot_viewers(lot_id: int) -> int:
    return len(_lot_rooms.get(lot_id, ()))


async def broadcast_lot(lot_id: int, event: dict) -> None:
    """Разослать событие всем зрителям комнаты лота (кто офлайн — просто мимо)."""
    for uid in list(_lot_rooms.get(lot_id, ())):
        await notify(uid, event)


async def _join_lot(lot_id: int, user_id: int) -> None:
    room = _lot_rooms.setdefault(lot_id, set())
    if user_id in room:
        return
    room.add(user_id)
    await broadcast_lot(lot_id, {"type": "lot_viewers", "lot_id": lot_id,
                                 "viewers": len(room)})


async def _leave_lot(lot_id: int, user_id: int) -> None:
    room = _lot_rooms.get(lot_id)
    if not room or user_id not in room:
        return
    room.discard(user_id)
    if room:
        await broadcast_lot(lot_id, {"type": "lot_viewers", "lot_id": lot_id,
                                     "viewers": len(room)})
    else:
        _lot_rooms.pop(lot_id, None)


async def _leave_all(user_id: int) -> None:
    for lot_id in [lid for lid, room in _lot_rooms.items() if user_id in room]:
        await _leave_lot(lot_id, user_id)


async def _handle_client_message(user_id: int, raw: str) -> None:
    """Входящее сообщение клиента: ping (keep-alive) или JSON-команда комнаты."""
    if raw == "ping":
        return
    import json
    try:
        msg = json.loads(raw)
    except Exception:
        return
    t = msg.get("type")
    lot_id = int(msg.get("lot_id") or 0)
    if not lot_id:
        return
    if t == "sub_lot":
        await _join_lot(lot_id, user_id)
    elif t == "unsub_lot":
        await _leave_lot(lot_id, user_id)
    elif t == "lot_react":
        # Зрительская реакция (🐸) — рейт-лимит 1/2с на пару (юзер, лот)
        key = (user_id, lot_id)
        now = time.monotonic()
        if now - _react_last.get(key, 0.0) < _REACT_MIN_INTERVAL_SEC:
            return
        _react_last[key] = now
        if user_id in _lot_rooms.get(lot_id, ()):   # реагируют только зрители
            emoji = str(msg.get("emoji") or "🐸")[:4]
            await broadcast_lot(lot_id, {"type": "lot_react", "lot_id": lot_id,
                                         "emoji": emoji, "from": user_id})


async def ws_session(websocket, user_id: int) -> None:
    """Полный жизненный цикл WS-сессии ПОСЛЕ accept(): параллельно шлём события
    из очереди и читаем команды клиента. Выход по разрыву соединения; чистка
    (unregister + выход из всех комнат) гарантирована."""
    q: asyncio.Queue = asyncio.Queue()
    register(user_id, q)

    async def _sender():
        while True:
            event = await q.get()
            await websocket.send_json(event)

    async def _receiver():
        while True:
            raw = await websocket.receive_text()
            await _handle_client_message(user_id, raw)

    sender = asyncio.create_task(_sender())
    receiver = asyncio.create_task(_receiver())
    try:
        # Любой из тасков падает при разрыве соединения — завершаем сессию
        _done, pending = await asyncio.wait(
            {sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
    finally:
        sender.cancel()
        receiver.cancel()
        unregister(user_id)
        await _leave_all(user_id)