"""Покупка произвольного набора косметики для примерочной Стадии 4.

Проверяет поведение, которое сломается, если buy_many() рассчитает сумму не по
конкретным предметам, спишет баланс до проверки средств или прочитает владение
до блокировки баланса.
"""
import asyncio
import pathlib
import sys
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.cosmetics import COSMETICS
from core.economy_contract import InsufficientBalance
from services.cosmetics import buy_many


ID_A = "cos_name_glow_moon"  # forest name glow, 250✨
ID_B = "cos_name_glow_frost"  # frost name glow, 440✨
assert COSMETICS[ID_A]["price"][0]["zarniki"] == 250
assert COSMETICS[ID_B]["price"][0]["zarniki"] == 440
EXPECTED_TOTAL = 690


class FakeCursor:
    def __init__(self, row=None, rows=None):
        self._row = row
        self._rows = rows or []

    async def fetchone(self):
        return self._row

    async def fetchall(self):
        return self._rows

    def __await__(self):
        async def _self():
            return self
        return _self().__await__()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class NoopTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakeConnection:
    def transaction(self):
        return NoopTransaction()


class FakeDB:
    """Минимальная in-memory модель PGAdapter для поведения buy_many()."""

    def __init__(self, balance):
        self.connection = FakeConnection()
        self.balance = balance
        self.executed = []
        self.granted = set()

    def execute(self, sql, args=()):
        self.executed.append((sql.strip(), tuple(args)))
        if "SELECT COALESCE(user_balance_zarniki" in sql:
            return FakeCursor((self.balance,))
        if "SELECT cosmetic_id FROM user_cosmetics" in sql:
            return FakeCursor(rows=[(cid,) for cid in self.granted])
        if sql.startswith("UPDATE users"):
            self.balance -= args[0]
        elif sql.startswith("INSERT INTO user_cosmetics"):
            self.granted.add(args[1])
        return FakeCursor()

    async def commit(self):
        pass


async def fake_balance_change(db, user_id, deltas, **_kwargs):
    """Cosmetics behavior test; the ledger itself has a dedicated contract test."""
    cost = int(-deltas["zarniki"])
    if db.balance < cost:
        raise InsufficientBalance("not enough zarniki")
    await db.execute("UPDATE users SET user_balance_zarniki = user_balance_zarniki - ? WHERE user_tg_id = ?", (cost, user_id))
    return SimpleNamespace(applied=True)


async def main():
    with patch("services.achievements.increment_metric", new_callable=AsyncMock), \
         patch("services.cosmetics.apply_balance_change", side_effect=fake_balance_change):
        ok, msg = await buy_many(FakeDB(balance=10_000), 1, [])
        assert not ok and "пуст" in msg.lower()

        ok, _ = await buy_many(FakeDB(balance=10_000), 1, ["cos_does_not_exist"])
        assert not ok

        poor_db = FakeDB(balance=EXPECTED_TOTAL - 1)
        ok, _ = await buy_many(poor_db, 555, [ID_A, ID_B])
        assert not ok
        assert not any(sql.startswith("UPDATE users") for sql, _ in poor_db.executed)
        assert not any(sql.startswith("INSERT INTO user_cosmetics") for sql, _ in poor_db.executed)

        rich_db = FakeDB(balance=EXPECTED_TOTAL)
        ok, msg = await buy_many(rich_db, 777, [ID_A, ID_B])
        assert ok, msg
        updates = [args for sql, args in rich_db.executed if sql.startswith("UPDATE users")]
        inserts = [args for sql, args in rich_db.executed if sql.startswith("INSERT INTO user_cosmetics")]
        assert updates == [(EXPECTED_TOTAL, 777)]
        assert len(inserts) == 2
        assert str(EXPECTED_TOTAL) in msg

        order_db = FakeDB(balance=EXPECTED_TOTAL)
        await buy_many(order_db, 111, [ID_A, ID_B])
        sql_order = [sql for sql, _ in order_db.executed]
        lock_index = next(i for i, sql in enumerate(sql_order) if "FOR UPDATE" in sql)
        owned_index = next(
            i for i, sql in enumerate(sql_order)
            if sql.startswith("SELECT cosmetic_id FROM user_cosmetics")
        )
        assert owned_index > lock_index, (
            "владение прочитано до блокировки баланса: второй параллельный вызов "
            "увидит старое владение и спишет цену повторно"
        )

    print("OK: buy_many — валидирует набор, не списывает при нехватке, покупает "
          "разные цены одной транзакцией и читает владение после FOR UPDATE")


asyncio.run(main())
