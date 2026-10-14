#!/usr/bin/env python3
"""ECO-04 PR-E: Dark Mora and Echo Shards are retired from player surfaces.

Balances stay in the database untouched; reads, the ledger and account
deletion keep working with the columns; the family wallet API keeps its shape;
no live code path can mint either currency.
"""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys
from urllib.parse import urlparse

import asyncpg

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import HTTPException

from bot.chat import family
from FastAPI.routers import dark_mora as dark_mora_router
from FastAPI.routers.marriage import my_marriage
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories.economy_ledger import apply_balance_change
from services import account_deletion, ai_assistant, promocodes
from services.profile_render import build_profile_text, get_template_var_help


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def scalar(db, sql: str, params: tuple) -> object:
    async with db.execute(sql, params) as cursor:
        return (await cursor.fetchone())[0]


def assert_no_live_minters() -> None:
    """Static guard: the retired Dark Mora credit helper and the Echo Shard
    duplicate writer have no production caller (balance writers as a whole are
    guarded by tools/audit_economy_mutations.py)."""
    for path in ROOT.rglob("*.py"):
        if {"tools", "scripts"} & set(path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        if "add_dark_mora(" in text and "async def add_dark_mora(" not in text:
            raise AssertionError(f"Dark Mora credit helper gained a caller: {path.relative_to(ROOT)}")
        if "apply_duplicate_progression(" in text and "async def apply_duplicate_progression(" not in text:
            raise AssertionError(f"Echo Shard duplicate writer gained a caller: {path.relative_to(ROOT)}")


async def run(dsn: str) -> None:
    assert_no_live_minters()
    for endpoint in (dark_mora_router.ritual,):
        try:
            await endpoint(db=None, user={"id": 1})
        except HTTPException as error:
            assert error.status_code == 410
        else:
            raise AssertionError("retired Dark Mora endpoint must answer 410")

    connection = await asyncpg.connect(dsn)
    transaction = connection.transaction()
    await transaction.start()
    try:
        db = PGAdapter(connection)
        actor, spouse, leaver = 950000000001, 950000000002, 950000000003
        await db.execute(
            "INSERT INTO users (user_tg_id, user_tg_username, user_balance_mora, user_balance_dark_mora) "
            "VALUES (?, 'legacy_a', 100, 50), (?, 'legacy_b', 0, 0), (?, 'legacy_c', 10, 7)",
            (actor, spouse, leaver),
        )
        async with db.execute(
            "INSERT INTO marriages (chat_id, user1_id, user1_name, user2_id, user2_name, family_balance_dark_mora) "
            "VALUES (?, ?, 'legacy-a', ?, 'legacy-b', 30) RETURNING id",
            (-950001, actor, spouse),
        ) as cursor:
            marriage_id = int((await cursor.fetchone())[0])
        await db.execute(
            "INSERT INTO marriage_members (user_id, marriage_id) VALUES (?, ?), (?, ?)",
            (actor, marriage_id, spouse, marriage_id),
        )

        # Family wallet: the read with Dark Mora inside does not fail, the API
        # shape is unchanged, the bot card no longer shows it.
        balances = await family.wallet_balances(db, marriage_id)
        assert "dark_mora" in balances
        api = await my_marriage(db=db, user={"id": actor})
        assert api["married"] and "family_balance_dark_mora" in api, api
        fam = await family.family_of(db, actor)
        assert fam is not None and fam.marriage_id == marriage_id
        text = await family.card(db, fam)
        assert "Тёмн" not in text and "🌑" not in text, text

        # Player-facing texts: profile card, Theme Lab help, AI balance tool.
        profile = await build_profile_text(db, actor, -950001)
        assert "Тёмная" not in profile, profile
        assert all(v["name"] != "темная_мора" for v in get_template_var_help("standard"))
        tool = await ai_assistant._tool_get_balance(db, actor, -950001)
        assert "dark_mora" not in tool, tool

        # Ledger still settles against the column (spend of an old balance).
        await apply_balance_change(
            db, actor, {"mora": -10, "dark_mora": -5}, reason_code="legacy_test_spend",
            idempotency_key="legacy-pr-e-spend", source_type="test",
        )
        assert float(await scalar(db, "SELECT user_balance_dark_mora FROM users WHERE user_tg_id = ?", (actor,))) == 45.0
        assert float(await scalar(db, "SELECT user_balance_mora FROM users WHERE user_tg_id = ?", (actor,))) == 90.0

        # Promocodes carrying Dark Mora are refused (no new accrual).
        await db.execute(
            "INSERT INTO promocodes (code, description, reward_mora, reward_diamonds, reward_dark_mora) "
            "VALUES ('LEGACYPRE', 'legacy', 0, 0, 5)",
        )
        try:
            await promocodes.activate_promocode(db, actor, "LEGACYPRE", -950001)
        except promocodes.PromoError:
            pass
        else:
            raise AssertionError("Dark Mora promocode must be refused")
        assert float(await scalar(db, "SELECT user_balance_dark_mora FROM users WHERE user_tg_id = ?", (actor,))) == 45.0

        # Account deletion still zeroes the legacy column.
        await account_deletion._finalize(db, leaver)
        assert float(await scalar(db, "SELECT user_balance_dark_mora FROM users WHERE user_tg_id = ?", (leaver,))) == 0.0
    finally:
        await transaction.rollback()
        await connection.close()


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True, type=local_dsn)
args = parser.parse_args()
asyncio.run(run(args.dsn))
print("OK: Dark Mora and Echo Shards are hidden, balances kept, ledger/deletion/family reads work, no minting")
