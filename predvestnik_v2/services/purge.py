"""Shared durable purge workflow. Telegram adapters supply permission/effect callbacks.

    warn is database-only and atomic; external effects reserve a durable target
    before delivery. A network error or crash never permits blind resend.
"""
import asyncio

from infrastructure.repositories import purge_sessions as repo

VERDICTS = frozenset({"forgive", "warn", "mute", "kick", "ban"})
DELIVERY_TIMEOUT = 40
RECONCILE_TIMEOUT = 8


class PurgeConflict(ValueError):
    pass


class PurgeUnavailable(PurgeConflict):
    """Temporary permission lookup failure, rather than revoked access."""


class DeliveryRejected(Exception):
    """Transport guarantees that no operation was applied (e.g. Telegram 4xx)."""


async def begin(db, **kwargs) -> int:
    return (await begin_with_receipt(db, **kwargs))["session_id"]


async def existing_start(db, *, chat_id: int, actor: int, action_id: str | None,
                         norm: int, date_from: str, date_to: str) -> dict | None:
    if action_id is not None:
        receipt = await repo.start_receipt(db, chat_id, actor, action_id)
        if receipt:
            if (int(receipt["norm"]), str(receipt["date_from"]), str(receipt["date_to"])) != (norm, date_from, date_to):
                raise PurgeConflict("Этот идентификатор уже использован с другим периодом или нормой.")
            return {"session_id": int(receipt["id"]), "created": False, "active": receipt["status"] == "active"}
    if await repo.get_active(db, chat_id):
        raise PurgeConflict("Чистка уже идёт. Продолжите текущую сессию.")
    return None


async def begin_with_receipt(db, *, chat_id: int, actor: int, norm: int, date_from: str, date_to: str,
                             destination: int, targets: list[dict], action_id: str | None = None) -> dict:
    if action_id is not None and (not action_id.strip() or len(action_id) > 96):
        raise PurgeConflict("Неверный идентификатор запуска.")
    await repo.ensure_operations(db)
    async with db.connection.transaction():
        await repo.lock_chat(db, chat_id)
        receipt = await existing_start(db, chat_id=chat_id, actor=actor, action_id=action_id,
                                       norm=norm, date_from=date_from, date_to=date_to)
        if receipt:
            return receipt
        sid = await repo.create(db, chat_id, actor, norm, date_from, date_to, destination, action_id)
        await repo.insert_targets(db,sid,targets)
        await db.execute("INSERT INTO chat_settings(chat_id,is_purging) VALUES (?,TRUE) "
                         "ON CONFLICT(chat_id) DO UPDATE SET is_purging=TRUE", (chat_id,))
        await db.execute("INSERT INTO moderation_logs(chat_id,user_id,admin_id,action,reason) VALUES (?,0,?,'purge_start',?)",
                         (chat_id, actor, f"норма {norm}"))
        return {"session_id": sid, "created": True, "active": True}


async def decide(db, *, session_id: int, user_id: int, actor: int, action: str, action_id: str,
                 authorize, execute) -> dict:
    if action not in VERDICTS or not action_id or len(action_id) > 96:
        raise PurgeConflict("Неверное решение или идентификатор операции.")
    await repo.ensure_operations(db)
    session = await repo.get_by_id(db, session_id)
    if not session:
        raise PurgeConflict("Чистка не найдена.")
    cid = int(session["chat_id"])
    await authorize(cid, user_id, action)
    async with db.connection.transaction():
        await repo.lock_chat(db, cid)
        current = await repo.get_by_id(db, session_id)
        if current["status"] != "active":
            raise PurgeConflict("Эта чистка уже завершена.")
        target = await repo.get_target(db, session_id, user_id)
        if not target:
            raise PurgeConflict("Участника нет в этой чистке.")
        if target["verdict"]:
            return {"ok": True, "verdict": target["verdict"], "replayed": True}
        if target["decision_state"] in {"sending", "unknown"}:
            raise PurgeConflict("Действие выполняется или его исход неизвестен. Сначала проверьте результат; повторная санкция заблокирована.")
        attempt = await repo.reserve(db, session_id, user_id, action, actor, action_id)
        if action in {"forgive", "warn"}:
            if action == "warn":
                await execute(cid, user_id, action)
            await repo.set_verdict(db, session_id, user_id, action, actor)
            await repo.operation_state(db, session_id, user_id, "done")
            return {"ok": True, "verdict": action, "replayed": False}
    # The durable sending state survives loss of process/connection after Telegram accepts.
    try:
        async with db.connection.transaction():
            # A live delivery owns this target until it returns or is cancelled.
            # Human reconciliation must never race an ongoing Telegram request.
            await repo.lock_delivery(db, session_id, user_id)
            target = await repo.get_target(db, session_id, user_id)
            if (target["decision_state"] != "sending" or target["decision_key"] != action_id
                    or target["decision_started_at"] != attempt):
                raise PurgeConflict("Результат уже сверен. Обновите досье перед новым решением.")
            await asyncio.wait_for(execute(cid, user_id, action), timeout=DELIVERY_TIMEOUT)
            await repo.lock_chat(db, cid)
            await repo.set_verdict(db, session_id, user_id, action, actor)
            await repo.operation_state(db, session_id, user_id, "done")
    except DeliveryRejected:
        await repo.delivery_failed(db, session_id, user_id, action_id, attempt, "failed", "Telegram отклонил действие. Проверьте права и повторите.")
        raise PurgeConflict("Telegram отклонил действие; решение не принято.")
    except PurgeConflict:
        raise
    except Exception:
        await repo.delivery_failed(db, session_id, user_id, action_id, attempt, "unknown", "Ответ не получен. Проверьте участника и журнал Telegram до повторной попытки.")
        raise PurgeConflict("Ответ Telegram не получен. Исход требует проверки, автоматического повтора не будет.") from None
    return {"ok": True, "verdict": action, "replayed": False}


