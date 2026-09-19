"""Monotonic Chronicle feats projected from authoritative, compatible state."""
from __future__ import annotations

from typing import Any

from core.feats_v1 import COMPATIBLE_GAME_VERSIONS, FEATS, FEATS_VERSION, evaluate_feats, feat_definition_digest
from core.reconstruction import CLICKER_UPGRADES, ENCOUNTERS, MEMORIES
from core.scar_map_v1 import FINAL_REQUIRED, POLICY_VERSION as SCAR_POLICY, unlocked_node_ids
from core.weekly_case_v1 import CASE_CATALOG, CONTENT_PACKS, definition_digest
from infrastructure.repositories import companions_v3 as companion_repo
from infrastructure.repositories import feats_v1 as receipt_repo
from infrastructure.repositories import reconstruction as reconstruction_repo
from infrastructure.repositories import reconstruction_units as unit_repo
from infrastructure.repositories import retention_v3 as retention_repo
from infrastructure.repositories import scar_map_v1 as scar_repo
from infrastructure.repositories import weekly_case_v1 as weekly_repo


def _verified_weekly_counts(rows: list[dict[str, Any]]) -> tuple[int, int]:
    definitions = {str(case["case_id"]): case for case in CASE_CATALOG}
    pack_2_ids = set(CONTENT_PACKS[1]["case_ids"])
    completed: set[str] = set()
    for row in rows:
        case = definitions.get(str(row.get("case_id") or ""))
        if not case or str(row.get("definition_digest") or "") != definition_digest(case):
            continue
        if str(row.get("policy_version") or "") != str(case["policy_version"]):
            continue
        if not row.get("completed_at") or int(row.get("progress_days") or 0) != int(case["target_days"]):
            continue
        if str(row.get("path_id") or "") not in case["paths"]:
            continue
        if str(row.get("finale_id") or "") not in case["finales"]:
            continue
        completed.add(str(case["case_id"]))
    return len(completed), len(completed & pack_2_ids)


def _verified_scar_completions(rows: list[dict[str, Any]]) -> int:
    completed = 0
    for row in rows:
        if str(row.get("policy_version") or "") != SCAR_POLICY or not row.get("completed_at"):
            continue
        try:
            counters, encounters = scar_repo.decode_state(row)
        except (TypeError, ValueError):
            continue
        if len(unlocked_node_ids(counters, encounters)) >= FINAL_REQUIRED:
            completed += 1
    return completed


async def get_user_feats(db, user_id: int) -> dict[str, Any]:
    if int(user_id) <= 0:
        raise ValueError("user_id must be positive")
    async with db.connection.transaction():
        await reconstruction_repo.lock_user(db, int(user_id))
        progress_rows, stats_rows = [], []
        for game_version in COMPATIBLE_GAME_VERSIONS:
            progress = await reconstruction_repo.get_progress(db, int(user_id), game_version)
            if progress:
                progress_rows.append(progress)
            stats = await reconstruction_repo.get_stats(db, int(user_id), game_version)
            if stats and int(stats.get("runs_started") or 0) > 0:
                stats_rows.append(stats)
        proofs = await unit_repo.get_clear_mastery_proof_ids_for_versions(db, int(user_id), COMPATIBLE_GAME_VERSIONS)
        discoveries = await companion_repo.list_claimed_discovery_ids(db, int(user_id))
        care_actions = await companion_repo.list_distinct_care_actions(db, int(user_id))
        rhythm_days = await retention_repo.count_completed_total_all_versions(db, int(user_id))
        weekly_completed, pack_2_completed = _verified_weekly_counts(await weekly_repo.all_cases(db, int(user_id)))
        scar_completed = _verified_scar_completions(await scar_repo.completed_cycles(db, int(user_id)))

        completed_encounters = {value for row in progress_rows for value in (row.get("completed") or []) if value in ENCOUNTERS}
        memories = {value for row in progress_rows for value in (row.get("memories") or []) if value in MEMORIES}
        route_choices = {value for row in progress_rows for value in (row.get("route_choices") or {}).values() if value in {"ink", "ash"}}
        distinct_upgrades = {key for row in stats_rows for key, value in (row.get("upgrades") or {}).items() if key in CLICKER_UPGRADES and int(value) > 0}
        snapshot = {
            "completed_encounters": len(completed_encounters), "memories": len(memories),
            "route_choices": len(route_choices), "recovery_proofs": int("bell_recover_three_clean" in proofs),
            "mastery_proofs": len(proofs), "distinct_upgrades": len(distinct_upgrades),
            "rhythm_days": int(rhythm_days), "distinct_care_actions": len(set(care_actions)),
            "distinct_discoveries": len(set(discoveries)), "weekly_cases_completed": weekly_completed,
            "pack_2_cases_completed": pack_2_completed, "scar_maps_completed": scar_completed,
        }
        feats = evaluate_feats(snapshot)
        definitions = {str(feat["id"]): feat for feat in FEATS}
        receipts = await receipt_repo.list_receipts(db, int(user_id))
        for feat_id, receipt in receipts.items():
            feat = definitions.get(feat_id)
            if not feat or receipt["definition_digest"] != feat_definition_digest(feat):
                raise RuntimeError("Chronicle feat receipt definition conflict")
        for item in feats:
            if item["completed"] and item["id"] not in receipts:
                feat = definitions[str(item["id"])]
                await receipt_repo.record_receipt(
                    db, user_id=int(user_id), feat_id=str(item["id"]), feat_version=FEATS_VERSION,
                    definition_digest=feat_definition_digest(feat),
                    evidence={"metric": feat["metric"], "value": int(snapshot[feat["metric"]]), "target": int(feat["target"])},
                )
        receipts = await receipt_repo.list_receipts(db, int(user_id))
        for item in feats:
            receipt = receipts.get(str(item["id"]))
            if receipt:
                item.update({"completed": True, "progress": int(item["target"]), "pct": 100, "achieved_at": receipt["achieved_at"]})
            else:
                item["achieved_at"] = None
        return {"version": FEATS_VERSION,
                "message": "Подвиги — постоянные отметки за путь, выбор и мастерство. Они не выдают валюту или силу.",
                "competitive": False, "rewards_enabled": False,
                "completed": sum(item["completed"] for item in feats), "total": len(feats), "feats": feats}
