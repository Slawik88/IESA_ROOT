"""FastAPI/notifications.py — in-process notification queue for WebSocket clients.

Since bot and FastAPI run in the same asyncio event loop (same process),
a plain dict of Queues works as the pub/sub bus. No Redis needed.

Usage (from bot scheduler):
    from FastAPI.notifications import notify
    await notify(user_id, {"type": "expedition_done", "pet": "Хомяк", "mora": 420})
"""
import asyncio

# user_id → asyncio.Queue
_queues: dict[int, asyncio.Queue] = {}


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
