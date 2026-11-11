"""«Крестики-нолики» с ботом прямо в сообщении: игрок — ❌ и ходит первым, бот — ⭕.

Ход приходит запросом `ttt:m:<клетка>:<доска>`. Доску присылает сам виджет: партия ни на что не играется (без
наград и ставок), поэтому сервер хранить её не обязан, но проверяет, что доска возможна и клетка свободна.
Бот играет почти без ошибок: изредка ошибается нарочно (MISTAKE_CHANCE), иначе у игрока не было бы шанса.
"""
from __future__ import annotations

import random
from functools import lru_cache

from services.widgets import Refused, Reply

EMPTY = "-" * 9
LINES = ((0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6))
MISTAKE_CHANCE = 0.25
_rng = random.Random()

SAMPLE = {"b": "xo-x-o--x", "w": "x", "l": "036"}


def winner(board: str) -> tuple[str, str]:
    """('x'|'o', линия) — победитель и его линия; ('d', '') — ничья; ('', '') — партия идёт."""
    for a, b, c in LINES:
        if board[a] != "-" and board[a] == board[b] == board[c]:
            return board[a], f"{a}{b}{c}"
    return ("d", "") if "-" not in board else ("", "")


@lru_cache(maxsize=8192)   # ограниченный общий кэш позиций, без данных игроков
def _score(board: str, turn: str) -> int:
    side, _ = winner(board)
    if side == "o":
        return 1
    if side == "x":
        return -1
    if side == "d":
        return 0
    scores = [_score(board[:i] + turn + board[i + 1:], "x" if turn == "o" else "o")
              for i in range(9) if board[i] == "-"]
    return max(scores) if turn == "o" else min(scores)


def bot_move(board: str) -> int:
    free = [i for i in range(9) if board[i] == "-"]
    for i in free:   # выигрыш в один ход бот не упускает никогда
        if winner(board[:i] + "o" + board[i + 1:])[0] == "o":
            return i
    if _rng.random() < MISTAKE_CHANCE:
        return _rng.choice(free)
    return max(free, key=lambda i: (_score(board[:i] + "o" + board[i + 1:], "x"), -abs(4 - i)))


def _view(board: str) -> dict:
    side, line = winner(board)
    out = {"b": board}
    if side:
        out.update(w=side, l=line)
    return out


async def state(db, user_id: int) -> dict:
    return _view(EMPTY)


async def act(db, user_id: int, verb: str, args: list[str]) -> Reply:
    if verb == "n":
        return Reply(_view(EMPTY), persist=True)
    if verb != "m" or len(args) != 2 or not args[0].isdigit():
        raise Refused("Этот виджет устарел. Попроси новый.")
    cell, board = int(args[0]), args[1]
    legal = len(board) == 9 and set(board) <= {"x", "o", "-"} and board.count("x") == board.count("o")
    if not legal or winner(board)[0]:
        raise Refused("Эта партия уже закончилась. Нажми «Новая партия».")
    if not 0 <= cell <= 8 or board[cell] != "-":
        raise Refused("Эта клетка уже занята.")
    board = board[:cell] + "x" + board[cell + 1:]
    if not winner(board)[0]:
        reply = bot_move(board)
        board = board[:reply] + "o" + board[reply + 1:]
    return Reply(_view(board), persist=True)
