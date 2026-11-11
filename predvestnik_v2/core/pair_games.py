"""Игры вдвоём в личной переписке (S29a): камень-ножницы-бумага, дуэль кубиков, крестики-нолики. Чистые правила.

Состояние партии — словарь (хранится в базе как JSON). Ходы присылают два игрока: «owner» (подключил бота) и «partner»
(его собеседник). Ставка — жетоны казино из одного фонда (бесплатные или купленные): игра денег не создаёт, победитель
получает обе ставки, при ничьей ставки возвращаются.
"""
from __future__ import annotations

from typing import Final

KINDS: Final[dict[str, str]] = {"rps": "✊ Камень, ножницы, бумага", "dice": "🎲 Дуэль кубиков", "ttt": "❌ Крестики-нолики"}
STAKES: Final = (10, 50, 100, 500)            # кнопки ставок на пульте; «без ставки» — 0
FUND_TITLES: Final = {"bonus": "бесплатных жетонов", "redeemable": "купленных жетонов"}
EXPIRE_HOURS: Final = 24                      # без хода дольше — партия отменяется, ставки возвращаются
XP: Final = 20                                # опыт Пропуска каждому за сыгранную партию (общий дневной предел обычных игр)
SIDES: Final = ("owner", "partner")

RPS: Final = {"r": "🪨 Камень", "s": "✂️ Ножницы", "p": "📄 Бумага"}
_BEATS: Final = {"r": "s", "s": "p", "p": "r"}
LINES: Final = ((0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6))
MARKS: Final = {"owner": "❌", "partner": "⭕"}


class MoveError(ValueError):
    """Ход не принят: понятная игроку причина (показывается всплывающим окном)."""


def other(side: str) -> str:
    return "partner" if side == "owner" else "owner"


def new_state(kind: str, first: str) -> dict:
    if kind not in KINDS:
        raise ValueError(kind)
    if kind == "ttt":
        return {"board": [""] * 9, "turn": first}
    return {"moves": {}, "round": 1, "last": None}


def move(kind: str, state: dict, side: str, value: str, *, roll: int | None = None) -> tuple[dict, str | None]:
    """Принять ход. Возвращает (новое состояние, итог): None — игра идёт, 'owner'/'partner' — победитель, 'draw' — ничья.
    Для кубиков value игнорируется: выпавшее число передаёт сервис (roll 1–6)."""
    state = {**state, **({"moves": dict(state["moves"])} if "moves" in state else {}),
             **({"board": list(state["board"])} if "board" in state else {})}
    if kind == "rps":
        if value not in RPS:
            raise MoveError("Такого хода нет.")
        return _two_secret(state, side, value, lambda a, b: "draw" if a == b else ("owner" if _BEATS[a] == b else "partner"))
    if kind == "dice":
        if roll is None or not 1 <= int(roll) <= 6:
            raise ValueError("roll must be 1..6")
        return _two_secret(state, side, int(roll), lambda a, b: "draw" if a == b else ("owner" if a > b else "partner"))
    if kind == "ttt":
        if state["turn"] != side:
            raise MoveError("Сейчас ход соперника.")
        if not value.isdigit() or not 0 <= int(value) <= 8 or state["board"][int(value)]:
            raise MoveError("Эта клетка уже занята.")
        state["board"][int(value)] = side
        won = next((state["board"][a] for a, b, c in LINES if state["board"][a] and state["board"][a] == state["board"][b] == state["board"][c]), None)
        if won:
            return state, won
        if all(state["board"]):
            return state, "draw"
        state["turn"] = other(side)
        return state, None
    raise ValueError(kind)


def _two_secret(state: dict, side: str, value, judge) -> tuple[dict, str | None]:
    """Оба делают ход втайне; когда походили оба — итог. Ничья — новый раунд с теми же ставками."""
    if side in state["moves"]:
        raise MoveError("Ты уже походил. Ждём соперника.")
    state["moves"][side] = value
    if len(state["moves"]) < 2:
        return state, None
    result = judge(state["moves"]["owner"], state["moves"]["partner"])
    if result == "draw":
        return {**state, "moves": {}, "round": state["round"] + 1, "last": dict(state["moves"])}, None
    return {**state, "last": dict(state["moves"])}, result


def forfeit(kind: str, state: dict) -> str | None:
    """Кто выигрывает партию, брошенную на сутки: в крестиках-ноликах после первого хода — соперник того, чей ход;
    в остальных играх ходы скрыты до конца раунда, затягивать незачем — ничья (ставки возвращаются)."""
    if kind == "ttt" and any(state.get("board") or []):
        return other(state["turn"])
    return None


def settle(stake: int, result: str) -> dict[str, int]:
    """Сколько жетонов вернуть каждой стороне по итогу (ставки обоих уже списаны)."""
    if result == "draw":
        return {"owner": stake, "partner": stake}
    return {result: 2 * stake, other(result): 0}
