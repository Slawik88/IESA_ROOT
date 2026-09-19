#!/usr/bin/env python3
"""Real PostgreSQL rollback proof for all-currency family custody transfers."""
from __future__ import annotations

import argparse
import asyncio
from decimal import Decimal
from urllib.parse import urlparse

import asyncpg

from core.economy_contract import IdempotencyConflict, InsufficientBalance, InvalidEconomicMutation
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories.family_wallet_v1 import transfer_between_personal_and_family


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def scalar(db, sql: str, params: tuple) -> object:
    async with db.execute(sql, params) as cursor:
        return (await cursor.fetchone())[0]


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    transaction = connection.transaction()
    await transaction.start()
    try:
        db = PGAdapter(connection)
        actor, spouse, outsider = 940000000001, 940000000002, 940000000003
        await db.execute(
            "INSERT INTO users (user_tg_id, user_balance_zarniki) VALUES (?, ?), (?, ?), (?, ?)",
            (actor, 10, spouse, 0, outsider, 10),
        )
        async with db.execute(
            "INSERT INTO marriages (chat_id, user1_id, user1_name, user2_id, user2_name) "
            "VALUES (?, ?, 'transfer-a', ?, 'transfer-b') RETURNING id",
            (-940001, actor, spouse),
        ) as cursor:
            marriage_id = int((await cursor.fetchone())[0])
        await db.execute(
            "INSERT INTO marriage_members (user_id, marriage_id) VALUES (?, ?), (?, ?)",
            (actor, marriage_id, spouse, marriage_id),
        )

        deposited = await transfer_between_personal_and_family(
            db, actor_id=actor, currency="zarniki", amount=5, action="deposit", idempotency_key="deposit-1"
        )
        assert deposited.applied
        replay = await transfer_between_personal_and_family(
            db, actor_id=actor, currency="zarniki", amount=5, action="deposit", idempotency_key="deposit-1"
        )
        assert not replay.applied and replay.operation_id == deposited.operation_id
        assert str(await scalar(db, "SELECT user_balance_zarniki FROM users WHERE user_tg_id = ?", (actor,))) == "5.0"
        assert str(await scalar(db, "SELECT zarniki FROM family_wallet_balances WHERE marriage_id = ?", (marriage_id,))) == "5.000000"
        try:
            await transfer_between_personal_and_family(
                db, actor_id=actor, currency="zarniki", amount=4, action="deposit", idempotency_key="deposit-1"
            )
        except IdempotencyConflict:
            pass
        else:
            raise AssertionError("same idempotency key with another amount must fail")

        withdrawn = await transfer_between_personal_and_family(
            db, actor_id=actor, currency="zarniki", amount=3, action="withdrawal", idempotency_key="withdraw-1"
        )
        assert withdrawn.applied
        assert str(await scalar(db, "SELECT user_balance_zarniki FROM users WHERE user_tg_id = ?", (actor,))) == "8.0"
        assert str(await scalar(db, "SELECT zarniki FROM family_wallet_balances WHERE marriage_id = ?", (marriage_id,))) == "2.000000"
        total = Decimal(str(await scalar(db, "SELECT user_balance_zarniki FROM users WHERE user_tg_id = ?", (actor,)))) + Decimal(str(await scalar(db, "SELECT zarniki FROM family_wallet_balances WHERE marriage_id = ?", (marriage_id,))))
        assert total == Decimal("10.000000")

        await db.execute(
            "UPDATE users SET user_balance_mora = 10, user_balance_diamonds = 10, "
            "user_balance_dark_mora = 10 WHERE user_tg_id = ?",
            (actor,),
        )
        for currency, personal_column in (
            ("mora", "user_balance_mora"),
            ("diamonds", "user_balance_diamonds"),
            ("dark_mora", "user_balance_dark_mora"),
        ):
            await transfer_between_personal_and_family(
                db, actor_id=actor, currency=currency, amount=4, action="deposit",
                idempotency_key=f"{currency}-deposit",
            )
            await transfer_between_personal_and_family(
                db, actor_id=actor, currency=currency, amount=1, action="withdrawal",
                idempotency_key=f"{currency}-withdraw",
            )
            personal_balance = Decimal(str(await scalar(
                db, f"SELECT {personal_column} FROM users WHERE user_tg_id = ?", (actor,)
            )))
            family_balance = Decimal(str(await scalar(
                db, f"SELECT {currency} FROM family_wallet_balances WHERE marriage_id = ?", (marriage_id,)
            )))
            assert personal_balance + family_balance == Decimal("10.000000"), currency

        try:
            await transfer_between_personal_and_family(
                db, actor_id=outsider, currency="zarniki", amount=1, action="deposit", idempotency_key="outsider"
            )
        except InvalidEconomicMutation:
            pass
        else:
            raise AssertionError("non-member must not transfer")
        try:
            await transfer_between_personal_and_family(
                db, actor_id=actor, currency="zarniki", amount=Decimal("1.5"), action="deposit", idempotency_key="fraction"
            )
        except InvalidEconomicMutation:
            pass
        else:
            raise AssertionError("fractional Zarniki must fail")
        try:
            await transfer_between_personal_and_family(
                db, actor_id=actor, currency="zarniki", amount=99, action="deposit", idempotency_key="insufficient"
            )
        except InsufficientBalance:
            pass
        else:
            raise AssertionError("insufficient deposit must fail")
        assert str(await scalar(db, "SELECT zarniki FROM family_wallet_balances WHERE marriage_id = ?", (marriage_id,))) == "2.000000"
    finally:
        await transaction.rollback()
        await connection.close()


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True, type=local_dsn)
args = parser.parse_args()
asyncio.run(run(args.dsn))
print("family wallet transfer: real PostgreSQL rollback proof OK")
