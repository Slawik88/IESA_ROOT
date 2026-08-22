"""Pure companion and scouting contracts for Reconstruction 3.0.

No database, adapters or wallet mutations live here.  Existing ``pets`` rows
remain ownership truth; this module only defines the new horizontal role,
Bond and expedition rules that are safe to test before economy cutover.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Final, Mapping
import hashlib


POLICY_VERSION: Final = "companions-v3-provisional-1"
SETTLEMENT_MODE: Final = "shadow_only"
REAL_REWARDS_ENABLED: Final = False

ROLE_UNLOCK_DAYS: Final = (0, 5, 10, 15, 20, 25, 30, 35, 40, 45)
CARE_BANK_CAP: Final = 7
CARE_RECOVERY_HOURS: Final = 48
BOND_MILESTONES: Final = (1, 3, 6, 10, 15, 21, 28, 36, 45, 55, 66, 78)
EXPEDITION_WEEKLY_MORA_CAP: Final = 600
SECOND_EXPEDITION_SLOT_ENCOUNTER: Final = "e06_archivist"
EXPEDITION_DISCOVERIES: Final = (
    "bell_fragment", "salt_map", "ink_trace", "ash_seed",
    "drowned_name", "mirror_shard", "tide_formula", "quiet_key",
    "archive_thread", "lantern_glass", "garden_mark", "sealed_route",
)


COMPANION_ROLES: Final[Mapping[str, Mapping[str, Any]]] = MappingProxyType({
    "navigator": {
        "name": "Навигатор", "emoji": "⌁",
        "implemented": False,
        "decision": "До старта раскрывает семейство одной будущей волны.",
        "tradeoff": "После просмотра нельзя заменить этот контракт.",
    },
    "rhythm_keeper": {
        "name": "Хранитель ритма", "emoji": "◌",
        "implemented": True,
        "decision": "Один раз защищает выбранный активный сигнал от последствий пропуска.",
        "tradeoff": "Пропуск считается в точности, а потолок бонуса серии ниже.",
    },
    "echo": {
        "name": "Эхо", "emoji": "◍",
        "implemented": True,
        "decision": "Один раз за волну предлагает повторить прошлый знак в коротком окне.",
        "tradeoff": "Ошибка сбрасывает прогресс; успех добавляет выбор, а не сырую силу.",
    },
    "gardener": {
        "name": "Садовник", "emoji": "❧",
        "implemented": False,
        "decision": "Выращивает межволновой вариант чередованием классов.",
        "tradeoff": "Повтор одного класса сбрасывает рост.",
    },
    "archivist": {
        "name": "Архивариус", "emoji": "▤",
        "implemented": False,
        "decision": "Разбирает один фрагмент повтора перед следующим выбором.",
        "tradeoff": "Занимает один слот усиления.",
    },
    "lantern": {
        "name": "Фонарь", "emoji": "✧",
        "implemented": True,
        "decision": "Заранее отмечает один тип ложного сигнала.",
        "tradeoff": "Между волнами доступно два варианта вместо трёх.",
    },
    "weaver": {
        "name": "Ткач", "emoji": "⌘",
        "implemented": False,
        "decision": "Связывает эффекты двух слабых узлов в один план.",
        "tradeoff": "Третий узел той же группы блокируется.",
    },
    "cartographer": {
        "name": "Картограф", "emoji": "◇",
        "implemented": False,
        "decision": "Показывает вероятности веток текущего контракта.",
        "tradeoff": "Бесплатная замена предложения закрывается.",
    },
    "guardian": {
        "name": "Страж", "emoji": "⬡",
        "implemented": True,
        "decision": "Позволяет заранее расширить одно окно реакции.",
        "tradeoff": "Множитель результата этого окна ниже.",
    },
    "trickster": {
        "name": "Трикстер", "emoji": "⟲",
        "implemented": False,
        "decision": "Меняет правило кульминации на более рискованное.",
        "tradeoff": "Выбор необратим до конца забега.",
    },
})


EXPEDITION_OPTIONS: Final[Mapping[int, Mapping[str, Any]]] = MappingProxyType({
    2: {"mora": 50, "route": "quick_feedback", "route_name": "Быстрый отклик"},
    6: {"mora": 145, "route": "story_clue", "route_name": "След истории"},
    12: {"mora": 285, "route": "schematic", "route_name": "Поиск схемы"},
})


class CompanionPolicyError(ValueError):
    pass


def _non_negative_int(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CompanionPolicyError(f"{label} must be a non-negative integer.")
    return value


def role_unlock_count(meaningful_days: int) -> int:
    """First direct choice is immediate; the ninth extra role arrives on day 45."""
    days = _non_negative_int(meaningful_days, "meaningful_days")
    return sum(days >= threshold for threshold in ROLE_UNLOCK_DAYS)


def bond_progress(points: int) -> dict[str, int | None]:
    value = _non_negative_int(points, "points")
    reached = [milestone for milestone in BOND_MILESTONES if milestone <= value]
    upcoming = next((milestone for milestone in BOND_MILESTONES if milestone > value), None)
    return {
        "points": value,
        "milestones_reached": len(reached),
        "last_milestone": reached[-1] if reached else None,
        "next_milestone": upcoming,
        "points_to_next": None if upcoming is None else upcoming - value,
    }


def recover_care_bank(
    bank: int,
    bank_updated_at: datetime,
    now: datetime,
) -> tuple[int, datetime]:
    """Recover one care opportunity per 48h without creating overflow backlog."""
    value = _non_negative_int(bank, "bank")
    if value > CARE_BANK_CAP:
        raise CompanionPolicyError(f"bank must be <= {CARE_BANK_CAP}.")
    if not isinstance(bank_updated_at, datetime) or not isinstance(now, datetime):
        raise CompanionPolicyError("care timestamps must be datetime values.")
    if now < bank_updated_at:
        return value, bank_updated_at
    if value == CARE_BANK_CAP:
        return value, now
    elapsed = now - bank_updated_at
    recovered = int(elapsed.total_seconds() // (CARE_RECOVERY_HOURS * 3600))
    if recovered <= 0:
        return value, bank_updated_at
    updated = min(CARE_BANK_CAP, value + recovered)
    anchor = (
        now
        if updated == CARE_BANK_CAP
        else bank_updated_at + timedelta(hours=CARE_RECOVERY_HOURS * recovered)
    )
    return updated, anchor


@dataclass(frozen=True, slots=True)
class ExpeditionQuote:
    duration_hours: int
    route: str
    route_name: str
    base_mora: int
    projected_mora: int
    weekly_mora_before: int
    weekly_mora_after: int
    cap_reached: bool
    settlement_mode: str = SETTLEMENT_MODE
    can_settle: bool = False


def quote_expedition(duration_hours: int, weekly_mora_before: int = 0) -> ExpeditionQuote:
    if isinstance(duration_hours, bool) or duration_hours not in EXPEDITION_OPTIONS:
        raise CompanionPolicyError("duration_hours must be 2, 6 or 12.")
    earned = _non_negative_int(weekly_mora_before, "weekly_mora_before")
    option = EXPEDITION_OPTIONS[duration_hours]
    remaining = max(0, EXPEDITION_WEEKLY_MORA_CAP - earned)
    projected = min(int(option["mora"]), remaining)
    return ExpeditionQuote(
        duration_hours=duration_hours,
        route=str(option["route"]),
        route_name=str(option["route_name"]),
        base_mora=int(option["mora"]),
        projected_mora=projected,
        weekly_mora_before=earned,
        weekly_mora_after=earned + projected,
        cap_reached=projected < int(option["mora"]),
    )


def expedition_slot_count(first_chapter_complete: bool) -> int:
    if not isinstance(first_chapter_complete, bool):
        raise CompanionPolicyError("first_chapter_complete must be boolean.")
    return 2 if first_chapter_complete else 1


def expedition_discovery(seed_digest: str, duration_hours: int) -> str:
    """Map a committed server seed to a bounded discovery catalog."""
    digest = str(seed_digest or "").strip().lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise CompanionPolicyError("seed_digest must be a SHA-256 hex digest.")
    if duration_hours not in EXPEDITION_OPTIONS:
        raise CompanionPolicyError("duration_hours must be 2, 6 or 12.")
    mixed = hashlib.sha256(f"{digest}:{duration_hours}".encode("ascii")).digest()
    return EXPEDITION_DISCOVERIES[int.from_bytes(mixed[:4], "big") % len(EXPEDITION_DISCOVERIES)]


def public_companion_manifest() -> dict[str, Any]:
    return {
        "policy_version": POLICY_VERSION,
        "settlement_mode": SETTLEMENT_MODE,
        "real_rewards_enabled": REAL_REWARDS_ENABLED,
        "role_unlock_days": list(ROLE_UNLOCK_DAYS),
        "roles": [{"id": role_id, **dict(role)} for role_id, role in COMPANION_ROLES.items()],
        "care": {
            "recovery_hours": CARE_RECOVERY_HOURS,
            "bank_cap": CARE_BANK_CAP,
            "bond_milestones": list(BOND_MILESTONES),
            "missed_care_penalty": False,
            "duplicate_power": False,
        },
        "expeditions": {
            "weekly_mora_cap": EXPEDITION_WEEKLY_MORA_CAP,
            "options": [asdict(quote_expedition(hours)) for hours in EXPEDITION_OPTIONS],
            "rewards_expire": False,
            "cancel_rerolls": False,
            "second_slot_encounter": SECOND_EXPEDITION_SLOT_ENCOUNTER,
            "discoveries": list(EXPEDITION_DISCOVERIES),
        },
    }
