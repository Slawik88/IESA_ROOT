"""Functional contract for one-time legacy mini-game stake refunds."""
import asyncio
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# Contract tests run without the optional production PostgreSQL driver.
economy_stub = types.ModuleType("infrastructure.repositories.economy")
async def _unused_add_balance(*args, **kwargs):
    raise AssertionError("test must replace add_balance")
economy_stub.add_balance = _unused_add_balance
sys.modules.setdefault("infrastructure.repositories.economy", economy_stub)

from services import skill_games


class Cursor:
    def __init__(self, rows=None):
        self.rows = rows or []

    async def __aenter__(self):
        return self

    def __await__(self):
        async def done():
            return self
        return done().__await__()

    async def __aexit__(self, *args):
        return False

    async def fetchall(self):
        return self.rows


class Tx:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        self.db.in_tx = True

    async def __aexit__(self, exc_type, exc, tb):
        self.db.in_tx = False
        return False


class Connection:
    def __init__(self, db):
        self.db = db

    def transaction(self):
        return Tx(self.db)


class DB:
    def __init__(self):
        self.in_tx = False
        self.connection = Connection(self)
        self.active = [
            {"id": 11, "game": "sapper", "stake": 125.0},
            {"id": 12, "game": "safe", "stake": 80.0},
        ]

    def execute(self, sql, args=()):
        if "SELECT id, game, stake" in sql:
            return Cursor(list(self.active))
        if "UPDATE minigame_sessions" in sql:
            assert self.in_tx
            session_id = int(args[1])
            self.active = [row for row in self.active if row["id"] != session_id]
            return Cursor()
        raise AssertionError(sql)


async def main():
    db = DB()
    credits = []

    async def fake_add_balance(_db, user_id, **kwargs):
        assert db.in_tx
        credits.append((user_id, kwargs))

    skill_games.add_balance = fake_add_balance
    first = await skill_games.refund_active_sessions(db, 7)
    second = await skill_games.refund_active_sessions(db, 7)

    assert first == {"count": 2, "refunded_mora": 205.0}
    assert second == {"count": 0, "refunded_mora": 0.0}
    assert [item[1]["idempotency_key"] for item in credits] == [
        "legacy-minigame-refund:11", "legacy-minigame-refund:12"
    ]

    router = pathlib.Path("FastAPI/routers/skill_games.py").read_text(encoding="utf-8")
    ui = pathlib.Path("FastAPI/static/index.html").read_text(encoding="utf-8")
    bot = pathlib.Path("bot/handlers/games.py").read_text(encoding="utf-8")
    assert "HTTPException(410" in router
    assert "swArena('games'" not in ui and 'id="ar-games"' not in ui
    assert "Разлом колокола" in bot and "Сапёр, Сейф и Алхимия со ставками закрыты" in bot

    print("OK: wager games are closed; active stakes refund atomically and once")


asyncio.run(main())
