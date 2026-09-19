"""Policy for one low-pressure, chat-native cooperative event."""
from __future__ import annotations

from math import ceil
from typing import Final


POLICY_VERSION: Final = "chat-echo-v1-2026-08-27"
DURATION_HOURS: Final = 6
COOLDOWN_DAYS: Final = 7
MIN_QUORUM: Final = 3
MAX_TARGET: Final = 20
SYMBOLS: Final = {
    "bell": {"emoji": "🔔", "name": "Звон"},
    "tide": {"emoji": "🌊", "name": "Прилив"},
    "silence": {"emoji": "◌", "name": "Тишина"},
}
FINALES: Final = {
    "bell": "Чат выбрал ответить: эхо стало общим сигналом.",
    "tide": "Чат пропустил эхо через себя: след изменился, но не исчез.",
    "silence": "Чат выдержал паузу: эхо раскрыло скрытый второй голос.",
    "balanced": "Ни один голос не победил: чат собрал устойчивый аккорд.",
}


def target_for_active_members(active_members_7d: int) -> int:
    active = max(0, int(active_members_7d))
    return max(MIN_QUORUM, min(MAX_TARGET, ceil(active * 0.35)))


def finale_for_counts(counts: dict[str, int]) -> str:
    normalized = {symbol: max(0, int(counts.get(symbol, 0))) for symbol in SYMBOLS}
    top = max(normalized.values(), default=0)
    winners = [symbol for symbol, count in normalized.items() if count == top]
    return winners[0] if len(winners) == 1 else "balanced"


def public_manifest() -> dict:
    return {
        "policy_version": POLICY_VERSION,
        "duration_hours": DURATION_HOURS,
        "cooldown_days": COOLDOWN_DAYS,
        "min_quorum": MIN_QUORUM,
        "max_target": MAX_TARGET,
        "admin_opt_in_required": True,
        "one_contribution_per_user": True,
        "new_currency": False,
        "economic_reward": None,
        "stars_can_buy_progress": False,
        "dm_notifications": False,
        "symbols": [{"id": key, **value} for key, value in SYMBOLS.items()],
    }
