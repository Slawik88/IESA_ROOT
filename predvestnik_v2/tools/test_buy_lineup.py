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

from core.cosmetics import COSMETIC_SLOTS, LINEUPS, lineup_items
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

# Новые японские линейки: не минимальные 6 заглушек, а по 15 самостоятельных
# предметов, при этом все визуальные слоты реально покрыты.
new_lineups = {
    "hanami": ("epic", 630),
    "moon_lotus": ("artifact", 1500),
    "ryujin_tide": ("artifact", 1500),
}
for lineup_id, (rarity, price) in new_lineups.items():
    meta = LINEUPS[lineup_id]
    items = lineup_items(lineup_id)
    assert len(items) == 15, f"{lineup_id}: ожидалось 15 предметов, получено {len(items)}"
    assert {item["slot"] for item in items.values()} == set(COSMETIC_SLOTS), \
        f"{lineup_id}: не все 6 слотов покрыты"
    assert {item["rarity"] for item in items.values()} == {rarity}
    assert {item["price"][0]["zarniki"] for item in items.values()} == {price}
    assert meta["rarity"] == rarity and meta["price"] == [{"zarniki": price}]
print("OK: Ханами / Лунный Лотос / Прилив Рюдзина — по 15 предметов, все 6 слотов, единый тир и цена")


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
        self.granted = set()   # имитирует строки user_cosmetics, персистентно между вызовами

    def execute(self, sql, args=()):
        self.executed.append((sql.strip(), tuple(args)))
        if "SELECT COALESCE(user_balance_zarniki" in sql:
            return FakeCursor((self.balance,))
        if "SELECT cosmetic_id FROM user_cosmetics" in sql:
            return FakeCursor(rows=[(cid,) for cid in self.granted])
        if sql.startswith("UPDATE users"):
            self.balance -= args[0]
            return FakeCursor(None)
        if sql.startswith("INSERT INTO user_cosmetics"):
            self.granted.add(args[1])
            return FakeCursor(None)
        if "SELECT" in sql:
            if "FROM" in sql:
                return FakeCursor(rows=[])
            return FakeCursor(None)
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

        # ── Регресс-тест финального ревью Стадии 3: владение ОБЯЗАНО читаться
        # ПОСЛЕ SELECT...FOR UPDATE, не до. В реальном Postgres второй
        # параллельный вызов buy_lineup для того же user_id блокируется на
        # FOR UPDATE, пока первый не закоммитится — если владение прочитано ДО
        # этой блокировки, оба вызова посчитают одну и ту же "missing" и спишут
        # total ДВАЖДЫ за одни и те же предметы (двойной тап по кнопке "Купить
        # всё недостающее" на фронте). FakeDB не умеет симулировать реальную
        # блокировку между двумя ОТДЕЛЬНЫМИ вызовами, но порядок SQL-запросов
        # ВНУТРИ одного вызова — то, что делает фикс верным под реальным
        # Postgres — проверяется напрямую по журналу executed.
        db_order = FakeDB(balance=total_needed)
        await buy_lineup(db_order, 111, "forest")
        sql_order = [sql for sql, _ in db_order.executed]
        idx_lock = next(i for i, s in enumerate(sql_order) if "FOR UPDATE" in s)
        idx_owned = next(i for i, s in enumerate(sql_order) if s.startswith("SELECT cosmetic_id FROM user_cosmetics"))
        assert idx_owned > idx_lock, (
            "владение прочитано ДО SELECT...FOR UPDATE — под реальным Postgres второй "
            "параллельный вызов (двойной тап) увидит СТАРОЕ владение и спишет total "
            "ещё раз за уже выданные предметы"
        )
        print("OK: buy_lineup — владение читается ПОСЛЕ захвата блокировки баланса "
              "(SELECT...FOR UPDATE), не до — двойной тап/параллельный вызов не спишет "
              "дважды за одни и те же предметы")


asyncio.run(main())
