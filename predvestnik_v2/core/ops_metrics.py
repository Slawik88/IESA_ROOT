"""In-process operational metrics: timings in fixed buckets and plain counters.

Pure data structures without I/O. Writers (HTTP middleware, pool, bot throttler,
auth) call ``observe``/``count``; the health service drains the current window
every few minutes into the database (``services/ops_health.py``).

Timings are stored as counts per fixed bucket, not raw samples: memory per series
is constant, windows can be summed exactly, and a percentile over any period is
read from the summed buckets (an upper-bound estimate, good enough for alerts).
"""
from __future__ import annotations

import bisect
import math
import time
from dataclasses import dataclass, field

# Upper bounds of timing buckets, milliseconds. The last bucket is "slower than 30 s".
BUCKETS_MS: tuple[float, ...] = (
    1, 2, 5, 10, 20, 50, 100, 200, 300, 500, 750,
    1000, 1500, 2000, 3000, 5000, 10000, 20000, 30000,
)
OVERFLOW_NAME = "__other__"
MAX_SERIES = 600   # distinct (kind, name) per window; beyond it values merge into OVERFLOW_NAME


@dataclass
class Series:
    count: int = 0
    total: float = 0.0
    peak: float = 0.0
    buckets: list[int] = field(default_factory=lambda: [0] * (len(BUCKETS_MS) + 1))

    def add(self, value: float) -> None:
        value = max(0.0, float(value))
        self.count += 1
        self.total += value
        self.peak = max(self.peak, value)
        self.buckets[bisect.bisect_left(BUCKETS_MS, value)] += 1

    def merge(self, other: "Series") -> None:
        self.count += other.count
        self.total += other.total
        self.peak = max(self.peak, other.peak)
        self.buckets = [a + b for a, b in zip(self.buckets, other.buckets)]


def percentile(buckets: list[int], q: float, peak: float | None = None) -> float:
    """Upper bound of the bucket holding the q-quantile; the overflow bucket reports ``peak``."""
    total = sum(buckets)
    if not total:
        return 0.0
    rank = max(1, math.ceil(q * total))
    seen = 0
    for index, amount in enumerate(buckets):
        seen += amount
        if seen >= rank:
            if index < len(BUCKETS_MS):
                bound = float(BUCKETS_MS[index])
                return min(bound, peak) if peak is not None and peak > 0 else bound
            return float(peak if peak is not None else BUCKETS_MS[-1])
    return float(peak or 0.0)


@dataclass
class Window:
    """Everything observed since the last drain."""
    started: float = field(default_factory=time.time)
    timings: dict[tuple[str, str], Series] = field(default_factory=dict)
    counters: dict[tuple[str, str], int] = field(default_factory=dict)

    def _key(self, kind: str, name: str, table: dict) -> tuple[str, str]:
        key = (kind, name[:120])
        if key in table or len(self.timings) + len(self.counters) < MAX_SERIES:
            return key
        return (kind, OVERFLOW_NAME)


class Registry:
    """One per process. Single-threaded asyncio: no locks needed."""

    def __init__(self) -> None:
        self.window = Window()

    def observe(self, kind: str, name: str, value_ms: float) -> None:
        key = self.window._key(kind, name, self.window.timings)
        series = self.window.timings.get(key)
        if series is None:
            series = self.window.timings[key] = Series()
        series.add(value_ms)

    def count(self, kind: str, name: str, amount: int = 1) -> None:
        key = self.window._key(kind, name, self.window.counters)
        self.window.counters[key] = self.window.counters.get(key, 0) + amount

    def drain(self) -> Window:
        """Hand over the current window and start a new one."""
        done, self.window = self.window, Window()
        return done

    def restore(self, window: Window) -> None:
        """Put a drained window back (its write failed), so the numbers are not lost."""
        for key, series in window.timings.items():
            self.window.timings.setdefault(key, Series()).merge(series)
        for key, amount in window.counters.items():
            self.window.counters[key] = self.window.counters.get(key, 0) + amount


registry = Registry()
observe = registry.observe
count = registry.count
