"""Регресс-тест П2/П3/П4 BOT_AUDIT.md: скидка Черепахи.

П2: apply_discount(bool) хардкодил скидку Lv5 (5%) для ЛЮБОГО уровня Черепахи —
Lv1 получал переплаченные 5% вместо 2%, Lv10 недополучал 5% вместо честных 10%.
П4: скидка не масштабировалась по слоту (Блок 12: passive = ×0.5) и брала
`LIMIT 1` без ORDER BY при 2+ Черепахах.
П3: скидка на крутку гачи (Черепаха Lv8+) была объявлена в реестре и на карточке,
но нигде не применялась к фактической цене крутки.

Фикс: services/economy.py и services/gacha.py теперь читают через
infrastructure.repositories.zoo.get_species_bonus() — тот же аксессор, что уже
верно используют экспедиции/квесты/зоопарк (уровень + слот + ORDER BY active-first)."""
import sys
import pathlib
import asyncio

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from services.economy import EconomyService
from services.gacha import _turtle_gacha_discount


class _FakeCursor:
    def __init__(self, row):
        self._row = row

    async def fetchone(self):
        return self._row

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeDB:
    """pet_level/placement для species_id='turtle' — как в get_species_level_placement()."""
    def __init__(self, level: int | None, placement: str | None):
        self.level = level
        self.placement = placement

    def execute(self, sql, args=()):
        if "FROM pets" in sql and "species_id" in sql:
            row = (self.level, self.placement) if self.level else None
            return _FakeCursor(row)
        return _FakeCursor(None)


async def main():
    eco_lv1_active = EconomyService(FakeDB(1, "active"))
    d = await eco_lv1_active.get_turtle_discount(1)
    assert abs(d - 0.02) < 1e-9, f"FAIL (П2): Lv1 active ожидали 2%, получили {d:.0%} (было бы 5% — хардкод Lv5)"

    eco_lv10_active = EconomyService(FakeDB(10, "active"))
    d = await eco_lv10_active.get_turtle_discount(1)
    assert abs(d - 0.10) < 1e-9, f"FAIL (П2): Lv10 active ожидали 10%, получили {d:.0%} (было бы 5% — хардкод Lv5)"

    eco_lv10_passive = EconomyService(FakeDB(10, "passive"))
    d = await eco_lv10_passive.get_turtle_discount(1)
    assert abs(d - 0.05) < 1e-9, f"FAIL (П4): Lv10 passive ожидали 10%×0.5=5% (Блок 12), получили {d:.0%}"

    eco_none = EconomyService(FakeDB(None, None))
    d = await eco_none.get_turtle_discount(1)
    assert d == 0.0, f"FAIL: нет Черепахи — скидка должна быть 0, получили {d:.0%}"

    price = eco_lv1_active.apply_discount_fraction(1000, 0.02)
    assert price == 980, f"FAIL: apply_discount_fraction(1000, 2%) ожидали 980, получили {price}"

    # П3: скидка на крутку гачи — Lv8+ активная Черепаха
    db8 = FakeDB(8, "active")
    gd = await _turtle_gacha_discount(db8, 1)
    assert abs(gd - 0.10) < 1e-9, f"FAIL (П3): Lv8 active ожидали 10% на крутку гачи, получили {gd:.0%}"

    db5 = FakeDB(5, "active")
    gd5 = await _turtle_gacha_discount(db5, 1)
    assert gd5 == 0.0, f"FAIL (П3): Lv5 ещё не должен давать скидку на крутку (порог Lv8), получили {gd5:.0%}"

    print("OK: скидка магазина уровень+слот-корректна (П2/П4), скидка на крутку гачи "
          "Lv8+ реально считается (П3)")


asyncio.run(main())
