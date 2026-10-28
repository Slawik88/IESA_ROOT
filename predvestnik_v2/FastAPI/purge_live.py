"""Live progress of «Чистка» for the screens that watch it (roadmap S05).

A screen that reads a chat's purge with ``live=1`` becomes its viewer for VIEWER_SEC (every read renews it). Any change
of that purge (dossier sent, decision, start, finish) pushes ``data_changed{scope:'purge'}`` over the existing WebSocket
to its viewers instead of a poll every 2 s. Pushes for one chat are merged: at most one per PUSH_EVERY_SEC, the first at
once, the rest at the end of the pause. Screens that never asked for live events (the purge screen before S05) get none.
Bot and Mini App share one process, so a change anywhere reaches the viewers directly.
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger

VIEWER_SEC = 90.0
PUSH_EVERY_SEC = 1.0
MAX_VIEWERS_PER_CHAT = 50

_viewers: dict[int, dict[int, float]] = {}   # chat → viewer → monotonic deadline
_revisions: dict[int, int] = {}
_last_push: dict[int, float] = {}
_scheduled: dict[int, asyncio.TimerHandle] = {}
_pushing: set[asyncio.Task] = set()   # running pushes, kept so they are not garbage-collected mid-way


def watch(chat_id: int, user_id: int) -> None:
    now = time.monotonic()
    viewers = {uid: until for uid, until in _viewers.get(int(chat_id), {}).items() if until > now}
    viewers[int(user_id)] = now + VIEWER_SEC
    while len(viewers) > MAX_VIEWERS_PER_CHAT:
        viewers.pop(min(viewers, key=viewers.get))
    _viewers[int(chat_id)] = viewers


def unwatch(chat_id: int, user_id: int) -> None:
    viewers = _viewers.get(int(chat_id))
    if viewers:
        viewers.pop(int(user_id), None)
        if not viewers:
            _viewers.pop(int(chat_id), None)


def revision(chat_id: int) -> int:
    return _revisions.get(int(chat_id), 0)


def changed(chat_id: int) -> None:
    """Something in this chat's purge changed: bump its revision and tell the viewers (merged, see module doc)."""
    cid = int(chat_id)
    if cid not in _viewers:   # nobody watches: no revision to keep
        _revisions.pop(cid, None)
        return
    _revisions[cid] = _revisions.get(cid, 0) + 1
    if cid in _scheduled:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:   # called outside the event loop (scripts): nobody can be watching
        return
    wait = _last_push.get(cid, 0.0) + PUSH_EVERY_SEC - time.monotonic()
    _scheduled[cid] = loop.call_later(max(0.0, wait), _start_push, loop, cid)


def _start_push(loop: asyncio.AbstractEventLoop, chat_id: int) -> None:
    task = loop.create_task(_push(chat_id), name=f"predvestnik:purge-live:{chat_id}")
    _pushing.add(task)
    task.add_done_callback(_pushing.discard)


async def _push(chat_id: int) -> None:
    _scheduled.pop(chat_id, None)
    _last_push[chat_id] = time.monotonic()
    from FastAPI.notifications import notify
    now = time.monotonic()
    viewers = [uid for uid, until in _viewers.get(chat_id, {}).items() if until > now]
    if not viewers:
        _viewers.pop(chat_id, None)
        _last_push.pop(chat_id, None)
        _revisions.pop(chat_id, None)
        return
    event = {"type": "data_changed", "scope": "purge", "chat_id": chat_id, "revision": revision(chat_id)}
    for uid in viewers:
        try:
            await notify(uid, event, forget_profile=False)
        except Exception as error:   # a live hint is optional: the screen still has its slow fallback poll
            logger.warning("purge live push to {} failed: {}", uid, type(error).__name__)


def reset() -> None:   # tests
    for handle in _scheduled.values():
        handle.cancel()
    _viewers.clear()
    _revisions.clear()
    _last_push.clear()
    _scheduled.clear()
