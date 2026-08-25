"""services/crypto_exchange.py — Крипто-Биржа (ШАГ4): лорные валюты, волатильность, свечи.

БЕЗОПАСНОСТЬ (после аудита): цена — НЕ предсказуемая функция (раньше были синусы,
которые игрок мог экстраполировать и печатать Мору без риска). Теперь цена —
гладкое СЛУЧАЙНОЕ БЛУЖДАНИЕ по узлам, где каждый узел = keyed-hash(SECRET, coin, idx).
  • Будущие узлы зависят от СЕКРЕТА (env CRYPTO_SEED / BOT_TOKEN) → игрок НЕ может
    предсказать будущую цену по прошлым свечам → нет risk-free тайминга.
  • Детерминирована для всех в один момент (честно, no client trust), без планировщика
    и без таблицы истории — график считается на лету.
  • Дополнительно: спред на продаже (CRYPTO_TRADE_FEE) = край казино → биржа это СТОК,
    а не источник Моры. Лимиты — в repositories/crypto.py.
Базовая валюта торговли — Мора 🪙. Портфель игрока — в crypto_holdings.
"""
import hashlib
import math
import os
import time

# 8 лорных валют. base — цена в Море (центр блуждания), vol — амплитуда колебаний.
# БАЛАНС-РЕБАЛАНС: vol резко снижена (было 0.18–0.35) — гигантские размахи ±18–35%
# легко перекрывали спред и при mean-reversion к известному base печатали Мору. Теперь
# амплитуда ±4–8% сопоставима с round-trip-комиссией 10% (CRYPTO_TRADE_FEE×2) ⇒ покупка
# ниже base и продажа у base убыточна. Разнообразие сохранено (Луминар тихий, Пирон/Солмар бойкие).
COINS: list[dict] = [
    {"id": "abyssite", "name": "Абиссит", "emoji": "🌑", "base": 1200.0, "vol": 0.07, "region": "Бездна", "use": "походы в глубины"},
    {"id": "luminar", "name": "Луминар", "emoji": "✨", "base": 800.0, "vol": 0.04, "region": "Архив", "use": "исследование Памятей"},
    {"id": "verdane", "name": "Вердан", "emoji": "🌿", "base": 350.0, "vol": 0.05, "region": "Сады", "use": "забота о спутниках"},
    {"id": "pyron", "name": "Пирон", "emoji": "🔥", "base": 2100.0, "vol": 0.08, "region": "Пепельный путь", "use": "опасные контракты"},
    {"id": "aquilon", "name": "Аквилон", "emoji": "💧", "base": 620.0, "vol": 0.05, "region": "Прилив", "use": "морские маршруты"},
    {"id": "zephyr", "name": "Зефир", "emoji": "🌪", "base": 480.0, "vol": 0.07, "region": "Высокие тропы", "use": "разведка сигналов"},
    {"id": "cryon", "name": "Крион", "emoji": "❄️", "base": 1500.0, "vol": 0.06, "region": "Мёрзлая грань", "use": "сдерживание угроз"},
    {"id": "solmar", "name": "Солмар", "emoji": "☀️", "base": 3000.0, "vol": 0.08, "region": "Солнечный предел", "use": "союзные проекты"},
]
_BY_ID = {c["id"]: c for c in COINS}

# Секрет для непредсказуемости будущих цен. В ПРОДЕ обязателен (CRYPTO_SEED или BOT_TOKEN
# всегда есть в env). Фолбэк-константа — только для локали; если репо публичный и сид не
# задан, цены станут предсказуемыми → ВСЕГДА задавай CRYPTO_SEED/BOT_TOKEN на проде.
_PRICE_SECRET = os.getenv("CRYPTO_SEED") or os.getenv("BOT_TOKEN") or "predvestnik-cx-dev-seed"
_BUCKET_SEC = 1800  # узлы блуждания каждые 30 минут (между ними — гладко)
_WORLD_PERIOD_SEC = 7 * 24 * 3600
WORLD_PHASES: tuple[dict, ...] = (
    {"id": "deep_tide", "name": "Глубокий прилив", "focus": ("abyssite", "aquilon"), "summary": "Экспедиции исследуют затопленные пути."},
    {"id": "ash_procession", "name": "Пепельное шествие", "focus": ("pyron", "solmar"), "summary": "Караваны идут через Пепельный путь."},
    {"id": "archive_wake", "name": "Пробуждение Архива", "focus": ("luminar", "zephyr"), "summary": "Архив открывает новые сигналы и маршруты."},
    {"id": "winter_garden", "name": "Зимний сад", "focus": ("verdane", "cryon"), "summary": "Сады и Мёрзлая грань обмениваются редкими запасами."},
)


def get_coin(coin_id: str) -> dict | None:
    return _BY_ID.get(coin_id)


def world_phase(t: float | None = None) -> dict:
    """Published weekly lore phase; the same result is visible to every player."""
    now = time.time() if t is None else float(t)
    period = math.floor(now / _WORLD_PERIOD_SEC)
    phase = WORLD_PHASES[period % len(WORLD_PHASES)]
    return {
        **phase,
        "period": period,
        "ends_at": int((period + 1) * _WORLD_PERIOD_SEC),
        "focused_volatility": 1.2,
    }


def _node(coin_id: str, idx: int) -> float:
    """Псевдослучайный множитель узла [0,1) — НЕпредсказуем без секрета (sha256)."""
    h = hashlib.sha256(f"{_PRICE_SECRET}|{coin_id}|{idx}".encode()).digest()
    return int.from_bytes(h[:6], "big") / float(1 << 48)


def price_at(coin: dict, t: float) -> float:
    """Цена монеты в момент t (unix-секунды): гладкое случайное блуждание вокруг base,
    ограничено снизу 20% базы. Будущее непредсказуемо (узлы на секрете)."""
    b = t / _BUCKET_SEC
    i = math.floor(b)
    frac = b - i
    w = frac * frac * (3 - 2 * frac)  # smoothstep → непрерывная гладкая цена
    noise = (_node(coin["id"], i) * (1 - w) + _node(coin["id"], i + 1) * w) * 2 - 1  # [-1,1]
    phase = world_phase(t)
    phase_vol = 1.2 if coin["id"] in phase["focus"] else 0.9
    f = 1.0 + noise * coin["vol"] * phase_vol
    return round(max(coin["base"] * 0.20, coin["base"] * f), 2)


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
