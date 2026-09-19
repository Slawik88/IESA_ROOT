"""Finite route-building for the non-economic Harbinger Sky."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Final


POLICY_VERSION: Final = "harbinger-sky-v1-2026-08-28"
MAX_PATH_SLOTS: Final = 7

BRANCHES: Final[tuple[dict[str, str], ...]] = (
    {"id": "rift", "name": "Разлом", "icon": "🔔", "theme": "мастерство и чтение боя"},
    {"id": "archive", "name": "Архив", "icon": "▥", "theme": "расследования и память"},
    {"id": "bond", "name": "Связь", "icon": "🐾", "theme": "спутники и забота"},
)

NODES: Final[tuple[dict[str, Any], ...]] = (
    {"id": "rift_gate", "branch": "rift", "tier": 1, "name": "Слышать трещину", "description": "Открывает разбор завершённого забега: ошибки, восстановление серии и найденный ритм.", "parents": (), "exclusive": None, "kind": "dossier"},
    {"id": "rift_reader", "branch": "rift", "tier": 2, "name": "Чтец знаков", "description": "Открывает атлас уже встреченных боевых семейств и их телеграфов.", "parents": ("rift_gate",), "exclusive": "rift_route", "kind": "lens"},
    {"id": "rift_vow", "branch": "rift", "tier": 2, "name": "Клятва тишины", "description": "Открывает тренировочные обеты — добровольные правила забега без дополнительных наград.", "parents": ("rift_gate",), "exclusive": "rift_route", "kind": "lens"},
    {"id": "rift_sigil", "branch": "rift", "tier": 3, "name": "Печать Звона", "description": "Профильная печать пути: победа определяется вниманием, а не скоростью нажатий.", "parents_any": ("rift_reader", "rift_vow"), "exclusive": None, "kind": "sigil"},

    {"id": "archive_gate", "branch": "archive", "tier": 1, "name": "Карта свидетельств", "description": "Собирает финалы Недельных Дел и находки походов в единую полку истории.", "parents": (), "exclusive": None, "kind": "dossier"},
    {"id": "archive_ink", "branch": "archive", "tier": 2, "name": "Чернильная линза", "description": "Показывает в деле решения, которыми ты сохранил связь и смысл.", "parents": ("archive_gate",), "exclusive": "archive_route", "kind": "lens"},
    {"id": "archive_ash", "branch": "archive", "tier": 2, "name": "Пепельная линза", "description": "Показывает в деле решения, которыми ты принял потерю и цену выбора.", "parents": ("archive_gate",), "exclusive": "archive_route", "kind": "lens"},
    {"id": "archive_sigil", "branch": "archive", "tier": 3, "name": "Печать Свидетеля", "description": "Профильная печать пути: ни один завершённый финал не исчезает из истории.", "parents_any": ("archive_ink", "archive_ash"), "exclusive": None, "kind": "sigil"},

    {"id": "bond_gate", "branch": "bond", "tier": 1, "name": "Дневник спутника", "description": "Открывает спокойную сводку заботы, ролей и найденных вместе вещей.", "parents": (), "exclusive": None, "kind": "dossier"},
    {"id": "bond_care", "branch": "bond", "tier": 2, "name": "Тёплая ладонь", "description": "Линза заботы подсказывает доступную сцену без штрафов за пропущенный день.", "parents": ("bond_gate",), "exclusive": "bond_route", "kind": "lens"},
    {"id": "bond_scout", "branch": "bond", "tier": 2, "name": "Дальний след", "description": "Линза разведки объясняет различия маршрутов 2/6/12 часов, не раскрывая скрытую находку.", "parents": ("bond_gate",), "exclusive": "bond_route", "kind": "lens"},
    {"id": "bond_sigil", "branch": "bond", "tier": 3, "name": "Печать Стаи", "description": "Профильная печать пути: связь растёт от совместных сцен, а не от обязательного стрика.", "parents_any": ("bond_care", "bond_scout"), "exclusive": None, "kind": "sigil"},
)

NODE_BY_ID: Final = {str(node["id"]): node for node in NODES}
SIGIL_IDS: Final = frozenset(node["id"] for node in NODES if node["kind"] == "sigil")
DEFINITION_DIGEST: Final = hashlib.sha256(json.dumps({
    "policy_version": POLICY_VERSION, "max_path_slots": MAX_PATH_SLOTS,
    "branches": BRANCHES, "nodes": NODES,
}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def validate_allocated_state(allocated: set[str], active_sigil: str | None = None) -> None:
    if len(allocated) > MAX_PATH_SLOTS or allocated - set(NODE_BY_ID):
        raise RuntimeError("Harbinger Sky state is malformed")
    groups: set[str] = set()
    for node_id in allocated:
        node = NODE_BY_ID[node_id]
        if any(parent not in allocated for parent in node.get("parents", ())):
            raise RuntimeError("Harbinger Sky state is malformed")
        parents_any = tuple(node.get("parents_any", ()))
        if parents_any and not any(parent in allocated for parent in parents_any):
            raise RuntimeError("Harbinger Sky state is malformed")
        group = node.get("exclusive")
        if group and group in groups:
            raise RuntimeError("Harbinger Sky state is malformed")
        if group:
            groups.add(group)
    if active_sigil is not None and (active_sigil not in SIGIL_IDS or active_sigil not in allocated):
        raise RuntimeError("Harbinger Sky sigil state is malformed")


def path_budget(completed_feats: int) -> int:
    """Derived capacity, never a wallet or purchasable currency."""
    return min(MAX_PATH_SLOTS, max(0, int(completed_feats)))


def can_allocate(allocated: set[str], node_id: str, budget: int) -> tuple[bool, str | None]:
    node = NODE_BY_ID.get(str(node_id))
    if not node:
        return False, "unknown_node"
    if node_id in allocated:
        return False, "already_allocated"
    if len(allocated) >= max(0, int(budget)):
        return False, "no_path_slots"
    if any(parent not in allocated for parent in node.get("parents", ())):
        return False, "parent_required"
    parents_any = tuple(node.get("parents_any", ()))
    if parents_any and not any(parent in allocated for parent in parents_any):
        return False, "parent_required"
    group = node.get("exclusive")
    if group and any(NODE_BY_ID.get(item, {}).get("exclusive") == group for item in allocated):
        return False, "route_already_chosen"
    return True, None


def public_view(*, allocated: set[str], active_sigil: str | None, revision: int,
                completed_feats: int, eclipse_cycle_key: str | None,
                current_cycle_no: int, current_cycle_key: str) -> dict[str, Any]:
    budget = path_budget(completed_feats)
    nodes = []
    for node in NODES:
        ok, reason = can_allocate(allocated, str(node["id"]), budget)
        nodes.append({
            **node,
            "parents": list(node.get("parents", ())),
            "parents_any": list(node.get("parents_any", ())),
            "allocated": node["id"] in allocated,
            "available": ok,
            "blocked_reason": reason,
        })
    return {
        "policy_version": POLICY_VERSION,
        "revision": int(revision),
        "branches": [dict(item) for item in BRANCHES],
        "nodes": nodes,
        "allocated_node_ids": sorted(allocated),
        "allocated_count": len(allocated),
        "path_slots": budget,
        "available_slots": max(0, budget - len(allocated)),
        "completed_feats": max(0, int(completed_feats)),
        "active_sigil": active_sigil if active_sigil in allocated else None,
        "current_scar_cycle_no": int(current_cycle_no),
        "eclipse_available": eclipse_cycle_key != current_cycle_key and bool(allocated),
        "new_currency": False,
        "economic_reward": None,
        "combat_power": False,
        "stars_can_buy_progress": False,
    }


def validate_definition() -> list[str]:
    errors: list[str] = []
    ids = [str(node["id"]) for node in NODES]
    if len(ids) != len(set(ids)):
        errors.append("node ids must be unique")
    for node in NODES:
        for parent in (*node.get("parents", ()), *node.get("parents_any", ())):
            if parent not in NODE_BY_ID:
                errors.append(f"{node['id']}: missing parent {parent}")
    return errors


_ERRORS = validate_definition()
if _ERRORS:
    raise RuntimeError("Invalid Harbinger Sky: " + "; ".join(_ERRORS))
