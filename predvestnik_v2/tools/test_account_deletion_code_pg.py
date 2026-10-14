#!/usr/bin/env python3
"""Real PostgreSQL proof (audit A11): the deletion confirmation code has a TTL,
an attempt limit, a resend interval and is consumed once. Everything runs in one
transaction that is rolled back. Only a loopback DSN is accepted."""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys
from urllib.parse import urlparse

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.constants import ACCOUNT_DELETE_CODE_ATTEMPTS, ACCOUNT_DELETE_PHRASE
from infrastructure.pg_adapter import PGAdapter
from services import account_deletion as acc

sent: list[str] = []


async def fake_tg(method: str, **kwargs) -> dict:
    text = kwargs.get("text", "")
    if "<code>" in text and "Код подтверждения" in text:
        sent.append(text.split("<code>")[1].split("</code>")[0])
    return {"ok": True}


async def scalar(db, sql: str, params: tuple) -> object:
    async with db.execute(sql, params) as cursor:
        return (await cursor.fetchone())[0]


def wrong(code: str) -> str:
    return f"{(int(code) + 1) % 1_000_000:06d}"


async def run(dsn: str) -> None:
    acc._tg = fake_tg
    connection = await asyncpg.connect(dsn)
    tx = connection.transaction()
    await tx.start()
    try:
        db = PGAdapter(connection)
        a, b, c, d = 960000000001, 960000000002, 960000000003, 960000000004
        await db.execute("INSERT INTO users (user_tg_id) VALUES (?), (?), (?), (?)", (a, b, c, d))

        # Attempt limit: the correct code is useless after the budget is spent.
        assert (await acc.request_deletion(db, a))[0]
        code = sent[-1]
        for i in range(ACCOUNT_DELETE_CODE_ATTEMPTS):
            ok, msg = await acc.confirm_deletion(db, a, wrong(code), ACCOUNT_DELETE_PHRASE)
            assert not ok, msg
        ok, msg = await acc.confirm_deletion(db, a, code, ACCOUNT_DELETE_PHRASE)
        assert not ok and "истёк или исчерпан" in msg, msg
        # Resend interval, then a new code with a fresh budget works.
        ok, msg = await acc.request_deletion(db, a)
        assert not ok and "минут" in msg, msg
        await db.execute("UPDATE account_deletions SET requested_at = NOW() - INTERVAL '11 minutes' WHERE user_id = ?", (a,))
        assert (await acc.request_deletion(db, a))[0]
        assert sent[-1] != "" and (await acc.confirm_deletion(db, a, sent[-1], ACCOUNT_DELETE_PHRASE))[0]
        assert await scalar(db, "SELECT status FROM account_deletions WHERE user_id = ?", (a,)) == "cooling"
        # Consumed once: replaying the same code does nothing.
        ok, _ = await acc.confirm_deletion(db, a, sent[-1], ACCOUNT_DELETE_PHRASE)
        assert not ok

        # TTL: a correct but expired code is rejected even by direct call.
        assert (await acc.request_deletion(db, b))[0]
        await db.execute("UPDATE account_deletions SET requested_at = NOW() - INTERVAL '16 minutes' WHERE user_id = ?", (b,))
        ok, msg = await acc.confirm_deletion(db, b, sent[-1], ACCOUNT_DELETE_PHRASE)
        assert not ok and "истёк" in msg, msg
        assert await scalar(db, "SELECT status FROM account_deletions WHERE user_id = ?", (b,)) == "confirming"

        # Inactivity warning rows carry no code: an empty code must not confirm them.
        await db.execute(
            "INSERT INTO account_deletions (user_id, source, status, warned_at) VALUES (?, 'inactivity', 'confirming', NOW())",
            (c,),
        )
        ok, _ = await acc.confirm_deletion(db, c, "", ACCOUNT_DELETE_PHRASE)
        assert not ok
        assert await scalar(db, "SELECT status FROM account_deletions WHERE user_id = ?", (c,)) == "confirming"

        # Wrong phrase does not spend an attempt; codes come from a CSPRNG-backed range.
        assert (await acc.request_deletion(db, d))[0]
        ok, _ = await acc.confirm_deletion(db, d, sent[-1], "нет")
        assert not ok
        assert await scalar(db, "SELECT confirm_attempts FROM account_deletions WHERE user_id = ?", (d,)) == 0
        assert all(len(x) == 6 and x.isdigit() for x in sent)

        # Inactivity warning: an expired self request (warned_at NULL) must not block it,
        # a fresh one (d, just requested) must. Both users are long inactive.
        await db.execute(
            "INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, last_message_at) "
            "VALUES (?, -1, NOW() - INTERVAL '400 days'), (?, -1, NOW() - INTERVAL '400 days')",
            (b, d),
        )
        await acc.daily_tick(db)
        assert await scalar(db, "SELECT source FROM account_deletions WHERE user_id = ? AND warned_at IS NOT NULL", (b,)) == "inactivity"
        assert await scalar(db, "SELECT warned_at IS NULL AND source = 'self' FROM account_deletions WHERE user_id = ?", (d,))
    finally:
        await tx.rollback()
        await connection.close()


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True)
args = parser.parse_args()
if urlparse(args.dsn).hostname not in {"127.0.0.1", "localhost", "::1"}:
    raise SystemExit("only a loopback PostgreSQL DSN is allowed")
asyncio.run(run(args.dsn))
print("account deletion confirmation code: real PostgreSQL proof OK")
