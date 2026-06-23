"""services/crypto_exchange.py — Крипто-Биржа (ШАГ4): лорные валюты, волатильность, свечи.

Цена монеты — ДЕТЕРМИНИРОВАННАЯ функция времени (наложение синусоид с
индивидуальной частотой/фазой). Поэтому:
  • не нужен планировщик/таблица истории цен — график считается на лету;
  • цена сервер-сайд и одинакова для всех в один момент → честно (no client trust);
  • сделки используют price_now() в момент запроса.
Базовая валюта торговли — Мора 🪙. Портфель игрока — в crypto_holdings.
"""
import math
import time

# 8 лорных валют. base — цена в Море, vol — амплитуда колебаний, seed — фаза.
COINS: list[dict] = [
    {"id": "abyssite", "name": "Абиссит",  "emoji": "🌑", "base": 1200.0, "vol": 0.28, "seed": 1.3},
    {"id": "luminar",  "name": "Луминар",  "emoji": "✨", "base": 800.0,  "vol": 0.18, "seed": 2.7},
    {"id": "verdane",  "name": "Вердан",   "emoji": "🌿", "base": 350.0,  "vol": 0.22, "seed": 0.9},
    {"id": "pyron",    "name": "Пирон",    "emoji": "🔥", "base": 2100.0, "vol": 0.35, "seed": 3.4},
    {"id": "aquilon",  "name": "Аквилон",  "emoji": "💧", "base": 620.0,  "vol": 0.20, "seed": 1.9},
    {"id": "zephyr",   "name": "Зефир",    "emoji": "🌪", "base": 480.0,  "vol": 0.30, "seed": 4.1},
    {"id": "cryon",    "name": "Крион",    "emoji": "❄️", "base": 1500.0, "vol": 0.25, "seed": 2.2},
    {"id": "solmar",   "name": "Солмар",   "emoji": "☀️", "base": 3000.0, "vol": 0.32, "seed": 0.5},
]
_BY_ID = {c["id"]: c for c in COINS}


def get_coin(coin_id: str) -> dict | None:
    return _BY_ID.get(coin_id)


def _factor(seed: float, vol: float, t_hours: float) -> float:
    osc = (math.sin(t_hours * 0.70 + seed) * 0.55
           + math.sin(t_hours * 0.21 + seed * 1.7) * 0.30
           + math.sin(t_hours * 2.90 + seed * 0.4) * 0.15)
    return 1.0 + osc * vol


def price_at(coin: dict, t: float) -> float:
    """Цена монеты в момент t (unix-секунды). Ограничена снизу 15% базы."""
    f = _factor(coin["seed"], coin["vol"], t / 3600.0)
    return round(max(coin["base"] * 0.15, coin["base"] * f), 2)


def price_now(coin: dict) -> float:
    return price_at(coin, time.time())


def candles(coin: dict, periods: int = 24, period_sec: int = 3600, now: float | None = None) -> list[dict]:
    """OHLC-свечи за последние `periods` периодов (по умолчанию 24 часовые)."""
    now = now if now is not None else time.time()
    out = []
    for i in range(periods, 0, -1):
        start = now - i * period_sec
        samples = [price_at(coin, start + period_sec * k / 6.0) for k in range(7)]
        out.append({"o": samples[0], "c": samples[-1],
                    "h": max(samples), "l": min(samples)})
    return out


def change_pct(coin: dict, hours: int = 24, now: float | None = None) -> float:
    now = now if now is not None else time.time()
    p_now = price_at(coin, now)
    p_then = price_at(coin, now - hours * 3600)
    return round((p_now - p_then) / p_then * 100, 2) if p_then else 0.0
