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
ARCHIVE_VERSION: Final = "companion-archive-v1-2026-08-27"
ARCHIVE_DISCOVERY_IDS_IMMUTABLE: Final = True
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
EXPEDITION_DISCOVERY_TEXT: Final[Mapping[str, str]] = MappingProxyType({
    "bell_fragment": "В песке звякнул осколок колокола; на нём вырезан незнакомый ритм.",
    "salt_map": "Соль проступила линиями карты и указала на закрытый берег.",
    "ink_trace": "Чернила не высохли: кто-то записал здесь половину имени.",
    "ash_seed": "В пепле сохранилось семя, которое не принадлежит этому костру.",
    "drowned_name": "Вода вернула имя, но стёрла последнюю букву.",
    "mirror_shard": "Осколок отражает не лицо, а путь, которым ты ещё не шёл.",
    "tide_formula": "На камне осталась формула прилива с одним пропущенным знаком.",
    "quiet_key": "Тихий ключ не открывает дверь — он открывает услышанный вопрос.",
    "archive_thread": "Нить архива ведёт к странице, которой нет в каталоге.",
    "lantern_glass": "Стекло Фонаря хранит тёплый свет даже в полной темноте.",
    "garden_mark": "На коре появилась метка сада, совпадающая с символом спутника.",
    "sealed_route": "Запечатанный путь отмечен датой следующего прилива.",
})
EXPEDITION_DISCOVERY_NAMES: Final[Mapping[str, str]] = MappingProxyType({
    "bell_fragment": "Осколок колокола", "salt_map": "Соляная карта",
    "ink_trace": "Чернильный след", "ash_seed": "Семя пепла",
    "drowned_name": "Утонувшее имя", "mirror_shard": "Осколок зеркала",
    "tide_formula": "Формула прилива", "quiet_key": "Тихий ключ",
    "archive_thread": "Нить архива", "lantern_glass": "Стекло Фонаря",
    "garden_mark": "Метка сада", "sealed_route": "Запечатанный путь",
})

# Duration is a visible route choice, not a hidden drop-rate multiplier. Each
# route advances one four-piece story set; this prevents the 2h route from being
# the universal optimal strategy for the whole Archive.
ARCHIVE_SETS: Final[Mapping[str, Mapping[str, Any]]] = MappingProxyType({
    "small_signs": {
        "name": "Малые знаки", "duration_hours": 2, "route_id": "quick_feedback",
        "discoveries": ("bell_fragment", "quiet_key", "mirror_shard", "garden_mark"),
        "finale": "Четыре малых знака складываются в предупреждение: Колокол отвечает не громкости, а вниманию.",
    },
    "lost_names": {
        "name": "Потерянные имена", "duration_hours": 6, "route_id": "story_clue",
        "discoveries": ("ink_trace", "drowned_name", "archive_thread", "lantern_glass"),
        "finale": "Страница возвращает утонувшее имя и оставляет место для того, кто дочитает его вслух.",
    },
    "sealed_routes": {
        "name": "Запечатанные пути", "duration_hours": 12, "route_id": "schematic",
        "discoveries": ("salt_map", "ash_seed", "tide_formula", "sealed_route"),
        "finale": "Карта, семя и формула отмечают путь, который открывается только между двумя приливами.",
    },
})
ARCHIVE_SET_BY_DURATION: Final = {
    int(meta["duration_hours"]): set_id for set_id, meta in ARCHIVE_SETS.items()
}

# Permanent, earned visual variants. They never enter the paid cosmetics
# registry and therefore cannot inherit VIP locks, set bonuses or combat stats.
COMPANION_SKIN_VERSION: Final = "companion-skins-v1-2026-08-28"
COMPANION_SKINS: Final[Mapping[str, Mapping[str, Any]]] = MappingProxyType({
    "natural": {
        "name": "Верный облик", "mark": "◌", "accent": "mist",
        "required_sets": (), "hint": "Доступен каждому владельцу спутника.",
    },
    "inkbound": {
        "name": "Чернильный след", "mark": "⌁", "accent": "ink",
        "required_sets": ("lost_names",), "hint": "Заверши «Потерянные имена».",
    },
    "tideglass": {
        "name": "Стекло прилива", "mark": "◇", "accent": "tide",
        "required_sets": ("sealed_routes",), "hint": "Заверши «Запечатанные пути».",
    },
    "bellkeeper": {
        "name": "Хранитель знаков", "mark": "✦", "accent": "bell",
        "required_sets": ("small_signs", "lost_names", "sealed_routes"),
        "hint": "Собери весь Архив находок.",
    },
})


def companion_skin_catalog(archive: Mapping[str, Any]) -> list[dict[str, Any]]:
    completed = {
        str(item["id"]) for item in archive.get("sets", []) if item.get("completed")
    }
    return [
        {
            "id": skin_id,
            **dict(meta),
            "unlocked": set(meta["required_sets"]).issubset(completed),
        }
        for skin_id, meta in COMPANION_SKINS.items()
    ]


def archive_set_id_for_discovery(discovery_id: str) -> str:
    for set_id, meta in ARCHIVE_SETS.items():
        if str(discovery_id) in meta["discoveries"]:
            return set_id
    raise CompanionPolicyError("Unknown Archive discovery.")


