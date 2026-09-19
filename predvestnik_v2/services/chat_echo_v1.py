"""Server-authoritative orchestration for the chat Echo event."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.chat_echo_v1 import (
    COOLDOWN_DAYS, DURATION_HOURS, FINALES, MIN_QUORUM, POLICY_VERSION,
    SYMBOLS, finale_for_counts, target_for_active_members,
)
from core.reconstruction import BALANCE_VERSION, GAME_VERSION
from infrastructure.repositories import chat_echo_v1 as repo
from infrastructure.repositories import gameplay_events as events


class EchoError(ValueError): pass
class EchoConflict(EchoError): pass
class EchoForbidden(EchoError): pass


def _public(event: dict, counts: dict[str, int], *, replay: bool = False) -> dict:
    total = sum(counts.values())
    return {
        "event_id": int(event["id"]), "status": event["status"],
        "target": int(event["target"]), "quorum": int(event["quorum"]),
        "total": total, "counts": {key: int(counts.get(key, 0)) for key in SYMBOLS},
        "ends_at": event["ends_at"], "finale_id": event.get("finale_id"),
        "finale_text": FINALES.get(str(event.get("finale_id"))),
        "economic_reward": None, "idempotent_replay": replay,
    }


async def candidates(db, chat_id: int) -> list[dict]:
    return await repo.eligible_candidates(db, chat_id)


async def start(db, *, chat_id: int, admin_id: int, eligible_user_ids: list[int]) -> dict:
    async with db.connection.transaction():
        await repo.lock_chat(db, chat_id)
        if not await repo.opt_in_enabled(db, chat_id):
            raise EchoForbidden("Администратор должен включить «Эхо в чате» в настройках.")
        await repo.expire_overdue(db, chat_id)
        await repo.recover_stale_creating(db, chat_id)
        if await repo.open_event(db, chat_id):
            raise EchoConflict("В этом чате уже идёт Эхо.")
        latest = await repo.latest_started_at(db, chat_id)
        now = datetime.now(timezone.utc)
        if latest and latest > now - timedelta(days=COOLDOWN_DAYS):
            raise EchoConflict("Новое Эхо можно запустить не чаще одного раза в 7 дней.")
        eligible = sorted({int(item) for item in eligible_user_ids if int(item) > 0})
        if len(eligible) < MIN_QUORUM:
            raise EchoConflict("Для Эха нужны минимум 3 подтверждённых участника.")
        active = len(eligible)
        target = min(active, target_for_active_members(active))
        event = await repo.create_event(
            db, chat_id=chat_id, policy_version=POLICY_VERSION, target=target,
            quorum=MIN_QUORUM, active_members_7d=active, started_by=admin_id,
            duration_hours=DURATION_HOURS, eligible_user_ids=eligible,
        )
        return _public(event, {})


async def overview(db, chat_id: int) -> dict | None:
    async with db.connection.transaction():
        await repo.lock_chat(db, chat_id)
        await repo.expire_overdue(db, chat_id)
        event = await repo.active_event(db, chat_id)
        return _public(event, await repo.counts(db, int(event["id"]))) if event else None


async def bind_message(db, event_id: int, chat_id: int, message_id: int) -> None:
    async with db.connection.transaction():
        await repo.lock_chat(db, chat_id)
        event = await repo.bind_message(db, event_id, chat_id, message_id, DURATION_HOURS)
        if not event:
            raise EchoConflict("Черновик Эха уже недоступен.")
        await events.record_event(
            db, user_id=int(event["started_by"]), event_name="chat_echo_started",
            game_version=GAME_VERSION, balance_version=BALANCE_VERSION,
            source="telegram_chat",
            payload={"event_id": int(event["id"]), "policy_version": POLICY_VERSION,
                     "target": int(event["target"]), "quorum": int(event["quorum"]),
                     "active_members_7d": int(event["active_members_7d"])},
            idempotency_key=f"chat-echo:{event['id']}:started",
        )


async def abort_unpublished(db, event_id: int, chat_id: int) -> None:
    async with db.connection.transaction():
        await repo.lock_chat(db, chat_id)
        await repo.cancel_unpublished(db, event_id, chat_id)


async def set_enabled(
    db, *, chat_id: int, actor_id: int, enabled: bool, operation_id: str
) -> dict | None:
    async with db.connection.transaction():
        await repo.lock_chat(db, chat_id)
        cancelled = await repo.set_enabled(db, chat_id, enabled)
        await events.record_event(
            db, user_id=actor_id, event_name="chat_echo_opt_changed",
            game_version=GAME_VERSION, balance_version=BALANCE_VERSION,
            source="telegram_chat", payload={"enabled": bool(enabled)},
            idempotency_key=f"chat-echo-opt:{operation_id}",
        )
        return cancelled


async def contribute(db, *, event_id: int, chat_id: int, user_id: int, symbol_id: str) -> dict:
    if symbol_id not in SYMBOLS:
        raise EchoError("Неизвестный знак.")
    async with db.connection.transaction():
        await repo.lock_chat(db, chat_id)
        event = await repo.lock_event(db, event_id, chat_id)
        if not event:
            raise EchoError("Эхо не найдено в этом чате.")
        now = datetime.now(timezone.utc)
        if event["status"] != "active" or event["ends_at"] <= now:
            if event["status"] == "active":
                await repo.expire_overdue(db, chat_id)
            raise EchoConflict("Это Эхо уже завершилось.")
        existing = await repo.existing_contribution(db, event_id, user_id)
        if existing:
            if existing != symbol_id:
                raise EchoConflict("Твой знак уже сохранён и не меняется.")
            return _public(event, await repo.counts(db, event_id), replay=True)
        if not await repo.in_snapshot(db, event_id, user_id):
            raise EchoForbidden("Ты не вошёл в подтверждённый состав этого Эха.")
        if not await repo.insert_contribution(db, event_id, user_id, symbol_id):
            raise EchoConflict("Твой вклад уже обрабатывается.")
        counts = await repo.counts(db, event_id)
        total = sum(counts.values())
        completed = total >= int(event["target"]) and total >= int(event["quorum"])
        if completed:
            finale_id = finale_for_counts(counts)
            event = await repo.complete(db, event_id, finale_id) or event
        await events.record_event(
            db, user_id=user_id, event_name="chat_echo_contributed",
            game_version=GAME_VERSION, balance_version=BALANCE_VERSION,
            source="telegram_chat",
            payload={"event_id": int(event_id), "policy_version": POLICY_VERSION,
                     "symbol_id": symbol_id, "total": total, "target": int(event["target"]),
                     "completed": completed},
            idempotency_key=f"chat-echo:{event_id}:user:{user_id}",
        )
        if completed:
            await events.record_event(
                db, user_id=user_id, event_name="chat_echo_completed",
                game_version=GAME_VERSION, balance_version=BALANCE_VERSION,
                source="telegram_chat",
                payload={"event_id": int(event_id), "policy_version": POLICY_VERSION,
                         "finale_id": event["finale_id"], "total": total,
                         "target": int(event["target"])},
                idempotency_key=f"chat-echo:{event_id}:completed",
            )
        return _public(event, counts)
