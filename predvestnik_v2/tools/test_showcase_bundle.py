"""Block 14: «весь набор» витрины недели — цена комплекта = сумма недельных скидок
минус бонус комплекта (−300✨), но скидка комплекта не больше 50% (на дешёвых
наборах −300 не уводит в абсурд/минус)."""
import sys
import pathlib

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from FastAPI.routers.showcase import _bundle_price, SHOWCASE_BUNDLE_DISCOUNT

assert SHOWCASE_BUNDLE_DISCOUNT == 300

cases = [
    # disc_sum, ожидаемая цена, комментарий
    (2000, 1700, "−300 на дорогом наборе"),
    (800,  500,  "−300 (500 = ровно порог, где −300 == 50%)"),
    (500,  250,  "50%-кап: −300 дало бы 200 (60%), берём 250"),
    (400,  200,  "50%-кап на дешёвом наборе (не 100)"),
    (100,  50,   "очень дешёвый — 50%, не уходим в минус"),
]
for disc_sum, expected, note in cases:
    got = _bundle_price(disc_sum)
    assert got == expected, f"disc_sum={disc_sum}: ожидали {expected} ({note}), получили {got}"
    # инварианты: не дороже суммы, не дешевле 50%, всегда ≥1
    assert got <= disc_sum, f"комплект дороже поштучной суммы ({got}>{disc_sum})"
    assert got >= round(disc_sum * 0.5), f"скидка комплекта >50% на {disc_sum} (got {got})"
    assert got >= 1

# −300 применяется, когда это НЕ превышает 50% (disc_sum >= 600)
assert _bundle_price(1000) == 700, "−300 на 1000 → 700"
assert _bundle_price(600) == 300, "−300 на 600 → 300 (ровно 50%)"

print("OK: цена комплекта = −300✨ от суммы, но не более 50% скидки; проверены "
      "дорогие и дешёвые наборы, инварианты (≤суммы, ≥50%, ≥1) держатся")
