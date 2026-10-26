"""Real connection races and cancellation; Telegram is replaced by controlled effects."""
import argparse
import asyncio
import pathlib
import sys
from unittest.mock import patch
from urllib.parse import urlparse
from uuid import uuid4

import asyncpg

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import purge_sessions as repo
from services import purge


async def refused(awaitable, text):
    try:
        await awaitable
    except purge.PurgeConflict as error:
        assert text in str(error), error
    else:
        raise AssertionError("Expected refusal")


async def run(dsn):
    connections = [await asyncpg.connect(dsn) for _ in range(2)]
    for connection in connections:
        await connection.execute("SET search_path TO predvestnik,public")
    a, b = [PGAdapter(c) for c in connections]
    cid = -int(uuid4().int % 1000000000 + 8000000000)
    task = None
    async def authorize(*args):
        return None
    async def materialize(*args):
        raise AssertionError("An ongoing delivery cannot be reconciled")
    async def effect(*args):
        return None
    try:
        start = dict(chat_id=cid, actor=101, norm=10, date_from="2026-10-01", date_to="2026-10-07",
                     destination=cid, action_id="start", targets=[dict(user_id=uid, count=0, days_in_chat=7, warns=0, required=10) for uid in (201,202,203)])
        sid = await purge.begin(a, **start)
        assert (await purge.existing_start(b, **{k:start[k] for k in ("chat_id","actor","norm","date_from","date_to","action_id")}))["session_id"] == sid
        entered, release = asyncio.Event(), asyncio.Event()
        async def delayed(*args):
            entered.set()
            await release.wait()
        decision = dict(session_id=sid, user_id=201, actor=101, action="ban", action_id="delivery", authorize=authorize)
        task = asyncio.create_task(purge.decide(a, **decision, execute=delayed))
        await asyncio.wait_for(entered.wait(), 2)
        await b.execute("UPDATE purge_targets SET decision_started_at=CLOCK_TIMESTAMP()-INTERVAL '3 minutes' WHERE session_id=? AND user_id=201", (sid,))
        await asyncio.wait_for(refused(purge.reconcile(b, session_id=sid, user_id=201, actor=303, applied=False,
            reason="Проверен журнал Telegram, действия нет", authorize=authorize, materialize=materialize), "ещё обрабатывает"), 2)
        await refused(purge.decide(b, **decision, execute=effect), "исход неизвестен")
        # One slow participant cannot stop another moderator's work or fresh reads.
        await asyncio.wait_for(purge.decide(b, **{**decision,"user_id":202,"action":"warn"}, execute=effect), 2)
        assert (await asyncio.wait_for(purge.view(b, chat_id=cid), 2))["counts"]["decided"] == 1
        await refused(purge.complete(b, chat_id=cid, actor=101, expected_session=sid), "Дождитесь")
        release.set()
        assert (await asyncio.wait_for(task, 2))["verdict"] == "ban"
        # Timeout rolls back adapter SQL, while the durable reservation stays unknown.
        async def timeout_effect(*args):
            await a.execute("INSERT INTO moderation_logs(chat_id,user_id,admin_id,action) VALUES (?,203,101,'test_timeout')", (cid,))
            await asyncio.sleep(10)
        third = {**decision,"user_id":203,"action_id":"same-retry-key"}
        with patch.object(purge, "DELIVERY_TIMEOUT", .02):
            await refused(purge.decide(a, **third, execute=timeout_effect), "Исход требует проверки")
        assert (await repo.get_target(b, sid, 203))["decision_state"] == "unknown"
        assert not await connections[1].fetchval("SELECT COUNT(*) FROM moderation_logs WHERE chat_id=$1 AND action='test_timeout'", cid)
        async def verified(*args):
            return None
        old = await repo.get_target(b, sid, 203)
        async def stalled_check(*args):
            await b.execute("INSERT INTO moderation_logs(chat_id,user_id,admin_id,action) VALUES (?,203,303,'test_check_timeout')", (cid,))
            await asyncio.sleep(10)
        with patch.object(purge, "RECONCILE_TIMEOUT", .02):
            await refused(purge.reconcile(b, session_id=sid, user_id=203, actor=303, applied=False,
                reason="Проверен журнал Telegram, действия нет", authorize=authorize, materialize=stalled_check), "затянулась")
        assert (await repo.get_target(b, sid, 203))["decision_state"] == "unknown"
        assert not await connections[1].fetchval("SELECT COUNT(*) FROM moderation_logs WHERE chat_id=$1 AND action='test_check_timeout'", cid)
        await purge.reconcile(b, session_id=sid, user_id=203, actor=303, applied=False,
                              reason="Проверен журнал Telegram, действия нет", authorize=authorize, materialize=verified)
        # Same retry key, new reservation: a delayed failure belongs to the old generation.
        generation = await repo.reserve(b, sid, 203, "mute", 303, "same-retry-key")
        await repo.delivery_failed(b, sid, 203, "same-retry-key", old["decision_started_at"], "failed", "late failure")
        row = await repo.get_target(b, sid, 203)
        assert row["decision_state"] == "sending" and row["decision_started_at"] == generation
        await b.execute("UPDATE purge_targets SET decision_state='failed' WHERE session_id=? AND user_id=203", (sid,))
        await purge.complete(b, chat_id=cid, actor=101, expected_session=sid)
        summary = await purge.view(a, chat_id=cid)
        assert not summary["active"] and summary["completed"]["id"] == sid
        assert summary["completed"]["counts"]["decided"] == 2
        await refused(purge.reconcile(b, session_id=sid, user_id=203, actor=303, applied=False,
            reason="Проверен журнал Telegram, действия нет", authorize=authorize, materialize=verified), "завершена")
        print("PASS: late delivery exclusion, independent moderators, bounded timeout, SQL rollback, generation-safe retry, closed session")
    finally:
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await b.execute("DELETE FROM purge_targets WHERE session_id IN (SELECT id FROM purge_sessions WHERE chat_id=?)", (cid,))
        await b.execute("DELETE FROM purge_sessions WHERE chat_id=?", (cid,))
        await b.execute("DELETE FROM moderation_logs WHERE chat_id=?", (cid,))
        await b.execute("DELETE FROM chat_settings WHERE chat_id=?", (cid,))
        for connection in connections:
            await connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    args = parser.parse_args()
    if urlparse(args.dsn).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise SystemExit("loopback database required")
    asyncio.run(run(args.dsn))
