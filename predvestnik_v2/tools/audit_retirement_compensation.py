#!/usr/bin/env python3
"""Aggregate-only local snapshot audit for retirement compensation planning.

This is deliberately *not* a migration or payout tool.  It only inspects an
explicit local PostgreSQL snapshot and emits a deterministic, PII-free report
of retained legacy-combat obligations.  It never reads DATABASE_URL/.env and
refuses non-loopback DSNs, so it cannot accidentally query production.

Example (only against a restored local snapshot):
  python tools/audit_retirement_compensation.py \
    --dsn 'postgresql://readonly@127.0.0.1/predvestnik_snapshot' \
    --snapshot-id cutover-2026-08-24 --cutoff-utc 2026-08-24T00:00:00Z
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


AUDIT_VERSION = "retirement-compensation-inventory-v1"
SCHEMA = "predvestnik"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", None}
SNAPSHOT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class AuditInputError(ValueError):
    """The requested audit is unsafe or does not identify one frozen snapshot."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _as_json_value(value: object) -> object:
    """Convert asyncpg records/decimal/date values without exposing raw state."""
    if isinstance(value, Mapping):
        return {str(key): _as_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_as_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_as_json_value(item) for item in value]
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def validate_local_snapshot_args(dsn: str, snapshot_id: str, cutoff_utc: str) -> datetime:
    """Reject ambient and remote connections before importing a database driver."""
    if not dsn or not isinstance(dsn, str):
        raise AuditInputError("Нужен явный локальный PostgreSQL DSN.")
    parsed = urlparse(dsn)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise AuditInputError("DSN должен быть postgres:// или postgresql:// URL.")
    if parsed.hostname not in LOCAL_HOSTS:
        raise AuditInputError("Инвентарь разрешён только для локального snapshot DSN.")
    if not SNAPSHOT_ID_RE.fullmatch(snapshot_id or ""):
        raise AuditInputError("snapshot_id должен быть коротким неизменяемым идентификатором.")
    try:
        parsed_cutoff = datetime.fromisoformat((cutoff_utc or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuditInputError("cutoff_utc должен быть ISO-8601 временем frozen snapshot.") from exc
    if parsed_cutoff.tzinfo is None:
        raise AuditInputError("cutoff_utc обязан содержать timezone, например Z.")
    return parsed_cutoff.astimezone(timezone.utc)


def _category(status: str, **fields: object) -> dict[str, object]:
    return {"status": status, **{name: _as_json_value(value) for name, value in fields.items()}}


async def load_catalog(conn, table_names: Iterable[str]) -> dict[str, set[str]]:
    """Return current columns; missing relations intentionally have an empty set."""
    names = sorted(set(table_names))
    rows = await conn.fetch(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = $1 AND table_name = ANY($2::text[])
        ORDER BY table_name, column_name
        """,
        SCHEMA,
        names,
    )
    catalog = {name: set() for name in names}
    for row in rows:
        catalog[str(row["table_name"])].add(str(row["column_name"]))
    return catalog


def category_readiness(catalog: Mapping[str, set[str]], requirements: Mapping[str, set[str]]) -> dict[str, object] | None:
    missing_tables = sorted(name for name in requirements if not catalog.get(name))
    if missing_tables:
        return _category("missing_table", missing_tables=missing_tables)
    missing_columns = {
        name: sorted(required - catalog[name])
        for name, required in requirements.items()
        if required - catalog[name]
    }
    if missing_columns:
        return _category("missing_columns", missing_columns=missing_columns)
    return None


def _manual(category: dict[str, object], *reasons: str) -> dict[str, object]:
    if reasons:
        category["status"] = "manual_recovery_required"
        category["manual_recovery_reasons"] = sorted(set(reasons))
    return category


async def audit_units(conn, catalog) -> dict[str, object]:
    requirements = {
        "user_units": {"user_id", "unit_id", "level", "shards", "obtained_at"},
        "user_squad": {"user_id", "slot", "unit_id"},
    }
    if issue := category_readiness(catalog, requirements):
        return issue
    units = await conn.fetchrow(
        """/* retirement_inventory:units */
        SELECT count(*)::bigint AS rows,
               count(DISTINCT user_id)::bigint AS owners,
               count(*) FILTER (WHERE level >= 1)::bigint AS opened_rows,
               count(*) FILTER (WHERE level = 0 AND shards > 0)::bigint AS partial_unlock_rows,
               coalesce(sum(shards), 0)::bigint AS shards_total,
               count(*) FILTER (WHERE level < 0 OR shards < 0)::bigint AS invalid_rows
        FROM predvestnik.user_units"""
    )
    squad = await conn.fetchrow(
        """/* retirement_inventory:user_squad */
        SELECT count(*)::bigint AS rows,
               count(DISTINCT user_id)::bigint AS owners,
               count(*) FILTER (WHERE slot < 0 OR slot > 2)::bigint AS invalid_slot_rows,
               count(*) FILTER (WHERE NOT EXISTS (
                 SELECT 1 FROM predvestnik.user_units u
                 WHERE u.user_id = s.user_id AND u.unit_id = s.unit_id
               ))::bigint AS orphan_unit_rows
        FROM predvestnik.user_squad s"""
    )
    payload = _category("ok", units=dict(units), squad=dict(squad))
    return _manual(
        payload,
        *( ["invalid_unit_values"] if units["invalid_rows"] else [] ),
        *( ["invalid_squad_layout"] if squad["invalid_slot_rows"] or squad["orphan_unit_rows"] else [] ),
    )


async def audit_battles(conn, catalog, json_validation_supported: bool) -> dict[str, object]:
    requirements = {"battles": {"id", "user_id", "mode", "ref_id", "status", "state_json", "created_at"}}
    if issue := category_readiness(catalog, requirements):
        return issue
    rows = await conn.fetch(
        """/* retirement_inventory:battles */
        SELECT mode, status, count(*)::bigint AS rows, count(DISTINCT user_id)::bigint AS owners
        FROM predvestnik.battles GROUP BY mode, status ORDER BY mode, status"""
    )
    if json_validation_supported:
        invalid_states = await conn.fetchval(
            """/* retirement_inventory:battles_json */
            SELECT count(*)::bigint FROM predvestnik.battles
            WHERE NOT pg_input_is_valid(state_json, 'jsonb'::regtype)"""
        )
        json_validation = "validated"
    else:
        invalid_states = None
        json_validation = "unsupported_by_snapshot_postgres"
    active_rows = sum(int(row["rows"]) for row in rows if row["status"] == "active")
    payload = _category(
        "ok", mode_status=[dict(row) for row in rows], active_rows=active_rows,
        invalid_state_json_rows=invalid_states, json_validation=json_validation,
    )
    reasons = []
    if active_rows:
        reasons.append("unfinished_legacy_battles")
    if invalid_states:
        reasons.append("invalid_battle_state_json")
    if not json_validation_supported:
        reasons.append("battle_json_validation_unsupported")
    return _manual(payload, *reasons)


async def audit_duel_escrow(conn, catalog, cutoff: datetime) -> dict[str, object]:
    requirements = {
        "duels": {"id", "challenger_id", "stake", "status", "created_at"},
        "user_reserve": {"user_id", "reserved_mora"},
    }
    if issue := category_readiness(catalog, requirements):
        return issue
    row = await conn.fetchrow(
        """/* retirement_inventory:duel_escrow */
        WITH pending AS (
          SELECT challenger_id, stake, created_at FROM predvestnik.duels WHERE status = 'pending'
        )
        SELECT count(*)::bigint AS pending_rows,
               count(DISTINCT challenger_id)::bigint AS challengers,
               coalesce(sum(stake), 0)::numeric AS pending_stake,
               count(*) FILTER (WHERE created_at <= $1)::bigint AS pending_at_cutoff,
               (SELECT coalesce(sum(reserved_mora), 0)::numeric FROM predvestnik.user_reserve) AS all_reserve,
               count(*) FILTER (WHERE stake < 0)::bigint AS invalid_stake_rows
        FROM pending""",
        cutoff,
    )
    payload = _category("ok", **dict(row))
    reasons = []
    if row["pending_rows"]:
        reasons.append("pending_duel_escrow_requires_release_or_owner_decision")
    if row["pending_stake"] > row["all_reserve"]:
        reasons.append("pending_duel_stake_exceeds_shared_reserve")
    if row["invalid_stake_rows"]:
        reasons.append("invalid_duel_stake")
    return _manual(payload, *reasons)


async def audit_legacy_expeditions(conn, catalog, cutoff: datetime) -> dict[str, object]:
    requirements = {
        "active_expeditions": {"pet_id", "chat_id", "duration_hours", "cost_mora", "ends_at"},
        "pets": {"id", "owner_id"},
    }
    if issue := category_readiness(catalog, requirements):
        return issue
    has_early_finish = "early_finish" in catalog["active_expeditions"]
    early_expr = "count(*) FILTER (WHERE e.early_finish)" if has_early_finish else "NULL::bigint"
    row = await conn.fetchrow(
        f"""/* retirement_inventory:legacy_expeditions */
        SELECT count(*)::bigint AS rows,
               count(DISTINCT p.owner_id)::bigint AS owners,
               coalesce(sum(e.cost_mora), 0)::numeric AS prepaid_mora,
               count(*) FILTER (WHERE e.ends_at <= $1)::bigint AS overdue_rows,
               {early_expr}::bigint AS early_finish_rows,
               count(*) FILTER (WHERE p.id IS NULL)::bigint AS orphan_pet_rows
        FROM predvestnik.active_expeditions e
        LEFT JOIN predvestnik.pets p ON p.id = e.pet_id""",
        cutoff,
    )
    payload = _category("ok", early_finish_column_present=has_early_finish, **dict(row))
    return _manual(
        payload,
        *( ["legacy_expedition_settlement_due"] if row["rows"] else [] ),
        *( ["overdue_legacy_expedition"] if row["overdue_rows"] else [] ),
        *( ["orphan_legacy_expedition_pet"] if row["orphan_pet_rows"] else [] ),
    )


async def audit_shadow_gates(conn, catalog, cutoff: datetime) -> dict[str, object]:
    requirements = {
        "shadow_gate_runs": {"pet_id", "user_id", "started_at", "dark_mora", "status"},
        "pets": {"id", "owner_id", "placement"},
    }
    if issue := category_readiness(catalog, requirements):
        return issue
    row = await conn.fetchrow(
        """/* retirement_inventory:shadow_gates */
        SELECT
          (SELECT count(*)::bigint FROM predvestnik.shadow_gate_runs WHERE status = 'active') AS active_rows,
          (SELECT coalesce(sum(dark_mora), 0)::numeric FROM predvestnik.shadow_gate_runs WHERE status = 'active') AS accrued_dark_mora,
          (SELECT count(*)::bigint FROM predvestnik.shadow_gate_runs g
             LEFT JOIN predvestnik.pets p ON p.id = g.pet_id
            WHERE g.status = 'active' AND p.id IS NULL) AS orphan_pet_rows,
          (SELECT count(*)::bigint FROM predvestnik.shadow_gate_runs
            WHERE status = 'active' AND started_at <= $1 - interval '12 hours') AS cap_exceeded_rows,
          (SELECT count(*)::bigint FROM predvestnik.pets p
             LEFT JOIN predvestnik.shadow_gate_runs g ON g.pet_id = p.id AND g.status = 'active'
            WHERE p.placement = 'gates' AND g.pet_id IS NULL) AS placement_without_run_rows""",
        cutoff,
    )
    payload = _category("ok", **dict(row))
    return _manual(
        payload,
        *( ["active_shadow_gate_requires_settlement"] if row["active_rows"] else [] ),
        *( ["shadow_gate_over_cap"] if row["cap_exceeded_rows"] else [] ),
        *( ["shadow_gate_pet_orphan"] if row["orphan_pet_rows"] else [] ),
        *( ["pet_placement_gate_mismatch"] if row["placement_without_run_rows"] else [] ),
    )


async def audit_raids(conn, catalog, cutoff: datetime) -> dict[str, object]:
    requirements = {
        "clan_raids": {"raid_id", "clan_id", "status", "ends_at"},
        "raid_contributions": {"raid_id", "user_id", "damage"},
    }
    if issue := category_readiness(catalog, requirements):
        return issue
    row = await conn.fetchrow(
        """/* retirement_inventory:raids */
        SELECT
          (SELECT count(*)::bigint FROM predvestnik.clan_raids WHERE status = 'active') AS active_rows,
          (SELECT count(*)::bigint FROM predvestnik.clan_raids WHERE status = 'active' AND ends_at <= $1) AS overdue_rows,
          (SELECT count(*)::bigint FROM predvestnik.raid_contributions) AS contribution_rows,
          (SELECT count(DISTINCT user_id)::bigint FROM predvestnik.raid_contributions) AS contributors,
          (SELECT coalesce(sum(damage), 0)::numeric FROM predvestnik.raid_contributions) AS contribution_damage,
          (SELECT count(*)::bigint FROM predvestnik.raid_contributions c
             LEFT JOIN predvestnik.clan_raids r ON r.raid_id = c.raid_id
            WHERE r.raid_id IS NULL) AS orphan_contribution_rows""",
        cutoff,
    )
    payload = _category("ok", **dict(row))
    return _manual(
        payload,
        *( ["active_raid_requires_owner_decision"] if row["active_rows"] else [] ),
        *( ["overdue_raid"] if row["overdue_rows"] else [] ),
        *( ["orphan_raid_contribution"] if row["orphan_contribution_rows"] else [] ),
    )


async def audit_clan_abyss(conn, catalog) -> dict[str, object]:
    requirements = {
        "clan_abyss": {"clan_id", "week_key", "floor"},
        "clan_abyss_contrib": {"clan_id", "user_id", "week_key", "shards"},
        "clan_abyss_opens": {"user_id", "day", "cnt"},
    }
    if issue := category_readiness(catalog, requirements):
        return issue
    row = await conn.fetchrow(
        """/* retirement_inventory:clan_abyss */
        SELECT
          (SELECT count(*)::bigint FROM predvestnik.clan_abyss) AS state_rows,
          (SELECT count(DISTINCT clan_id)::bigint FROM predvestnik.clan_abyss) AS clans,
          (SELECT count(*)::bigint FROM predvestnik.clan_abyss_contrib) AS contribution_rows,
          (SELECT count(DISTINCT user_id)::bigint FROM predvestnik.clan_abyss_contrib) AS contributors,
          (SELECT coalesce(sum(shards), 0)::numeric FROM predvestnik.clan_abyss_contrib) AS contributed_shards,
          (SELECT count(*)::bigint FROM predvestnik.clan_abyss_opens) AS opens_rows,
          (SELECT count(*)::bigint FROM predvestnik.clan_abyss_opens WHERE cnt < 0) AS invalid_open_rows"""
    )
    payload = _category("ok", **dict(row))
    return _manual(
        payload,
        *( ["clan_abyss_progress_requires_owner_decision"] if row["state_rows"] or row["contribution_rows"] else [] ),
        *( ["invalid_abyss_open_counter"] if row["invalid_open_rows"] else [] ),
    )


async def audit_clan_wars(conn, catalog, cutoff: datetime) -> dict[str, object]:
    requirements = {
        "war_nodes": {"id", "owner_clan_id"},
        "clan_wars2": {"id", "node_id", "status", "ends_at"},
        "clan_war_attacks": {"war_id", "user_id", "damage"},
    }
    if issue := category_readiness(catalog, requirements):
        return issue
    row = await conn.fetchrow(
        """/* retirement_inventory:clan_wars */
        SELECT
          (SELECT count(*)::bigint FROM predvestnik.war_nodes WHERE owner_clan_id IS NOT NULL) AS owned_nodes,
          (SELECT count(*)::bigint FROM predvestnik.clan_wars2 WHERE status = 'active') AS active_rows,
          (SELECT count(*)::bigint FROM predvestnik.clan_wars2 WHERE status = 'active' AND ends_at <= $1) AS overdue_rows,
          (SELECT count(*)::bigint FROM predvestnik.clan_war_attacks) AS attack_rows,
          (SELECT count(DISTINCT user_id)::bigint FROM predvestnik.clan_war_attacks) AS attackers,
          (SELECT coalesce(sum(damage), 0)::numeric FROM predvestnik.clan_war_attacks) AS attack_damage,
          (SELECT count(*)::bigint FROM predvestnik.clan_war_attacks a
             LEFT JOIN predvestnik.clan_wars2 w ON w.id = a.war_id
            WHERE w.id IS NULL) AS orphan_attack_rows""",
        cutoff,
    )
    payload = _category("ok", **dict(row))
    return _manual(
        payload,
        *( ["active_clan_war_requires_owner_decision"] if row["active_rows"] else [] ),
        *( ["overdue_clan_war"] if row["overdue_rows"] else [] ),
        *( ["orphan_clan_war_attack"] if row["orphan_attack_rows"] else [] ),
    )


async def audit_clan_balances(conn, catalog) -> dict[str, object]:
    requirements = {
        "clans": {"clan_id", "treasury_shards", "treasury_mora"},
        "clan_members": {"clan_id", "user_id", "clan_coins"},
        "clan_buildings": {"clan_id", "key", "level"},
    }
    if issue := category_readiness(catalog, requirements):
        return issue
    row = await conn.fetchrow(
        """/* retirement_inventory:clan_balances */
        SELECT
          (SELECT count(*)::bigint FROM predvestnik.clans) AS clans,
          (SELECT coalesce(sum(treasury_shards), 0)::numeric FROM predvestnik.clans) AS treasury_shards,
          (SELECT coalesce(sum(treasury_mora), 0)::numeric FROM predvestnik.clans) AS treasury_mora,
          (SELECT count(*)::bigint FROM predvestnik.clan_members WHERE clan_coins <> 0) AS member_coin_rows,
          (SELECT coalesce(sum(clan_coins), 0)::numeric FROM predvestnik.clan_members) AS member_coins,
          (SELECT count(*)::bigint FROM predvestnik.clan_buildings) AS building_rows,
          (SELECT count(*)::bigint FROM predvestnik.clan_buildings WHERE level < 0) AS invalid_building_rows"""
    )
    payload = _category("ok", **dict(row))
    return _manual(
        payload,
        *( ["legacy_clan_assets_require_owner_decision"] if row["treasury_shards"] or row["treasury_mora"] or row["member_coins"] or row["building_rows"] else [] ),
        *( ["invalid_clan_building_level"] if row["invalid_building_rows"] else [] ),
    )


async def collect_inventory(conn, snapshot_id: str, cutoff: datetime) -> dict[str, object]:
    tables = {
        "user_units", "user_squad", "battles", "duels", "user_reserve",
        "active_expeditions", "pets", "shadow_gate_runs", "clan_raids",
        "raid_contributions", "clan_abyss", "clan_abyss_contrib", "clan_abyss_opens",
        "war_nodes", "clan_wars2", "clan_war_attacks", "clans", "clan_members",
        "clan_buildings",
    }
    catalog = await load_catalog(conn, tables)
    json_validation_supported = bool(await conn.fetchval(
        "SELECT to_regprocedure('pg_input_is_valid(text,regtype)') IS NOT NULL"
    ))
    categories = {
        "units": await audit_units(conn, catalog),
        "battles": await audit_battles(conn, catalog, json_validation_supported),
        "duel_escrow": await audit_duel_escrow(conn, catalog, cutoff),
        "legacy_expeditions": await audit_legacy_expeditions(conn, catalog, cutoff),
        "shadow_gates": await audit_shadow_gates(conn, catalog, cutoff),
        "raids": await audit_raids(conn, catalog, cutoff),
        "clan_abyss": await audit_clan_abyss(conn, catalog),
        "clan_wars": await audit_clan_wars(conn, catalog, cutoff),
        "clan_balances": await audit_clan_balances(conn, catalog),
    }
    return {
        "audit_version": AUDIT_VERSION,
        "snapshot_id": snapshot_id,
        "cutoff_utc": cutoff.isoformat().replace("+00:00", "Z"),
        "categories": categories,
    }


def finalize_report(report: Mapping[str, object]) -> dict[str, object]:
    payload = _as_json_value(dict(report))
    canonical = _canonical_json(payload)
    return {**payload, "checksum_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}


async def run_audit(dsn: str, snapshot_id: str, cutoff: datetime) -> dict[str, object]:
    try:
        import asyncpg
    except ImportError as exc:  # pragma: no cover - runtime dependency only
        raise RuntimeError("Для запуска аудита нужен asyncpg из runtime-окружения проекта.") from exc
    conn = await asyncpg.connect(dsn)
    try:
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            await conn.execute("SET LOCAL search_path TO predvestnik, public")
            return finalize_report(await collect_inventory(conn, snapshot_id, cutoff))
    finally:
        await conn.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", required=True, help="Explicit local restored-snapshot PostgreSQL URL")
    parser.add_argument("--snapshot-id", required=True, help="Immutable identifier of the restored local snapshot")
    parser.add_argument("--cutoff-utc", required=True, help="UTC cutoff from that frozen snapshot, ISO-8601")
    parser.add_argument("--output", type=Path, help="Optional local JSON output path; stdout remains canonical")
    return parser.parse_args(argv)


async def _main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        cutoff = validate_local_snapshot_args(args.dsn, args.snapshot_id, args.cutoff_utc)
        report = await run_audit(args.dsn, args.snapshot_id, cutoff)
    except (AuditInputError, RuntimeError) as exc:
        print(f"AUDIT BLOCKED: {exc}", file=sys.stderr)
        return 2
    rendered = _canonical_json(report)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