async def complete(db, *, chat_id: int, actor: int, expected_session: int | None = None) -> dict:
    await repo.ensure_operations(db)
    async with db.connection.transaction():
        await repo.lock_chat(db, chat_id)
        session = await repo.get_active(db, chat_id)
        if not session:
            raise PurgeConflict("Чистка сейчас не идёт.")
        if expected_session is not None and int(session["id"]) != expected_session:
            raise PurgeConflict("Открыта уже другая чистка. Обновите страницу.")
        async with db.execute("SELECT COUNT(*) FROM purge_targets WHERE session_id=? AND decision_state IN ('sending','unknown')",
                              (session["id"],)) as cursor:
            if int((await cursor.fetchone())[0]):
                raise PurgeConflict("Дождитесь исполнения решений. При неизвестном исходе сначала сверяйте операцию.")
        await repo.finish(db, int(session["id"]))
        # Independent manual chat closure must survive purge completion.
        await db.execute("UPDATE chat_settings SET is_purging=FALSE WHERE chat_id=?", (chat_id,))
        await db.execute("INSERT INTO moderation_logs(chat_id,user_id,admin_id,action) VALUES (?,0,?,'purge_finish')", (chat_id, actor))
        return {"session_id": int(session["id"]), "counts": await repo.counts(db, int(session["id"]))}


async def view(db, *, chat_id: int, page: int = 0, mode: str = "pending") -> dict:
    isolation = None if db.connection.is_in_transaction() else "repeatable_read"
    async with db.connection.transaction(isolation=isolation):
        return await _view_snapshot(db,chat_id=chat_id,page=page,mode=mode)


async def _view_snapshot(db, *, chat_id: int, page: int, mode: str) -> dict:
    if mode not in {"all", "pending", "decided"} or not 0 <= page <= 10000:
        raise PurgeConflict("Неверный фильтр страницы.")
    session = await repo.get_active(db, chat_id)
    if not session:
        completed = await repo.latest_finished(db, chat_id)
        if completed:
            completed["counts"] = await repo.counts(db, int(completed["id"]))
        return {"active": False, "items": [], "page": 0, "has_more": False, "completed": completed}
    counts = await repo.counts(db, int(session["id"]))
    total = {"pending": counts["total"] - counts["decided"], "decided": counts["decided"], "all": counts["total"]}[mode]
    page = min(page, max(0, (total - 1) // 25))
    rows = await repo.target_page(db, int(session["id"]), page, mode)
    return {"active": True, "session": {k: session[k] for k in ("id", "norm", "date_from", "date_to", "initiator_id")},
            "counts": counts, "page": page, "mode": mode, "has_more": len(rows) > 25,
            "items": [{k: row.get(k) for k in ("user_id", "username", "msg_count", "days_in_chat", "warns", "required_norm", "member_tag", "verdict", "verdict_by", "verdict_by_name", "verdict_by_username", "verdict_at", "reconcile_ready", "decision_state", "decision_action", "decision_error")}
                      for row in rows[:25]]}


async def reconcile(db, *, session_id: int, user_id: int, actor: int, applied: bool, reason: str, authorize, materialize) -> dict:
    """Explicit human verification; never retries a possibly delivered action."""
    if len(reason.strip()) < 12 or len(reason) > 300:
        raise PurgeConflict("Опишите проверку результата: 12–300 символов.")
    await repo.ensure_operations(db)
    session = await repo.get_by_id(db, session_id)
    if not session:
        raise PurgeConflict("Чистка не найдена.")
    await authorize(int(session["chat_id"]), None, None)
    async with db.connection.transaction():
        await repo.lock_chat(db, int(session["chat_id"]))
        if not await repo.lock_delivery(db, session_id, user_id, wait=False):
            raise PurgeConflict("Telegram ещё обрабатывает действие. Дождитесь ответа перед сверкой.")
        current = await repo.get_by_id(db, session_id)
        if current["status"] != "active":
            raise PurgeConflict("Эта чистка уже завершена.")
        row = await repo.get_target(db, session_id, user_id)
        if not row or row["verdict"] or row["decision_state"] not in {"sending", "unknown"}:
            raise PurgeConflict("Эта операция не требует сверки.")
        async with db.execute("SELECT decision_started_at < CLOCK_TIMESTAMP()-INTERVAL '2 minutes' FROM purge_targets "
                              "WHERE session_id=? AND user_id=?", (session_id, user_id)) as cursor:
            expired = bool((await cursor.fetchone())[0])
        if row["decision_state"] == "sending" and not expired:
            raise PurgeConflict("Действие ещё может исполняться. Подождите две минуты перед сверкой.")
        try:
            await asyncio.wait_for(materialize(row, applied), timeout=RECONCILE_TIMEOUT)
        except TimeoutError:
            raise PurgeUnavailable("Проверка результата в Telegram затянулась. Досье сохранено; повторите сверку позже.") from None
        if applied:
            await repo.set_verdict(db, session_id, user_id, row["decision_action"], int(row["decision_actor"]))
        await repo.operation_state(db, session_id, user_id, "done" if applied else "failed", None if applied else "Модератор подтвердил отсутствие действия.")
        await db.execute("INSERT INTO moderation_logs(chat_id,user_id,admin_id,action,reason) VALUES (?,?,?,'purge_reconcile',?)",
                         (session["chat_id"], user_id, actor, f"{'applied' if applied else 'not_applied'}: {reason.strip()}"))
        return {"ok": True, "applied": applied}
