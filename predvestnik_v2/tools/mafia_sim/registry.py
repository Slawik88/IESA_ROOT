"""Scenario registry: every scenario is an ``async def name(h: Harness)`` that asserts."""
from __future__ import annotations

from typing import Awaitable, Callable

SCENARIOS: dict[str, Callable[..., Awaitable[None]]] = {}


def scenario(fn):
    SCENARIOS[fn.__name__] = fn
    return fn


def ok(condition: object, message: str) -> None:
    """Assertion with a readable story: what the player should have seen."""
    if not condition:
        raise AssertionError(message)
