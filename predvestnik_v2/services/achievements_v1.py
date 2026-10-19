"""Server-authoritative achievements from immutable activity terminals only."""
from __future__ import annotations

from datetime import date, datetime, timezone

from core import achievements_v1 as rules
from infrastructure.repositories import achievements_v1 as repo
from infrastructure.repositories import economy_ledger


class AchievementConflict(rules.AchievementPolicyError):
    pass


def _week_key(now: datetime) -> date:
    moment = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return date.fromisocalendar(moment.isocalendar().year, moment.isocalendar().week, 1)


def _source_event_id(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > 160 or any(ord(char) < 32 for char in normalized):
        raise rules.AchievementPolicyError("Invalid terminal event id.")
    return normalized


async def record_terminal(
    db, *, user_id: int, metric: str, source_event_id: str, source_snapshot: dict,
    now: datetime | None = None,
) -> dict:
    """Project one verified terminal game event into its achievement family.

    This is intentionally not a public API.  Terminal game services call it
    with their server-owned run/match id in the same outer transaction.
    """
    rules.validate()
    family = rules.family_for_metric(metric)
    source_event_id = _source_event_id(source_event_id)
    snapshot = dict(source_snapshot)
    now = now or datetime.now(timezone.utc)
    definition = rules.FAMILIES[family]
    async with db.connection.transaction():
        await repo.lock_user(db, int(user_id))
        inserted = await repo.save_metric_receipt(
            db, user_id=int(user_id), family=family, source_event_id=source_event_id,
            source_kind=str(definition["source_kind"]), source_snapshot=snapshot,
        )
        progress = await repo.lock_progress(db, user_id=int(user_id), family=family)
        if not inserted:
            return {"family": family, "level": int(progress["level"]), "idempotent_replay": True, "awards": []}
        first_week = await repo.save_active_week(db, user_id=int(user_id), family=family, week_key=_week_key(now))
        completed = int(progress["completed_events"]) + 1
        active_weeks = int(progress["active_weeks"]) + int(first_week)
        previous_level = int(progress["level"])
        level = rules.unlocked_level(family, completed_events=completed, active_weeks=active_weeks)
        await repo.save_progress(db, user_id=int(user_id), family=family, completed_events=completed,
                                 active_weeks=active_weeks, level=level)
        awards = []
        for reached_level in range(previous_level + 1, level + 1):
            amount = rules.reward_mora(reached_level)
            if not await repo.reserve_reward(db, user_id=int(user_id), family=family, level=reached_level,
                                             amount_mora=amount, policy_version=rules.POLICY_VERSION):
                raise AchievementConflict("Achievement level reward receipt conflict.")
            mutation = await economy_ledger.apply_balance_change(
                db, int(user_id), {"mora": amount}, reason_code="achievement_reward",
                idempotency_key=f"achievement-v1:{family}:{reached_level}", source_type="achievement",
                reference_type="achievement_level", reference_id=f"{family}:{reached_level}",
                metadata={"policy_version": rules.POLICY_VERSION, "family": family,
                          "level": reached_level, "amount_mora": amount},
                note=f"Достижение {definition['title']} · уровень {reached_level}",
            )
            awards.append({"level": reached_level, "amount_mora": amount, "operation_id": mutation.operation_id})
    return {"family": family, "level": level, "completed_events": completed,
            "active_weeks": active_weeks, "idempotent_replay": False, "awards": awards}


async def overview(db, *, user_id: int) -> dict:
    """Read-only view; no legacy counters are imported or trusted."""
    rows = {str(row["family"]): row for row in await repo.list_progress(db, int(user_id))}
    rewards = await repo.list_rewards(db, int(user_id))
    families = []
    for family, definition in rules.FAMILIES.items():
        row = rows.get(family) or {"completed_events": 0, "active_weeks": 0, "level": 0}
        level = int(row["level"])
        completed_events = int(row["completed_events"])
        active_weeks = int(row["active_weeks"])
        next_level = level + 1 if level < rules.max_level(family) else None
        milestones = [{
            "level": milestone,
            "events_required": rules.event_threshold(family, milestone),
            "weeks_required": rules.required_weeks(family, milestone),
            "reward_mora": rules.reward_mora(milestone),
            "status": "claimed" if (family, milestone) in rewards else ("reached" if level >= milestone else "locked"),
        } for milestone in rules.milestones(family)]
        families.append({
            "id": family, "title": definition["title"], "icon": definition["icon"],
            "category": definition["category"], "help": definition["help"],
            "action_label": definition["action_label"], "level": level,
            "max_level": rules.max_level(family), "week_gate": rules.required_weeks(family, rules.max_level(family)), "measure": definition.get("measure", ("завершение", "завершения", "завершений")), "completed_events": completed_events,
            "active_weeks": active_weeks, "next": None if next_level is None else {
                "level": next_level, "events_required": rules.event_threshold(family, next_level),
                "weeks_required": rules.required_weeks(family, next_level), "reward_mora": rules.reward_mora(next_level),
            },
            "claimed_levels": [number for number in range(1, level + 1) if (family, number) in rewards],
            "milestones": milestones,
        })
    return {"policy_version": rules.POLICY_VERSION, "currency": "mora", "max_active_weeks": rules.MAX_ACTIVE_WEEKS,
            "summary": {"families": len(families), "total_levels": sum(item["level"] for item in families),
                        "max_levels": sum(item["max_level"] for item in families),
                        "claimed_mora": sum(receipt["amount_mora"] for (family, _), receipt in rewards.items()
                                            if family in rules.FAMILIES)},
            "families": families,
            "message": "Серии за игры и приключения сохраняют прежние условия. Серии развития учитывают подтверждённые действия без требования активных недель."}


def _validate_life_fact(family: str, fact: str) -> str:
    """Canonical fact identity is shared by live writers and history projection."""
    from core.skins_v3_catalog import SKINS
    from core.skins_v3 import TIERS
    fact = str(fact)
    if family in {'care', 'quester'}:
        if date.fromisoformat(fact).isoformat() != fact:
            raise rules.AchievementPolicyError('Invalid canonical day')
    elif family == 'builder':
        building, level = fact.split(':')
        if building not in {'lounge', 'markers', 'workshop'} or level not in {'1','2','3','4','5'}:
            raise rules.AchievementPolicyError('Invalid camp fact')
    elif family == 'stylist':
        skin, tier = fact.split(':')
        if skin not in SKINS or tier not in TIERS[1:]:
            raise rules.AchievementPolicyError('Invalid skin fact')
    else:
        raise rules.AchievementPolicyError('Unknown life achievement')
    return fact


async def record_life_event(db, *, user_id: int, family: str, fact: str) -> dict:
    fact = _validate_life_fact(family, fact)
    return await record_terminal(db, user_id=user_id, metric=rules.FAMILIES[family]['metric'],
                                 source_event_id=fact, source_snapshot={'fact':fact})


async def reconcile_history(db, *, user_id: int) -> dict:
    """Incremental owned projection from successful durable receipts; no counters."""
    import json
    version = 'life-history-2026-10-19'
    facts = {'care':set(), 'builder':set(), 'stylist':set(), 'quester':set()}
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        imported_before = await repo.history_imported(db, user_id, version)
        known = await repo.known_life_facts(db, user_id)
        source = await repo.life_history_sources(db, user_id)
        for row in source['upgrades']:
            family = 'stylist' if row['reason']=='skin_upgrade' else 'builder'
            facts[family].add(str(row['reference']))
        for row in source['feeds']:
            try:
                request, response = json.loads(row['request_json']), json.loads(row['response_json'])
                if request.get('type')!='feed' or response.get('ok') is not True or response.get('pet_id')!=request.get('pet_id'):
                    continue
                day = row['created_at'].astimezone(timezone.utc).date()
                if day <= source['today']: facts['care'].add(day.isoformat())
            except (ValueError, TypeError, AttributeError):
                continue
        for row in source['quests']:
            value = str(row['reward_id'])
            if value.startswith('daily:'):
                try:
                    day = date.fromisoformat(value[6:])
                    if day <= source['today']: facts['quester'].add(day.isoformat())
                except ValueError:
                    continue
        count = 0
        for family, values in facts.items():
            for fact in sorted(values):
                if (family,fact) in known:
                    continue
                try:
                    _validate_life_fact(family, fact)
                except ValueError:
                    continue
                await record_life_event(db, user_id=user_id, family=family, fact=fact)
                count += 1
        await repo.mark_history_import(db, user_id, version)
    return {'already_reconciled':imported_before, 'facts':count}
