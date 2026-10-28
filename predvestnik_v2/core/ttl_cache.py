"""Short-lived in-process memo for hot read-only answers (message tops, the own profile).

Bot and Mini App run in one process, so a write anywhere can drop an entry here directly.
"""
from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Hashable


class TtlCache:
    """Values live `ttl` seconds; expired entries and, past `max_entries`, the oldest ones are dropped on put."""

    def __init__(self, ttl: float, max_entries: int) -> None:
        self.ttl = float(ttl)
        self.max_entries = int(max_entries)
        self._entries: OrderedDict[Hashable, tuple[float, Any]] = OrderedDict()

    def get(self, key: Hashable, now: float | None = None) -> Any | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry[0] <= (time.monotonic() if now is None else now):
            del self._entries[key]
            return None
        return entry[1]

    def put(self, key: Hashable, value: Any, now: float | None = None) -> None:
        self._entries.pop(key, None)
        moment = time.monotonic() if now is None else now
        self._entries[key] = (moment + self.ttl, value)
        # One TTL for all and insertion order kept: the front is always the entry that expires first.
        while self._entries and (len(self._entries) > self.max_entries or next(iter(self._entries.values()))[0] <= moment):
            self._entries.popitem(last=False)

    def drop(self, key: Hashable) -> None:
        self._entries.pop(key, None)

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
