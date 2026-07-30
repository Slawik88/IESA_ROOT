"""Стадия 3 косметики: «Купить всё недостающее» — массовая покупка недостающих
предметов линейки одной транзакцией, цена = кол-во недостающих × цена линейки
(core/cosmetics.py::LINEUPS — единая фиксированная цена за предмет в рамках
линейки). Мирроит buy_bundle() (routers/showcase.py) для витрины недели, но без
скидки комплекта — она там из-за поштучных цен, здесь цена и так одна на всех."""
import sys
import pathlib
import asyncio
from unittest.mock import AsyncMock, patch

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.cosmetics import lineup_items
from services.cosmetics import lineup_buy_quote, buy_lineup

# ── lineup_buy_quote(): чистая функция, реальный каталог, без БД ────────────
assert lineup_buy_quote("no_such_lineup", set()) is None, "неизвестная линейка → None"

forest_ids = set(lineup_items("forest"))
assert len(forest_ids) >= 2, "линейка 'forest' должна содержать несколько предметов"

q_none_owned = lineup_buy_quote("forest", set())
assert q_none_owned is not None
assert set(q_none_owned["missing"]) == forest_ids
assert q_none_owned["unit_price"] == 250
assert q_none_owned["total"] == 250 * len(forest_ids)

q_all_owned = lineup_buy_quote("forest", forest_ids)
assert q_all_owned is None, "вся линейка уже куплена → None (нечего докупать)"

one_owned = {next(iter(forest_ids))}
q_partial = lineup_buy_quote("forest", one_owned)
assert q_partial is not None
assert len(q_partial["missing"]) == len(forest_ids) - 1
assert q_partial["total"] == 250 * (len(forest_ids) - 1)

print("OK: lineup_buy_quote — None на неизвестной/полностью собранной линейке, "
      "верная раскладка missing×цена на частично собранной")


# ── buy_lineup(): транзакция, нехватка/достаток баланса ─────────────────────
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

    async def __aexit__(self, *a):
        return False


class _NoopTx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeConnection:
    def transaction(self):
        return _NoopTx()


class FakeDB:
    """execute() синхронный (не async def) — как реальный PGAdapter, курсор
    одновременно awaitable И async context manager (buy_lineup использует оба
    стиля: `await db.execute(...)` для UPDATE/INSERT, `async with db.execute(...)
    as c:` для SELECT ... FOR UPDATE — см. services/cosmetics.py::buy())."""

    def __init__(self, balance):
        self.connection = FakeConnection()
        self.executed = []
        self.balance = balance

    def execute(self, sql, args=()):
        self.executed.append((sql.strip(), tuple(args)))
        if "SELECT COALESCE(user_balance_zarniki" in sql:
            return FakeCursor((self.balance,))
        if "SELECT cosmetic_id FROM user_cosmetics" in sql:
            return FakeCursor(rows=[])
        if "SELECT" in sql:
            # Default for any SELECT: return empty rows or single empty row
            if "FROM" in sql:
                return FakeCursor(rows=[])
            return FakeCursor(None)
        # For UPDATE/INSERT: return empty cursor (no rows returned)
        return FakeCursor(None)

    async def commit(self):
        pass


async def main():
    # Mock increment_metric to avoid side DB operations in achievements tracking
    with patch("services.achievements.increment_metric", new_callable=AsyncMock):
        total_needed = 250 * len(forest_ids)

        # Недостаточно баланса — без единого UPDATE/INSERT (пока никаких списаний)
        db_poor = FakeDB(balance=total_needed - 1)
        ok, msg = await buy_lineup(db_poor, 555, "forest")
        assert ok is False, "должно отказать при нехватке баланса"
        assert "Нужно" in msg
        assert not any(sql.startswith("UPDATE users") for sql, _ in db_poor.executed), \
            "баланс не должен списываться при отказе"
        assert not any(sql.startswith("INSERT INTO user_cosmetics") for sql, _ in db_poor.executed), \
            "предметы не должны выдаваться при отказе"

        # Хватает баланса — ровно 1 UPDATE + по 1 INSERT на каждый недостающий предмет
        db_rich = FakeDB(balance=total_needed)
        ok, msg = await buy_lineup(db_rich, 777, "forest")
        assert ok is True, f"должно пройти при достаточном балансе: {msg}"
        updates = [a for sql, a in db_rich.executed if sql.startswith("UPDATE users")]
        inserts = [a for sql, a in db_rich.executed if sql.startswith("INSERT INTO user_cosmetics")]
        assert len(updates) == 1, f"ожидался 1 UPDATE баланса, получено {len(updates)}"
        assert updates[0][0] == total_needed, f"списано {updates[0][0]}, ожидалось {total_needed}"
        assert len(inserts) == len(forest_ids), \
            f"ожидалось {len(forest_ids)} INSERT (по одному на предмет), получено {len(inserts)}"
        assert str(len(forest_ids)) in msg and str(total_needed) in msg

        print("OK: buy_lineup — отказ без побочных эффектов при нехватке баланса; "
              "при достатке — 1 списание + по 1 выдаче на каждый недостающий предмет, "
              "сообщение содержит количество и сумму")


asyncio.run(main())
