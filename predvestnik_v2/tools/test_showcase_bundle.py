"""Block 14: «весь набор» витрины недели. Бонус комплекта — от 200✨ (2 предмета)
до 400✨ (полный набор из SHOWCASE_SLOTS), линейно по количеству. Цена не дешевле
60% суммы (макс 40% off) — «не так дёшево»."""
import sys
import pathlib

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from FastAPI.routers.showcase import (
    _bundle_price, _bundle_discount, SHOWCASE_BUNDLE_MIN, SHOWCASE_BUNDLE_MAX)
from infrastructure.repositories.showcase import SHOWCASE_SLOTS

assert SHOWCASE_BUNDLE_MIN == 200 and SHOWCASE_BUNDLE_MAX == 400

# Бонус растёт от 200 (2 предмета) до 400 (полный набор)
assert _bundle_discount(2) == 200, "2 предмета → −200"
assert _bundle_discount(SHOWCASE_SLOTS) == 400, "полный набор → −400"
for n in range(2, SHOWCASE_SLOTS + 1):
    d = _bundle_discount(n)
    assert 200 <= d <= 400, f"бонус за {n} предметов вне 200..400: {d}"
# монотонно не убывает с ростом набора
disc_seq = [_bundle_discount(n) for n in range(2, SHOWCASE_SLOTS + 1)]
assert disc_seq == sorted(disc_seq), f"бонус не растёт с размером набора: {disc_seq}"

print("Бонус комплекта по размеру:",
      {n: _bundle_discount(n) for n in range(2, SHOWCASE_SLOTS + 1)})

# Цена: −бонус от суммы, но не дешевле 60% (макс 40% off)
for disc_sum, count in [(1200, 5), (1000, 5), (800, 3), (500, 2), (300, 2), (2000, 4)]:
    p = _bundle_price(disc_sum, count)
    assert p <= disc_sum, f"комплект дороже суммы: {p}>{disc_sum}"
    assert p >= round(disc_sum * 0.6), f"скидка >40% на {disc_sum}: цена {p}"
    assert p >= 1
    # не глубже, чем полный бонус
    assert p >= disc_sum - _bundle_discount(count), "цена ниже, чем сумма минус бонус"

# Конкретика: дорогой полный набор — ровно −400 (пол не мешает)
assert _bundle_price(1200, 5) == 800, f"1200/5 → 800, got {_bundle_price(1200,5)}"
# Дешёвый набор упирается в пол 60% (−200 дало бы 40% off, floor держит)
assert _bundle_price(300, 2) == round(300 * 0.6), f"300/2 floor 60%, got {_bundle_price(300,2)}"

print("OK: бонус комплекта 200→400 по размеру набора, цена не дешевле 60% суммы "
      "(«не так дёшево»), инварианты держатся")
