#!/usr/bin/env python3
"""PostgreSQL proof that profile results use only current, trust-aware games."""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys
from urllib.parse import urlparse

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import FastAPI.routers.profile as profile_router
from FastAPI.routers.profile import _ensure_profile_tables, _game_results, _sanctions
from infrastructure.pg_adapter import PGAdapter


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    db = PGAdapter(connection)
    schema = f"profile_contract_{os.getpid()}"
    fresh = connection.transaction()
    await fresh.start()
    try:
        await connection.execute(f'CREATE SCHEMA "{schema}"')
        await connection.execute(f'SET LOCAL search_path TO "{schema}", public')
        profile_router._PROFILE_TABLES_READY = False
        await _ensure_profile_tables(db)
        for table in ("rhythm_v2_runs", "minesweeper_v2_runs", "mafia_v1_matches", "pet_v1_state", "achievement_v1_progress"):
            assert await connection.fetchval("SELECT to_regclass($1)", table), table
    finally:
        await fresh.rollback()
    profile_router._PROFILE_TABLES_READY = False
    await _ensure_profile_tables(db)
    assert profile_router._PROFILE_TABLES_READY
    transaction = connection.transaction()
    await transaction.start()
    try:
        user_id = 979101
        for suffix, score, integrity in (
            ("clear", 123, "clear"),
            ("quarantined", 999_999, "quarantined"),
            ("legacy", 888_888, "legacy_unverified"),
            ("review", 777_777, "review_required"),
            ("offline", 666_666, "offline_exposed"),
            ("pending-finished", 555_555, "pending"),
        ):
            await db.execute(
                "INSERT INTO rhythm_v2_runs(run_id,user_id,mode,ruleset_version,seed,offers_json,status,health,score,integrity_status) "
                "VALUES (?,?,?,?,?,?::jsonb,'finished',0,?,?)",
                (f"profile-proof-{suffix}", user_id, "normal", "profile-proof-v1", b"seed", "[]", score, integrity),
            )
        await db.execute(
            "INSERT INTO rhythm_v2_runs(run_id,user_id,mode,ruleset_version,seed,offers_json,status,health,score,integrity_status) "
            "VALUES ('profile-proof-active',?,'normal','profile-proof-v1',?,'[]'::jsonb,'active',1,444444,'pending'),"
            "('profile-proof-cancelled',?,'normal','profile-proof-v1',?,'[]'::jsonb,'cancelled',1,333333,'clear')",
            (user_id, b"seed", user_id, b"seed"),
        )

        await db.execute(
            "INSERT INTO minesweeper_v2_runs(run_id,user_id,difficulty,ruleset_version,seed,status,opened_actions,elapsed_ms) "
            "VALUES (?,?,?,?,?,'won',7,5000), (?,?,?,?,?,'lost',3,NULL)",
            ("profile-proof-mine-win", user_id, "easy", "profile-proof-v1", b"mine",
             "profile-proof-mine-loss", user_id, "normal", "profile-proof-v1", b"mine"),
        )
        async with db.execute(
            "INSERT INTO mafia_v1_matches(chat_id,initiator_id,ruleset_version,max_players,enabled_roles_json,vote_mode,phase,winner) "
            "VALUES (?,?,?,4,'[]'::jsonb,'open','finished','town') RETURNING id",
            (-979101, user_id, "profile-proof-v1"),
        ) as cursor:
            match_id = (await cursor.fetchone())[0]
        await db.execute(
            "INSERT INTO mafia_v1_players(match_id,user_id,join_order,display_name,role) VALUES (?,?,1,'Profile proof','citizen')",
            (match_id, user_id),
        )

        personal = await _game_results(db, user_id, include_private=True)
        public = await _game_results(db, user_id, include_private=False)

        assert personal["rhythm"] == {
            "verified_runs": 1,
            "best_verified_score": 123,
            "personal_unranked_runs": 5,
        }
        assert public["rhythm"] == {"verified_runs": 1, "best_verified_score": 123}
        assert 999_999 not in public["rhythm"].values(), "quarantined score must not become public proof"
        assert personal["minesweeper"] == {
            "played": 2,
            "wins": 1,
            "best_ms": {"easy": 5000, "normal": None, "hard": None},
        }
        assert personal["mafia"] == {"played": 1, "wins": 1}
        assert public["minesweeper"] == personal["minesweeper"]
        assert public["mafia"] == personal["mafia"]
        await db.execute(
            "INSERT INTO global_sanctions(target_type,target_id,sanction_type,reason,issued_by) "
            "VALUES ('user',?,'ban','PRIVATE MODERATOR NOTE',42)",
            (user_id,),
        )
        owner_sanctions = await _sanctions(db, user_id, include_private=True)
        public_sanctions = await _sanctions(db, user_id, include_private=False)
        assert owner_sanctions["active_global"]["reason"] == "PRIVATE MODERATOR NOTE"
        assert "PRIVATE MODERATOR NOTE" not in str(public_sanctions)
        assert all("reason" not in item for item in public_sanctions["history"])
    finally:
        await transaction.rollback()
        await connection.close()


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True, type=local_dsn)
args = parser.parse_args()
asyncio.run(run(args.dsn))
print("Profile current projection: trusted public results and private quarantine count OK")
