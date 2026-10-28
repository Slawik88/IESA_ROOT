"""FastAPI/notifications.py — in-process notification queue for WebSocket clients.

Since bot and FastAPI run in the same asyncio event loop (same process),
a plain dict of Queues works as the pub/sub bus. No Redis needed.

Usage (from bot scheduler):
    from FastAPI.notifications import notify
    await notify(user_id, {"type": "expedition_done", "pet": "Хомяк", "mora": 420})

ws_session() — ПОЛНЫЙ протокол WS-сессии: сервер только отправляет события,
от клиента принимается лишь keep-alive "ping". Live-комнаты лотов старого
аукциона удалены вместе с аукционом (audit A03): клиент их не использовал, а
команды комнат позволяли бесконечно наращивать память процесса.
"""
import asyncio
import json

from loguru import logger

from FastAPI import profile_snapshot

# user_id → queues of every open tab/device for this account
_queues: dict[int, set[asyncio.Queue]] = {}

# Per-connection backlog cap. A client that stops reading is disconnected
# instead of letting its queue grow without bound; it reconnects with backoff.
WS_QUEUE_MAXSIZE = 256


class _ClientQueue(asyncio.Queue):
    """Bounded queue of one WS connection; `overflowed` fires when it is dropped."""

    def __init__(self) -> None:
        super().__init__(maxsize=WS_QUEUE_MAXSIZE)
        self.overflowed = asyncio.Event()


_balance_listener_task: asyncio.Task | None = None
_balance_listener_lock = asyncio.Lock()
_balance_listener_ready = asyncio.Event()


# Waits between reconnect attempts of the LISTEN connection (the last one repeats).
LISTENER_RETRY_SEC = (1.0, 2.0, 5.0, 10.0, 30.0)


async def _balance_listener() -> None:
    """Bridge transactional PostgreSQL player events to local WS queues.

    Every application process listens to the same channel. Only the process
    holding a user's WebSocket has a matching queue, so no shared Redis bus or
    periodic profile reads are needed.

    LISTEN lives on its own connection outside the pool (it used to occupy a
    pool slot for good). When that connection drops (database restart,
    network), the listener reconnects with a growing pause; events sent while
    it is down are not replayed — the next change refreshes the screen.
    """
    from infrastructure.database import connect_direct, create_pool
    from infrastructure.pg_adapter import PGAdapter
    from infrastructure.repositories import balance_events

    def on_balance(_connection, _pid, _channel, payload: str) -> None:
        try:
            event = json.loads(payload)
            user_id = int(event.pop("user_id"))
            if event.get("type") in {
                "balance_changed", "data_changed", "notification_pending"
            }:
                asyncio.create_task(notify(user_id, event))
        except Exception as exc:
            logger.warning(f"balance event ignored: {exc}")

    await create_pool()   # chooses the database source the direct connection reuses
    failures = 0
    while True:
        conn = None
        lost = asyncio.Event()
        try:
            conn = await connect_direct()
            await balance_events.ensure_schema(PGAdapter(conn))
            conn.add_termination_listener(lambda _conn: lost.set())
            await conn.add_listener(balance_events.CHANNEL, on_balance)
            _balance_listener_ready.set()
            failures = 0
            await lost.wait()
            logger.warning("player event listener connection lost; reconnecting")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"player event listener failed: {type(exc).__name__}: {exc}")
        finally:
            _balance_listener_ready.clear()
            if conn is not None and not conn.is_closed():
                conn.terminate()   # a half-open socket must not stall the reconnect loop
        await asyncio.sleep(LISTENER_RETRY_SEC[min(failures, len(LISTENER_RETRY_SEC) - 1)])
        failures += 1


