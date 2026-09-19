"""Finite, non-economic Chronicle feats for Reconstruction 3.0.

Unlike the retired achievement ladder, feats reward breadth and demonstrated
mastery. They are derived from authoritative state, have one terminal tier and
never grant currency, power, tradeable loot or leaderboard score.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Final, Mapping


FEATS_VERSION: Final = "chronicle-feats-v2-2026-08-28"
COMPATIBLE_GAME_VERSIONS: Final[tuple[str, ...]] = ("3.0.0-alpha.4",)

FEATS: Final[tuple[dict[str, Any], ...]] = (
    {"id": "first_echo", "icon": "🔔", "name": "Первый отклик", "description": "Заверши первую встречу Хроники.", "metric": "completed_encounters", "target": 1, "kind": "journey"},
    {"id": "bound_memory", "icon": "◈", "name": "Связанная память", "description": "Сделай первый постоянный выбор Памяти.", "metric": "memories", "target": 1, "kind": "choice"},
    {"id": "chosen_path", "icon": "◇", "name": "Своя тропа", "description": "Выбери путь первой главы Хроники.", "metric": "route_choices", "target": 1, "kind": "choice"},
    {"id": "three_signs", "icon": "▤", "name": "Три знака", "description": "Заверши три разные сюжетные встречи.", "metric": "completed_encounters", "target": 3, "kind": "breadth"},
    {"id": "returned_after_error", "icon": "↺", "name": "Вернувшийся звон", "description": "Победи после ошибки и восстанови серию не короче 8.", "metric": "recovery_proofs", "target": 1, "kind": "mastery"},
    {"id": "three_disciplines", "icon": "✦", "name": "Три дисциплины", "description": "Докажи три разных испытания мастерства.", "metric": "mastery_proofs", "target": 3, "kind": "mastery"},
    {"id": "living_build", "icon": "⌘", "name": "Живая сборка", "description": "Заверши забеги с четырьмя разными усилениями суммарно.", "metric": "distinct_upgrades", "target": 4, "kind": "breadth"},
    {"id": "rhythm_without_chain", "icon": "◌", "name": "Ритм без цепи", "description": "Выполни Контракт Ритма в четыре разные даты; пропуски ничего не сбрасывают.", "metric": "rhythm_days", "target": 4, "kind": "rhythm"},
    {"id": "trusted_companion", "icon": "🐾", "name": "Три языка заботы", "description": "Открой кормление, игру и уход как три разные сцены со спутником.", "metric": "distinct_care_actions", "target": 3, "kind": "companion"},
    {"id": "field_archive", "icon": "🗺", "name": "Полевой архив", "description": "Вернись из походов с тремя разными находками.", "metric": "distinct_discoveries", "target": 3, "kind": "discovery"},
    {"id": "case_1_closed", "icon": "▥", "name": "Первое закрытое дело", "description": "Заверши одно Недельное Дело и сохрани его финал в Архиве.", "metric": "weekly_cases_completed", "target": 1, "kind": "story"},
    {"id": "pack_2_witness", "icon": "⌁", "name": "Свидетель второго свода", "description": "Заверши хотя бы одно Дело из второго неизменяемого свода историй.", "metric": "pack_2_cases_completed", "target": 1, "kind": "story"},
    {"id": "scar_map_complete", "icon": "✧", "name": "Созвездие шрамов", "description": "Заверши одну Карту Шрамов, открыв любые девять узлов за цикл.", "metric": "scar_maps_completed", "target": 1, "kind": "mastery"},
)


def feat_definition_digest(feat: Mapping[str, Any]) -> str:
    canonical = json.dumps(dict(feat), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def evaluate_feats(snapshot: Mapping[str, int]) -> list[dict[str, Any]]:
    """Build a bounded public view from trusted aggregate facts."""
    result: list[dict[str, Any]] = []
    for order, feat in enumerate(FEATS):
        raw = snapshot.get(str(feat["metric"]), 0)
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ValueError(f"Feat metric {feat['metric']} must be an integer.")
        current = max(0, raw)
        target = int(feat["target"])
        visible_progress = min(current, target)
        result.append({
            "id": feat["id"], "icon": feat["icon"], "name": feat["name"],
            "description": feat["description"], "kind": feat["kind"],
            "progress": visible_progress, "target": target,
            "pct": round(visible_progress / target * 100),
            "completed": current >= target, "order": order,
            "reward": None, "competitive": False,
        })
    return result


def validate_feats() -> list[str]:
    errors: list[str] = []
    ids = [str(item.get("id") or "") for item in FEATS]
    if len(ids) != len(set(ids)):
        errors.append("feat ids must be unique")
    for item in FEATS:
        if int(item.get("target") or 0) <= 0:
            errors.append(f"{item.get('id')}: target must be positive")
        if not item.get("description") or not item.get("metric"):
            errors.append(f"{item.get('id')}: missing player-facing contract")
    return errors


_CONTENT_ERRORS = validate_feats()
if _CONTENT_ERRORS:
    raise RuntimeError("Invalid Chronicle feats: " + "; ".join(_CONTENT_ERRORS))
