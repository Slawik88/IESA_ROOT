"""Shared durable purge workflow. Telegram adapters supply permission/effect callbacks.

    warn is database-only and atomic; external effects reserve a durable target
    before delivery. A network error or crash never permits blind resend.
"""
from infrastructure.repositories import purge_sessions as repo

VERDICTS = frozenset({"forgive", "warn", "mute", "kick", "ban"})


class PurgeConflict(ValueError):
    pass


class DeliveryRejected(Exception):
    """Transport guarantees that no operation was applied (e.g. Telegram 4xx)."""


async def begin(db, **kwargs) -> int:
    return (await begin_with_receipt(db, **kwargs))["session_id"]


async def begin_with_receipt(db, *, chat_id: int, actor: int, norm: int, date_from: str, date_to: str,
                             destination: int, targets: list[dict], action_id: str | None = None) -> dict:
    if action_id is not None and (not action_id.strip() or len(action_id) > 96):
        raise PurgeConflict("Неверный идентификатор запуска.")
    await repo.ensure_operations(db)
    async with db.connection.transaction():
        await repo.lock_chat(db, chat_id)
        if action_id is not None:
            receipt = await repo.start_receipt(db, chat_id, actor, action_id)
            if receipt:
                if (int(receipt["norm"]), str(receipt["date_from"]), str(receipt["date_to"])) != (norm, date_from, date_to):
                    raise PurgeConflict("Этот идентификатор уже использован с другим периодом или нормой.")
                return {"session_id": int(receipt["id"]), "created": False, "active": receipt["status"] == "active"}
        if await repo.get_active(db, chat_id):
            raise PurgeConflict("Чистка уже идёт. Продолжите текущую сессию.")
        sid = await repo.create(db, chat_id, actor, norm, date_from, date_to, destination, action_id)
        for t in targets:
            await db.execute("INSERT INTO purge_targets(session_id,user_id,username,msg_count,days_in_chat,warns,required_norm,member_tag) "
                             "VALUES (?,?,?,?,?,?,?,?)", (sid, t["user_id"], t.get("username"), t["count"],
                              t["days_in_chat"], t["warns"], t["required"], t.get("tag")))
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
        await repo.reserve(db, session_id, user_id, action, actor, action_id)
        if action in {"forgive", "warn"}:
            if action == "warn":
                await execute(cid, user_id, action)
            await repo.set_verdict(db, session_id, user_id, action, actor)
            await repo.operation_state(db, session_id, user_id, "done")
            return {"ok": True, "verdict": action, "replayed": False}
    # The durable sending state survives loss of process/connection after Telegram accepts.
    try:
        await execute(cid, user_id, action)
    except DeliveryRejected:
        await repo.operation_state(db, session_id, user_id, "failed", "Telegram отклонил действие. Проверьте права и повторите.")
        raise PurgeConflict("Telegram отклонил действие; решение не принято.")
    except Exception:
        await repo.operation_state(db, session_id, user_id, "unknown", "Ответ не получен. Проверьте участника и журнал Telegram до повторной попытки.")
        raise PurgeConflict("Ответ Telegram не получен. Исход требует проверки, автоматического повтора не будет.") from None
    async with db.connection.transaction():
        await repo.lock_chat(db, cid)
        await repo.set_verdict(db, session_id, user_id, action, actor)
        await repo.operation_state(db, session_id, user_id, "done")
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
    if mode not in {"all", "pending", "decided"} or not 0 <= page <= 10000:
        raise PurgeConflict("Неверный фильтр страницы.")
    await repo.ensure_operations(db)
    session = await repo.get_active(db, chat_id)
    if not session:
        return {"active": False, "items": [], "page": 0, "has_more": False}
    rows = await repo.target_page(db, int(session["id"]), page, mode)
    return {"active": True, "session": {k: session[k] for k in ("id", "norm", "date_from", "date_to", "initiator_id")},
            "counts": await repo.counts(db, int(session["id"])), "page": page, "mode": mode, "has_more": len(rows) > 25,
            "items": [{k: row.get(k) for k in ("user_id", "username", "msg_count", "days_in_chat", "warns", "required_norm", "member_tag", "verdict", "decision_state", "decision_action", "decision_error")}
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
        row = await repo.get_target(db, session_id, user_id)
        if not row or row["verdict"] or row["decision_state"] not in {"sending", "unknown"}:
            raise PurgeConflict("Эта операция не требует сверки.")
        async with db.execute("SELECT decision_started_at < CLOCK_TIMESTAMP()-INTERVAL '2 minutes' FROM purge_targets "
                              "WHERE session_id=? AND user_id=?", (session_id, user_id)) as cursor:
            expired = bool((await cursor.fetchone())[0])
        if row["decision_state"] == "sending" and not expired:
            raise PurgeConflict("Действие ещё может исполняться. Подождите две минуты перед сверкой.")
        await materialize(row, applied)
        if applied:
            await repo.set_verdict(db, session_id, user_id, row["decision_action"], int(row["decision_actor"]))
        await repo.operation_state(db, session_id, user_id, "done" if applied else "failed", None if applied else "Модератор подтвердил отсутствие действия.")
        await db.execute("INSERT INTO moderation_logs(chat_id,user_id,admin_id,action,reason) VALUES (?,?,?,'purge_reconcile',?)",
                         (session["chat_id"], user_id, actor, f"{'applied' if applied else 'not_applied'}: {reason.strip()}"))
        return {"ok": True, "applied": applied}