COMPANION_ROLES: Final[Mapping[str, Mapping[str, Any]]] = MappingProxyType({
    "navigator": {
        "name": "Навигатор", "emoji": "⌁",
        "implemented": True,
        "decision": "До старта раскрывает темп и давление одной будущей волны.",
        "tradeoff": "Прогноз фиксируется на весь забег и не раскрывает правильные ответы.",
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
        "implemented": True,
        "decision": "После волны выделяет одну полезную закономерность твоей игры.",
        "tradeoff": "Разбор занимает один слот: доступно два усиления вместо трёх.",
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


def expedition_discovery(
    seed_digest: str,
    duration_hours: int,
    committed_discovery_ids: tuple[str, ...] | list[str] | set[str] = (),
) -> str:
    """Choose a missing route fragment first, then a deterministic duplicate."""
    digest = str(seed_digest or "").strip().lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise CompanionPolicyError("seed_digest must be a SHA-256 hex digest.")
    if duration_hours not in EXPEDITION_OPTIONS:
        raise CompanionPolicyError("duration_hours must be 2, 6 or 12.")
    set_id = ARCHIVE_SET_BY_DURATION[duration_hours]
    pool = tuple(ARCHIVE_SETS[set_id]["discoveries"])
    committed = {str(item) for item in committed_discovery_ids}
    candidates = tuple(item for item in pool if item not in committed) or pool
    mixed = hashlib.sha256(
        f"{ARCHIVE_VERSION}:{digest}:{duration_hours}".encode("ascii")
    ).digest()
    return candidates[int.from_bytes(mixed[:4], "big") % len(candidates)]


def archive_view(discovery_counts: Mapping[str, int]) -> dict[str, Any]:
    """Return a spoiler-safe collection view from durable ownership/history."""
    normalized = {
        str(discovery_id): max(0, int(count))
        for discovery_id, count in discovery_counts.items()
        if str(discovery_id) in EXPEDITION_DISCOVERIES
    }
    sets: list[dict[str, Any]] = []
    for set_id, meta in ARCHIVE_SETS.items():
        items = []
        for discovery_id in meta["discoveries"]:
            count = normalized.get(discovery_id, 0)
            items.append({
                "id": discovery_id,
                "name": EXPEDITION_DISCOVERY_NAMES[discovery_id] if count else None,
                "text": EXPEDITION_DISCOVERY_TEXT[discovery_id] if count else None,
                "found": count > 0,
                "duplicates": max(0, count - 1),
            })
        progress = sum(item["found"] for item in items)
        target = len(items)
        sets.append({
            "id": set_id, "name": meta["name"],
            "duration_hours": int(meta["duration_hours"]),
            "route_id": meta["route_id"], "progress": progress, "target": target,
            "completed": progress == target,
            "finale": meta["finale"] if progress == target else None,
            "items": items,
        })
    return {
        "version": ARCHIVE_VERSION,
        "new_currency": False,
        "rewards_enabled": False,
        "found": sum(item["found"] for story_set in sets for item in story_set["items"]),
        "total": len(EXPEDITION_DISCOVERIES),
        "completed_sets": sum(story_set["completed"] for story_set in sets),
        "sets": sets,
    }


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
            "discovery_text": dict(EXPEDITION_DISCOVERY_TEXT),
            "archive": {
                "version": ARCHIVE_VERSION,
                "discovery_ids_immutable": ARCHIVE_DISCOVERY_IDS_IMMUTABLE,
                "id_reuse_forbidden": True,
                "sets": [
                    {
                        "id": set_id, "name": meta["name"],
                        "duration_hours": int(meta["duration_hours"]),
                        "route_id": meta["route_id"],
                        "target": len(meta["discoveries"]),
                    }
                    for set_id, meta in ARCHIVE_SETS.items()
                ],
                "new_currency": False,
                "result_hidden_until_claim": True,
            },
        },
        "skins": {
            "version": COMPANION_SKIN_VERSION,
            "paid": False,
            "combat_power": False,
            "random": False,
            "items": [{"id": skin_id, **dict(meta)} for skin_id, meta in COMPANION_SKINS.items()],
        },
    }


def validate_archive_content() -> list[str]:
    errors: list[str] = []
    flattened = [item for meta in ARCHIVE_SETS.values() for item in meta["discoveries"]]
    if len(flattened) != len(set(flattened)) or set(flattened) != set(EXPEDITION_DISCOVERIES):
        errors.append("Archive sets must partition all expedition discoveries exactly once.")
    if set(ARCHIVE_SET_BY_DURATION) != set(EXPEDITION_OPTIONS):
        errors.append("Every expedition duration must own exactly one Archive set.")
    if set(EXPEDITION_DISCOVERY_NAMES) != set(EXPEDITION_DISCOVERIES):
        errors.append("Every discovery needs a player-facing name.")
    if not ARCHIVE_DISCOVERY_IDS_IMMUTABLE:
        errors.append("Archive discovery ids must be globally immutable.")
    known_sets = set(ARCHIVE_SETS)
    for skin_id, skin in COMPANION_SKINS.items():
        if not set(skin["required_sets"]).issubset(known_sets):
            errors.append(f"Companion skin {skin_id} references an unknown Archive set.")
    return errors


_ARCHIVE_ERRORS = validate_archive_content()
if _ARCHIVE_ERRORS:
    raise RuntimeError("Invalid companion Archive: " + "; ".join(_ARCHIVE_ERRORS))
