"""Read-only planning helpers for durable cosmetic entitlements.

The live entitlement remains ``user_cosmetics``.  This module does not mutate a
database: it classifies references collected by the audit script so a removal
can be planned before any player-visible change is made.
"""
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from core.cosmetics import COSMETICS, COSMETIC_LEGACY_ID_MAP


HISTORICAL_REFERENCE_SOURCES = {"refund_log", "lineup_wipe_log"}


def classify_cosmetic_id(
    cosmetic_id: str,
    registry: Mapping[str, Mapping[str, Any]] = COSMETICS,
    legacy_map: Mapping[str, str] = COSMETIC_LEGACY_ID_MAP,
) -> dict[str, Any]:
    """Classify an ID without changing ownership or resolving it silently."""
    current = registry.get(cosmetic_id)
    if current is not None:
        archived = bool(current.get("archived"))
        return {
            "status": "archived" if archived else "active",
            "target_id": None,
            "recommended_action": "keep_owner_only_archive" if archived else "keep",
        }

    target_id = legacy_map.get(cosmetic_id)
    if target_id and target_id in registry:
        return {
            "status": "legacy_alias",
            "target_id": target_id,
            "recommended_action": "versioned_alias_migration",
        }
    if target_id:
        return {
            "status": "legacy_target_missing",
            "target_id": target_id,
            "recommended_action": "restore_archive_or_approve_compensation",
        }
    return {
        "status": "unknown",
        "target_id": None,
        "recommended_action": "investigate_then_restore_archive",
    }


def build_cosmetic_lifecycle_report(
    references: Iterable[Mapping[str, Any]],
    registry: Mapping[str, Mapping[str, Any]] = COSMETICS,
    legacy_map: Mapping[str, str] = COSMETIC_LEGACY_ID_MAP,
    *,
    include_user_ids: bool = False,
) -> dict[str, Any]:
    """Aggregate normalized references into a privacy-safe removal report.

    Each reference may contain ``cosmetic_id``, ``source``, ``user_id`` and
    ``quantity``.  Default output contains counts, never player identifiers.
    """
    refs = list(references)
    by_id: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for ref in refs:
        cosmetic_id = str(ref.get("cosmetic_id") or "").strip()
        if cosmetic_id:
            by_id[cosmetic_id].append(ref)

    entries: list[dict[str, Any]] = []
    all_users: set[int] = set()
    status_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()

    for cosmetic_id in sorted(by_id):
        item_refs = by_id[cosmetic_id]
        live_refs = [
            ref for ref in item_refs
            if str(ref.get("source") or "unknown") not in HISTORICAL_REFERENCE_SOURCES
        ]
        historical_refs = [ref for ref in item_refs if ref not in live_refs]
        classification = classify_cosmetic_id(cosmetic_id, registry, legacy_map)
        users = {
            int(ref["user_id"])
            for ref in live_refs
            if ref.get("user_id") is not None
        }
        historical_users = {
            int(ref["user_id"])
            for ref in historical_refs
            if ref.get("user_id") is not None
        }
        all_users.update(users)
        per_source = Counter(str(ref.get("source") or "unknown") for ref in item_refs)
        source_counts.update(per_source)
        status_counts[classification["status"]] += 1

        issues: list[str] = []
        if "inventory" in per_source:
            issues.append("cosmetic_stored_as_stackable_inventory")
        if "bp_reward" in per_source and classification["status"] not in ("active", "archived"):
            issues.append("battle_pass_references_unresolvable_cosmetic")
        if live_refs and classification["status"] == "legacy_alias":
            issues.append("legacy_alias_pending_migration")
        elif live_refs and classification["status"] not in ("active", "archived"):
            issues.append("registry_definition_missing")

        entry: dict[str, Any] = {
            "cosmetic_id": cosmetic_id,
            **classification,
            "reference_count": sum(int(ref.get("quantity") or 1) for ref in live_refs),
            "historical_reference_count": sum(
                int(ref.get("quantity") or 1) for ref in historical_refs
            ),
            "affected_user_count": len(users),
            "historical_user_count": len(historical_users),
            "sources": dict(sorted(per_source.items())),
            "issues": issues,
            "safe_to_remove_definition": not live_refs,
        }
        if include_user_ids:
            entry["user_ids"] = sorted(users)
            entry["historical_user_ids"] = sorted(historical_users)
        entries.append(entry)

    unresolved = [
        item for item in entries
        if item["issues"] or (
            item["reference_count"] > 0
            and item["status"] not in ("active", "archived")
        )
    ]
    return {
        "summary": {
            "reference_rows": len(refs),
            "unique_cosmetic_ids": len(entries),
            "affected_user_count": len(all_users),
            "status_counts": dict(sorted(status_counts.items())),
            "source_counts": dict(sorted(source_counts.items())),
            "unresolved_id_count": len(unresolved),
        },
        "unresolved": unresolved,
        "all_ids": entries,
    }
