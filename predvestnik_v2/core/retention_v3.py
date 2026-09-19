"""Pure retention/content policy for Reconstruction 3.0.

The policy deliberately rewards one meaningful intention per day instead of a
checklist.  Missing a calendar day never destroys progress, and Telegram Stars
cannot buy contract progress, retries, combat power or leaderboard score.
"""
from __future__ import annotations

import hashlib
from datetime import date
from typing import Any, Final


POLICY_VERSION: Final = "rhythm-v1-2026-08-26"
SETTLEMENT_MODE: Final = "shadow_only"
REAL_REWARDS_ENABLED: Final = False
DAILY_OFFER_COUNT: Final = 3
WEEKLY_MEANINGFUL_DAY_TARGET: Final = 4


DAILY_CONTRACTS: Final[dict[str, dict[str, Any]]] = {
    "steady_hand": {
        "category": "mastery",
        "name": "Твёрдая рука",
        "description": "Заверши один осмысленный забег с точностью не ниже 75%.",
        "metric": "accurate_runs",
        "target": 1,
        "why": "Короткая проверка личного мастерства без требования победить.",
    },
    "returning_echo": {
        "category": "mastery",
        "name": "Возвращённое эхо",
        "description": "После ошибки закончи забег, сохранив серию не ниже 8.",
        "metric": "recovery_runs",
        "target": 1,
        "why": "Ценит восстановление, а не идеальную игру.",
    },
    "charged_bell": {
        "category": "tempo",
        "name": "Заряженный колокол",
        "description": "Выпусти 3 Разряда за любое число забегов сегодня.",
        "metric": "discharges",
        "target": 3,
        "why": "Даёт ясную цель внутри основной боевой петли.",
    },
    "two_attempts": {
        "category": "tempo",
        "name": "Две попытки",
        "description": "Заверши 2 осмысленных забега; победа не обязательна.",
        "metric": "meaningful_runs",
        "target": 2,
        "why": "Создаёт короткую сессию и не наказывает за поражение.",
    },
    "living_build": {
        "category": "discovery",
        "name": "Живая сборка",
        "description": "Заверши забег с двумя разными усилениями.",
        "metric": "diverse_build_runs",
        "target": 1,
        "why": "Побуждает исследовать trade-off, а не повторять сильнейший шаблон.",
    },
    "unread_path": {
        "category": "discovery",
        "name": "Непрочитанная тропа",
        "description": "Заверши одну сюжетную встречу Хроники.",
        "metric": "distinct_encounters",
        "target": 1,
        "why": "Связывает дневное намерение с продвижением по созданному контенту.",
    },
}


def _ordered_category(category: str) -> list[str]:
    return sorted(
        contract_id
        for contract_id, contract in DAILY_CONTRACTS.items()
        if contract["category"] == category
    )


def daily_offer_ids(user_id: int, day: date | str) -> tuple[str, ...]:
    """Return a stable, varied offer: mastery + tempo + discovery."""
    uid = int(user_id)
    if uid <= 0:
        raise ValueError("user_id must be positive")
    day_key = day.isoformat() if isinstance(day, date) else str(day)
    result: list[str] = []
    for category in ("mastery", "tempo", "discovery"):
        options = _ordered_category(category)
        digest = hashlib.sha256(f"{POLICY_VERSION}:{uid}:{day_key}:{category}".encode()).digest()
        result.append(options[int.from_bytes(digest[:4], "big") % len(options)])
    return tuple(result)


def terminal_contribution(
    contract_id: str,
    *,
    outcome: str,
    encounter_id: str,
    mastery: dict[str, Any],
    upgrades: list[str],
    meaningful: bool,
) -> int:
    """Calculate progress contributed by one server-confirmed terminal run."""
    if contract_id not in DAILY_CONTRACTS or not meaningful:
        return 0
    correct = max(0, int(mastery.get("correct_taps", 0)))
    wrong = max(0, int(mastery.get("mistakes", 0)))
    missed = max(0, int(mastery.get("missed_signals", 0)))
    attempts = correct + wrong + missed
    accuracy = (correct / attempts * 100) if attempts else 0
    max_combo = max(0, int(mastery.get("max_combo", mastery.get("best_combo", 0))))
    discharges = max(0, int(mastery.get("discharges", 0)))
    if contract_id == "steady_hand":
        return int(accuracy >= 75)
    if contract_id == "returning_echo":
        return int(wrong > 0 and max_combo >= 8)
    if contract_id == "charged_bell":
        return discharges
    if contract_id == "two_attempts":
        return 1
    if contract_id == "living_build":
        return int(len(set(upgrades)) >= 2)
    if contract_id == "unread_path":
        return int(bool(encounter_id))
    return 0


def public_manifest() -> dict[str, Any]:
    return {
        "policy_version": POLICY_VERSION,
        "settlement_mode": SETTLEMENT_MODE,
        "real_rewards_enabled": REAL_REWARDS_ENABLED,
        "daily_offer_count": DAILY_OFFER_COUNT,
        "weekly_meaningful_day_target": WEEKLY_MEANINGFUL_DAY_TARGET,
        "missed_day_penalty": False,
        "streak_resets": False,
        "stars_can_buy_progress": False,
        "contracts": [
            {"id": contract_id, **dict(contract)}
            for contract_id, contract in DAILY_CONTRACTS.items()
        ],
    }


def validate_content() -> list[str]:
    errors: list[str] = []
    categories = {item["category"] for item in DAILY_CONTRACTS.values()}
    if categories != {"mastery", "tempo", "discovery"}:
        errors.append("Daily contracts must cover mastery/tempo/discovery.")
    if any(int(item["target"]) <= 0 for item in DAILY_CONTRACTS.values()):
        errors.append("Daily contract targets must be positive.")
    return errors
