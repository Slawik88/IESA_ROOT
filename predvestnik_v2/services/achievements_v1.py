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
        next_level = level + 1 if level < rules.MAX_LEVEL else None
        milestones = [{
            "level": milestone,
            "events_required": rules.event_threshold(family, milestone),
            "weeks_required": rules.week_threshold(milestone),
            "reward_mora": rules.reward_mora(milestone),
            "status": "claimed" if (family, milestone) in rewards else ("reached" if level >= milestone else "locked"),
        } for milestone in rules.MILESTONE_LEVELS]
        families.append({
            "id": family, "title": definition["title"], "icon": definition["icon"],
            "category": definition["category"], "help": definition["help"],
            "action_label": definition["action_label"], "level": level,
            "max_level": rules.MAX_LEVEL, "completed_events": completed_events,
            "active_weeks": active_weeks, "next": None if next_level is None else {
                "level": next_level, "events_required": rules.event_threshold(family, next_level),
                "weeks_required": rules.week_threshold(next_level), "reward_mora": rules.reward_mora(next_level),
            },
            "claimed_levels": [number for number in range(1, level + 1) if (family, number) in rewards],
            "milestones": milestones,
        })
    return {"policy_version": rules.POLICY_VERSION, "currency": "mora", "max_active_weeks": rules.MAX_ACTIVE_WEEKS,
            "summary": {"families": len(families), "total_levels": sum(item["level"] for item in families),
                        "claimed_mora": sum(receipt["amount_mora"] for (family, _), receipt in rewards.items()
                                            if family in rules.FAMILIES)},
            "families": families,
            "message": "Прогресс учитывает только подтверждённые завершённые активности. Уровень 40 требует 156 активных недель."}
