# services/alchemy.py — R7.2 «Алхимия»: merge-2048 4×4 на 60 секунд.
#
# Server-authoritative через РЕПЛЕЙ: сервер выдаёт seed, клиент играет локально
# (та же детерминированная симуляция на JS — app.04.js), шлёт лог ходов;
# сервер реплеит симуляцию и сам вычисляет счёт. Любое расхождение клиентского
# «нарисованного» счёта не имеет значения — платится только серверный.
#
# ВАЖНО: RNG (xorshift32) и порядок операций обязаны бит-в-бит совпадать с
# JS-реализацией (_alchSim в app.04.js) — проверяется кросс-тестом node↔python.
GRID = 4
MOVES = ("L", "R", "U", "D")
TIME_LIMIT_SEC = 60
SUBMIT_GRACE_SEC = 15          # сеть/лаги: приём лога до 60+15с от старта
MAX_MOVES = 250
TARGET_SCORE = 1000            # payout = stake × min(3.0, score/TARGET)
PAYOUT_CAP_MULT = 3.0


def xorshift32(state: int) -> int:
    state ^= (state << 13) & 0xFFFFFFFF
    state ^= (state >> 17)
    state ^= (state << 5) & 0xFFFFFFFF
    return state & 0xFFFFFFFF


class Sim:
    """Детерминированная партия: seed → стартовая доска → ходы → счёт."""

    def __init__(self, seed: int):
        self.rng = seed & 0xFFFFFFFF or 1
        self.board = [0] * (GRID * GRID)
        self.score = 0
        self.spawn()
        self.spawn()

    def _next(self) -> int:
        self.rng = xorshift32(self.rng)
        return self.rng

    def spawn(self) -> None:
        empty = [i for i, v in enumerate(self.board) if v == 0]
        if not empty:
            return
        pos = empty[self._next() % len(empty)]
        self.board[pos] = 2 if (self._next() % 10) < 9 else 4

    def _slide_line(self, line: list[int]) -> tuple[list[int], int, bool]:
        """Сдвиг строки ВЛЕВО с мерджем. → (новая строка, очки, менялась ли)."""
        vals = [v for v in line if v]
        out, gained, i = [], 0, 0
        while i < len(vals):
            if i + 1 < len(vals) and vals[i] == vals[i + 1]:
                out.append(vals[i] * 2)
                gained += vals[i] * 2
                i += 2
            else:
                out.append(vals[i])
                i += 1
        out += [0] * (GRID - len(out))
        return out, gained, out != line

    def move(self, d: str) -> bool:
        """Один ход. Возвращает True, если доска изменилась (тогда спавн)."""
        changed = False
        for k in range(GRID):
            if d in ("L", "R"):
                idx = [k * GRID + j for j in range(GRID)]
            else:
                idx = [j * GRID + k for j in range(GRID)]
            line = [self.board[i] for i in idx]
            if d in ("R", "D"):
                line.reverse()
            new, gained, ch = self._slide_line(line)
            if d in ("R", "D"):
                new.reverse()
            if ch:
                changed = True
                self.score += gained
                for i, v in zip(idx, new):
                    self.board[i] = v
        if changed:
            self.spawn()
        return changed


def replay(seed: int, moves: list[str]) -> dict:
    """Реплей партии на сервере: единственный источник счёта."""
    sim = Sim(seed)
    applied = 0
    for m in moves[:MAX_MOVES]:
        if m in MOVES and sim.move(m):
            applied += 1
    return {"score": sim.score, "board": sim.board, "applied": applied}


def payout_mult(score: int) -> float:
    return round(min(PAYOUT_CAP_MULT, score / TARGET_SCORE), 3)