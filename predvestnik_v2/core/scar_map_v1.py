"""Deterministic 28-day mastery map without currency or paid progression."""
from __future__ import annotations

from typing import Any, Final

POLICY_VERSION: Final = "scar-map-v1-2026-08-28"
DURATION_DAYS: Final = 28
FINAL_REQUIRED: Final = 9

NODES: Final[tuple[dict[str, Any], ...]] = (
    {"id": "precision", "lane": "mastery", "name": "Точный след", "hint": "Победи с точностью 80%+.", "metric": "max_accuracy", "target": 80},
    {"id": "recovery", "lane": "mastery", "name": "Шрам ошибки", "hint": "Победи после хотя бы одной ошибки.", "metric": "recovery_wins", "target": 1},
    {"id": "flawless", "lane": "mastery", "name": "Чистый звон", "hint": "Победи без ошибок и пропусков.", "metric": "flawless_wins", "target": 1},
    {"id": "long_combo", "lane": "mastery", "name": "Нить внимания", "hint": "Собери серию из 12 точных действий.", "metric": "max_combo", "target": 12},
    {"id": "first_run", "lane": "tempo", "name": "Первый разрез", "hint": "Заверши значимый забег.", "metric": "terminal_runs", "target": 1},
    {"id": "five_runs", "lane": "tempo", "name": "Устойчивый пульс", "hint": "Заверши 5 значимых забегов.", "metric": "terminal_runs", "target": 5},
    {"id": "ten_discharges", "lane": "tempo", "name": "Гроза внутри", "hint": "Создай 10 Разрядов.", "metric": "discharges", "target": 10},
    {"id": "three_encounters", "lane": "tempo", "name": "Три колокола", "hint": "Заверши 3 разные встречи.", "metric": "encounter_count", "target": 3},
    {"id": "rhythm_day", "lane": "discovery", "name": "Выбранный день", "hint": "Заверши один выбранный Ритм.", "metric": "meaningful_days", "target": 1},
    {"id": "four_rhythm_days", "lane": "discovery", "name": "Своя каденция", "hint": "Заверши Ритм в 4 разные дни.", "metric": "meaningful_days", "target": 4},
    {"id": "two_discoveries", "lane": "discovery", "name": "Две находки", "hint": "Открой 2 новые записи Архива.", "metric": "archive_discoveries", "target": 2},
    {"id": "six_discoveries", "lane": "discovery", "name": "Полка свидетельств", "hint": "Открой 6 новых записей Архива.", "metric": "archive_discoveries", "target": 6},
)

NODE_IDS: Final = frozenset(node["id"] for node in NODES)


def resolved_metrics(counters: dict[str, int], encounters: set[str]) -> dict[str, int]:
    result = {key: max(0, int(value or 0)) for key, value in counters.items()}
    result["encounter_count"] = len(encounters)
    return result


def unlocked_node_ids(counters: dict[str, int], encounters: set[str]) -> list[str]:
    metrics = resolved_metrics(counters, encounters)
    return [node["id"] for node in NODES if metrics.get(node["metric"], 0) >= int(node["target"])]


def public_view(row: dict[str, Any], counters: dict[str, int], encounters: set[str]) -> dict[str, Any]:
    metrics = resolved_metrics(counters, encounters)
    unlocked = set(unlocked_node_ids(counters, encounters))
    nodes = []
    for node in NODES:
        current = min(int(node["target"]), metrics.get(node["metric"], 0))
        nodes.append({
            "id": node["id"], "lane": node["lane"], "name": node["name"],
            "hint": node["hint"], "current": current, "target": int(node["target"]),
            "unlocked": node["id"] in unlocked,
        })
    return {
        "policy_version": POLICY_VERSION,
        "cycle_no": int(row["cycle_no"]),
        "started_at": row["started_at"],
        "ends_at": row["ends_at"],
        "duration_days": DURATION_DAYS,
        "nodes": nodes,
        "unlocked_count": len(unlocked),
        "total_nodes": len(NODES),
        "final_required": FINAL_REQUIRED,
        "completed": len(unlocked) >= FINAL_REQUIRED,
        "completed_at": row.get("completed_at"),
        "economic_reward": None,
        "new_currency": False,
        "stars_can_buy_progress": False,
        "premium_track_enabled": False,
    }
