"""Coin market tick clock. Pure arithmetic, no SQL.

Ticks are absolute indices persisted in history, orders and shorts. Until the
switch epoch a tick lasted LEGACY_SECONDS (index = epoch // 300). From the
switch on it lasts TICK_SECONDS, numbered on from the last legacy index, so
every stored tick keeps its meaning and the sequence never jumps or repeats.
"""
from __future__ import annotations

from dataclasses import dataclass

LEGACY_SECONDS = 300
TICK_SECONDS = 150
DAY_SECONDS = 86_400


@dataclass(frozen=True)
class Clock:
    switch_epoch: int
    base_tick: int

    def __post_init__(self) -> None:
        if self.switch_epoch % LEGACY_SECONDS or self.base_tick * LEGACY_SECONDS != self.switch_epoch:
            raise ValueError("Switch epoch must start a legacy tick.")


def tick_of(epoch: int, clock: Clock | None) -> int:
    """Index of the tick running at `epoch` (seconds)."""
    if clock is None or epoch < clock.switch_epoch:
        return epoch // LEGACY_SECONDS
    return clock.base_tick + (epoch - clock.switch_epoch) // TICK_SECONDS


def tick_at(tick: int, clock: Clock | None) -> int:
    """Epoch second at which `tick` starts."""
    if clock is None or tick <= clock.base_tick:
        return tick * LEGACY_SECONDS
    return clock.switch_epoch + (tick - clock.base_tick) * TICK_SECONDS


def ticks_back(tick: int, seconds: int, clock: Clock | None) -> int:
    """First tick of the window that ends at `tick` and spans `seconds`."""
    return max(0, tick_of(tick_at(tick, clock) - seconds, clock))


def rebased_expiry(expires_tick: int, clock: Clock) -> int:
    """Keep an order's wall-clock lifetime when the tick shortens."""
    if expires_tick <= clock.base_tick:
        return expires_tick
    return clock.base_tick + (expires_tick - clock.base_tick) * LEGACY_SECONDS // TICK_SECONDS
