"""Short-lived snapshot of GET /profile/me per player (S04).

The own profile costs ~35 SQL statements and the Mini App reads it on open, after each change and on live events.
A snapshot lives SNAPSHOT_SEC seconds and is forgotten as soon as the player changes something: after any of their
non-GET requests (FastAPI.deps.get_db) and on any live event about them (FastAPI.notifications.notify). A read that
started before such a change stores its result under the old generation, which is never read again.
The body is kept already encoded, with its ETag: an unchanged profile answers 304 without a body.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from core.ttl_cache import TtlCache

SNAPSHOT_SEC = 8
MAX_PLAYERS = 1024   # only profiles read in the last SNAPSHOT_SEC stay: expired ones are dropped on put
_MAX_GENERATIONS = 100_000

_snapshots = TtlCache(SNAPSHOT_SEC, max_entries=MAX_PLAYERS)
_generations: dict[int, int] = {}
_epoch = 0   # bumped when the generation table is reset: keys from before the reset are never read again


@dataclass(frozen=True)
class Snapshot:
    body: bytes
    etag: str


def key(user_id: int) -> tuple[int, int, int]:
    """Take it before reading the database; store the result under it."""
    return int(user_id), _epoch, _generations.get(int(user_id), 0)


def get(snapshot_key: tuple[int, int, int]) -> Snapshot | None:
    return _snapshots.get(snapshot_key)


def put(snapshot_key: tuple[int, int, int], body: bytes) -> Snapshot:
    snapshot = Snapshot(body, f'"{hashlib.sha256(body).hexdigest()[:32]}"')
    _snapshots.put(snapshot_key, snapshot)
    return snapshot


def forget(user_id: int) -> None:
    global _epoch
    if not user_id:
        return
    if len(_generations) >= _MAX_GENERATIONS:
        _generations.clear()
        _snapshots.clear()
        _epoch += 1
    _generations[int(user_id)] = _generations.get(int(user_id), 0) + 1


def reset() -> None:   # tests
    _generations.clear()
    _snapshots.clear()
