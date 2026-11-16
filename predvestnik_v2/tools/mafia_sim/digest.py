"""A comparable fingerprint of what the bot did: every outgoing Telegram call, normalised and hashed.

The point of the whole-bot suite is to say «the same scenarios give the same result before and after» a library
bump (S23a) or a bot change.  Fingerprints therefore ignore what legitimately differs between runs — the ids a run
happens to use, clocks, aiogram's ``Default`` placeholders — and keep everything a player could see: methods,
texts, buttons, targets, topics, answers to Telegram.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from enum import Enum
from typing import Any

from tools.mafia_sim.world import World

_ID_KEYS = {"message_id", "message_ids", "reply_to_message_id", "message_thread_id", "pre_checkout_query_id", "callback_query_id"}
_CLOCK = re.compile(r"\b[0-2]\d:[0-5]\d(:[0-5]\d)?\b")
_RUN_IDS = re.compile(r"(?<=sim-photo-)\d+|(?<=mf:)\d+|(?<=start=mj)\d+")   # file id, Mafia lobby/match id, join link


def _plain(value: Any) -> Any:
    """JSON-friendly copy; drops aiogram's ``Default`` placeholders and unset values."""
    if hasattr(value, "model_dump"):
        return _plain(value.model_dump(exclude_none=True))   # python mode: aiogram's Default placeholders cannot be JSON-dumped
    if isinstance(value, Enum):
        return _plain(value.value)
    if isinstance(value, (date, datetime)):
        return "<time>"
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items() if v is not None and type(v).__name__ != "Default"}
    if isinstance(value, (list, tuple, set)):
        return [_plain(v) for v in (sorted(value, key=str) if isinstance(value, set) else value)]
    if type(value).__name__ == "Default":
        return None
    if isinstance(value, (bytes, bytearray)) or hasattr(value, "read") or type(value).__name__.endswith("InputFile"):
        return "<file>"
    return value if isinstance(value, (str, int, float, bool)) else str(value)


def calls_since(world: World, start: int) -> list[list[Any]]:
    calls = [[name, _plain(params)] for name, params in world.calls[start:]]
    for name, params in calls:
        for key in ("until_date", "date", "expire_date"):
            if key in params:
                params[key] = "<time>"
    return calls


def canonical(calls: list[list[Any]], labels: dict[int, str]) -> str:
    """JSON text with run-specific ids replaced by stable labels (users, chats) and first-seen order (messages)."""
    ordered = sorted(labels.items(), key=lambda kv: -len(str(abs(kv[0]))))
    seen: dict[int, str] = {}

    def relabel(node: Any, key: str = "") -> Any:
        if isinstance(node, dict):
            return {k: relabel(v, k) for k, v in node.items()}
        if isinstance(node, list):
            return [relabel(v, key) for v in node]
        if isinstance(node, bool):
            return node
        if isinstance(node, int):
            if node in labels:
                return labels[node]
            return seen.setdefault(node, f"#{len(seen) + 1}") if key in _ID_KEYS else node
        if isinstance(node, str):
            for number, label in ordered:
                node = node.replace(str(number), label)
            return _RUN_IDS.sub("<n>", _CLOCK.sub("<clock>", node))
        return node

    return json.dumps(relabel(calls), ensure_ascii=False, sort_keys=True, indent=0)


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
