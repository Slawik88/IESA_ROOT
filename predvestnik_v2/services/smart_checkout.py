"""services/smart_checkout.py — Smart Checkout (ШАГ6).

Универсальный расчёт «недостающих ресурсов» при покупке: если базовой валюты не
хватает, дефицит конвертируется в Зарники (✨) по фиксированному курсу
ZARNIKI_EXCHANGE_RATES с округлением ВВЕРХ (math.ceil — без дробных ✨).

Чистая логика, без БД/HTTP — оборачивается вокруг любой покупки. Списание базовой
валюты + Зарников выполняется АТОМАРНО на стороне репозитория (см. economy.buy_item
cover_with_zarniki) — здесь только расчёт.
"""
import math

from core.constants import ZARNIKI_EXCHANGE_RATES

_CUR_ICON = {"mora": "🪙", "diamonds": "💎", "dark_mora": "🌑", "zarniki": "✨"}
_CUR_LABEL = {"mora": "Моры", "diamonds": "Алмазов", "dark_mora": "Тёмной Моры", "zarniki": "Зарников"}


def zarniki_for_deficit(currency: str, amount: float) -> int | None:
    """Сколько ✨ нужно, чтобы покрыть `amount` единиц дефицита `currency` (ceil).
    None — валюта не конвертируется в ✨ (покрыть нельзя)."""
    if amount <= 0:
        return 0
    rate = ZARNIKI_EXCHANGE_RATES.get(currency)
    if not rate:
        return None
    return math.ceil(amount / rate)


def calculate_missing_resources_cost(balances: dict, cost: dict) -> dict:
    """УНИВЕРСАЛЬНЫЙ хелпер (CalculateMissingResourcesCost).

    balances: {"mora": .., "diamonds": .., "zarniki": ..}
    cost:     {"mora": .., "diamonds": ..}  (требуемая цена покупки)

    → {
        affordable: bool,            # хватает базовой валюты без ✨
        deficits: {cur: {"amount", "icon", "label", "zarniki"}},  # чего и сколько не хватает
        zarniki_needed: int,         # сумма ✨ на покрытие ВСЕГО дефицита (ceil)
        zarniki_have: float,
        coverable: bool,             # дефицит покрываем И ✨ хватает (сценарий A vs B)
      }
    """
    deficits: dict[str, dict] = {}
    zarniki_needed = 0
    all_convertible = True
    for cur, amount in cost.items():
        if cur == "zarniki" or not amount or amount <= 0:
            continue
        have = float(balances.get(cur, 0) or 0)
        miss = float(amount) - have
        if miss > 0:
            z = zarniki_for_deficit(cur, miss)
            if z is None:
                all_convertible = False
                deficits[cur] = {"amount": miss, "icon": _CUR_ICON.get(cur, cur),
                                 "label": _CUR_LABEL.get(cur, cur), "zarniki": None}
            else:
                zarniki_needed += z
                deficits[cur] = {"amount": miss, "icon": _CUR_ICON.get(cur, cur),
                                 "label": _CUR_LABEL.get(cur, cur), "zarniki": z}

    zarniki_have = float(balances.get("zarniki", 0) or 0)
    # учитываем, что у покупки может быть и собственная ✨-цена
    own_zarniki = float(cost.get("zarniki", 0) or 0)
    affordable = not deficits
    coverable = (not affordable) and all_convertible and (zarniki_have >= zarniki_needed + own_zarniki)
    return {
        "affordable": affordable,
        "deficits": deficits,
        "zarniki_needed": zarniki_needed,
        "zarniki_have": zarniki_have,
        "coverable": coverable,
    }