async def ensure_balance_listener() -> bool:
    """Start one lazy dedicated LISTEN connection per application process."""
    global _balance_listener_task
    if not _balance_listener_task or _balance_listener_task.done():
        async with _balance_listener_lock:
            if not _balance_listener_task or _balance_listener_task.done():
                _balance_listener_ready.clear()
                _balance_listener_task = asyncio.create_task(
                    _balance_listener(), name="predvestnik:balance-events"
                )

                def report_failure(task: asyncio.Task) -> None:
                    if task.cancelled():
                        return
                    exc = task.exception()
                    if exc:
                        logger.error(f"player event listener stopped: {exc}")

                _balance_listener_task.add_done_callback(report_failure)
    try:
        await asyncio.wait_for(_balance_listener_ready.wait(), timeout=8.0)
        return True
    except asyncio.TimeoutError:
        logger.warning("player event listener startup timed out; WebSocket stays available")
        return False


async def notify(user_id: int, event: dict) -> bool:
    """Доставить событие подключённому WS-клиенту. Возвращает True, если клиент
    онлайн (событие отправлено), иначе False — вызывающий может сохранить его в
    web_notifications для показа при следующем входе (Welcome Back)."""
    profile_snapshot.forget(user_id)   # live event about the player: their profile snapshot is no longer current
    queues = tuple(_queues.get(user_id, ()))
    delivered = False
    for q in queues:
        try:
            q.put_nowait(event)
            delivered = True
        except asyncio.QueueFull:
            # Slow or stalled reader: drop this connection, keep the others.
            unregister(user_id, q)
            overflowed = getattr(q, "overflowed", None)
            if overflowed is not None:
                overflowed.set()
            logger.warning(f"WS queue overflow for user {user_id}: connection dropped")
    return delivered


def register(user_id: int, q: asyncio.Queue) -> None:
    _queues.setdefault(user_id, set()).add(q)


def unregister(user_id: int, q: asyncio.Queue | None = None) -> None:
    if q is None:
        _queues.pop(user_id, None)
        return
    queues = _queues.get(user_id)
    if not queues:
        return
    queues.discard(q)
    if not queues:
        _queues.pop(user_id, None)


async def ws_session(websocket, user_id: int, *, app_version: str = "",
                     still_allowed=None, recheck_sec: float = 300.0) -> None:
    """Полный жизненный цикл WS-сессии ПОСЛЕ accept(): параллельно шлём события
    из очереди и читаем keep-alive клиента. Выход по разрыву соединения или
    переполнению очереди; unregister гарантирован. still_allowed() повторно
    проверяет допуск аккаунта раз в recheck_sec (audit A06)."""
    q = _ClientQueue()
    register(user_id, q)
    q.put_nowait({"type": "app_version", "version": str(app_version)})
    if await ensure_balance_listener():
        q.put_nowait({"type": "balance_stream_ready"})

    async def _sender():
        while True:
            event = await q.get()
            await websocket.send_json(event)

    async def _receiver():
        while True:
            await websocket.receive_text()   # keep-alive "ping"; nothing is stored

    async def _watchdog():
        while True:
            await asyncio.sleep(recheck_sec)
            if not await still_allowed():
                return

    sender = asyncio.create_task(_sender())
    receiver = asyncio.create_task(_receiver())
    overflow = asyncio.create_task(q.overflowed.wait())
    tasks = {sender, receiver, overflow}
    watchdog = asyncio.create_task(_watchdog()) if still_allowed else None
    if watchdog:
        tasks.add(watchdog)
    try:
        # Любой из тасков падает при разрыве соединения — завершаем сессию
        _done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        close_code = None
        if overflow in _done:
            close_code = 1013   # try again later: client reconnects
        elif watchdog in _done and not watchdog.cancelled() and watchdog.exception() is None:
            close_code = 1008   # account no longer allowed
        if close_code:
            try:
                # a dead peer must not hold the session
                await asyncio.wait_for(websocket.close(code=close_code), 2)
            except Exception:
                pass
    finally:
        for task in tasks:
            task.cancel()
        unregister(user_id, q)
