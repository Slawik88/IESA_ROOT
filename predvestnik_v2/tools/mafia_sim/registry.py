"""Scenario registry: every scenario is an ``async def name(h: Harness)`` that asserts."""
from __future__ import annotations

from typing import Awaitable, Callable

SCENARIOS: dict[str, Callable[..., Awaitable[None]]] = {}
BOT_SCENARIOS: dict[str, Callable[..., Awaitable[None]]] = {}  # whole-bot suite (tools/test_bot_scenarios_sim_pg.py), kept apart from Mafia


def scenario(fn):
    SCENARIOS[fn.__name__] = fn
    return fn


VOLATILE: set[str] = set()   # whole-bot scenarios whose answers are random by design (they are checked, but not fingerprinted)


def bot_scenario(fn=None, *, volatile: bool = False):
    """``@bot_scenario`` or ``@bot_scenario(volatile=True)`` for answers that legitimately differ on every run."""
    def register(function):
        BOT_SCENARIOS[function.__name__] = function
        if volatile:
            VOLATILE.add(function.__name__)
        return function
    return register(fn) if fn is not None else register


def ok(condition: object, message: str) -> None:
    """Assertion with a readable story: what the player should have seen."""
    if not condition:
        raise AssertionError(message)
