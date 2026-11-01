"""
core/money.py
Деньги «Домового»: целые копейки внутри, человекочитаемый рубль снаружи.
"""
from core.constants import KOPECKS_IN_RUBLE, MAX_AMOUNT_RUBLES


class AmountError(ValueError):
    """Не удалось разобрать сумму, введённую человеком."""


def parse_amount(raw: str) -> int:
    """«1200», «1 200,50», «1200.5» → копейки. Ошибка ввода → AmountError."""
    cleaned = raw.replace(" ", "").replace("\u00a0", "").replace(",", ".")
    if not cleaned or any(ch not in "0123456789." for ch in cleaned):
        raise AmountError("Сумма должна быть числом, например: 1200 или 1200.50")
    if cleaned.count(".") > 1:
        raise AmountError("Лишние точки в сумме")
    rubles, _, kops = cleaned.partition(".")
    if len(kops) > 2:
        raise AmountError("Копейки — максимум два знака: 1200.50")
    rubles = rubles.lstrip("0") or "0"
    if len(rubles) > len(str(MAX_AMOUNT_RUBLES)):
        raise AmountError("Слишком большая сумма")
    kop = int(rubles or "0") * KOPECKS_IN_RUBLE + int((kops + "00")[:2] or "0")
    if kop <= 0:
        raise AmountError("Сумма должна быть больше нуля")
    if kop > MAX_AMOUNT_RUBLES * KOPECKS_IN_RUBLE:
        raise AmountError("Слишком большая сумма")
    return kop


def format_amount(kop: int, currency: str) -> str:
    """1050000 → «10 500 ₽»; 105050 → «1 050,50 ₽»."""
    sign = "-" if kop < 0 else ""
    rubles, kops = divmod(abs(int(kop)), KOPECKS_IN_RUBLE)
    ruble_str = sign + f"{rubles:,}".replace(",", " ")
    if kops:
        return f"{ruble_str},{kops:02d} {currency}"
    return f"{ruble_str} {currency}"
