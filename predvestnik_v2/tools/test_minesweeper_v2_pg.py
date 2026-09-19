#!/usr/bin/env python3
"""Real PostgreSQL proof for server-owned Minesweeper transitions/ranking."""
from __future__ import annotations

import argparse
import asyncio
from urllib.parse import urlparse

import asyncpg

from core import minesweeper_v2 as rules
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import achievements_v1 as achievements_repo
from infrastructure.repositories import economy_ledger
from services import minesweeper_v2 as game


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def layout_for(db, run_id: str):
    async with db.execute("SELECT seed,difficulty,first_cell FROM minesweeper_v2_runs WHERE run_id=?", (run_id,)) as cursor:
        row = await cursor.fetchone()
    assert row and row["first_cell"] is not None
    return rules.board(bytes(row["seed"]), rules.difficulty(row["difficulty"]), int(row["first_cell"]))


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    db = PGAdapter(connection)
    await achievements_repo.ensure_tables(db)
    await economy_ledger.ensure_tables(db)
    transaction = connection.transaction(); await transaction.start()
    try:
        first = await game.start_run(db, user_id=976001, difficulty="easy")
        assert first["status"] == "awaiting_first_open" and first["size"] == 6
        try:
            await game.act(db, user_id=976001, run_id=first["run_id"], action_id="first-flag", expected_revision=0, kind="toggle_flag", cell=0)
        except game.MinesweeperConflict:
            pass
        else:
            raise AssertionError("first action must be an open")
        state = await game.act(db, user_id=976001, run_id=first["run_id"], action_id="first-open", expected_revision=0, kind="open", cell=14)
        assert state["status"] == "active" and 14 in state["revealed"] and not state["mines"]
        replay = await game.act(db, user_id=976001, run_id=first["run_id"], action_id="first-open", expected_revision=0, kind="open", cell=14)
        assert replay["idempotent_replay"] and replay["revision"] == state["revision"]
        try:
            await game.act(db, user_id=976001, run_id=first["run_id"], action_id="first-open", expected_revision=0, kind="open", cell=15)
        except game.MinesweeperConflict:
            pass
        else:
            raise AssertionError("action id must bind the exact request")
        try:
            await game.current_run(db, user_id=976002, run_id=first["run_id"])
        except game.MinesweeperConflict:
            pass
        else:
            raise AssertionError("foreign user must not read the run")
        layout = await layout_for(db, first["run_id"])
        mine = next(iter(layout["mines"]))
        lost = await game.act(db, user_id=976001, run_id=first["run_id"], action_id="mine", expected_revision=state["revision"], kind="open", cell=mine)
        assert lost["status"] == "lost" and mine in lost["mines"]
        recovered_loss = await game.current_run(db, user_id=976001, run_id=first["run_id"])
        assert recovered_loss["status"] == "lost"
        assert recovered_loss["mines"] == lost["mines"], "GET recovery must reveal the terminal mine layout"
        async with db.execute("SELECT COUNT(*) FROM quest_v1_metric_receipts WHERE user_id=? AND metric='minesweeper_completed' AND event_id=?", (976001, f"minesweeper:{first['run_id']}")) as cursor:
            assert (await cursor.fetchone())[0] == 1
        async with db.execute("SELECT metric FROM quest_v1_metric_receipts WHERE user_id=? AND event_id=? ORDER BY metric", (976001, f"minesweeper:{first['run_id']}")) as cursor:
            assert [row[0] for row in await cursor.fetchall()] == ['game_completed', 'minesweeper_completed']
        try:
            await game.act(db, user_id=976001, run_id=first["run_id"], action_id="after-loss", expected_revision=lost["revision"], kind="open", cell=1)
        except game.MinesweeperConflict:
            pass
        else:
            raise AssertionError("terminal loss must be immutable")

        winner = await game.start_run(db, user_id=976001, difficulty="easy")
        state = await game.act(db, user_id=976001, run_id=winner["run_id"], action_id="start-win", expected_revision=0, kind="open", cell=14)
        layout = await layout_for(db, winner["run_id"])
        counter = 0
        while state["status"] == "active":
            revealed = set(state["revealed"])
            safe = next(cell for cell in range(36) if cell not in layout["mines"] and cell not in revealed)
            counter += 1
            state = await game.act(db, user_id=976001, run_id=winner["run_id"], action_id=f"safe-{counter}", expected_revision=state["revision"], kind="open", cell=safe)
        assert state["status"] == "won" and state["elapsed_ms"] is not None
        async with db.execute("SELECT metric FROM quest_v1_metric_receipts WHERE user_id=? AND event_id=? ORDER BY metric", (976001, f"minesweeper:{winner['run_id']}")) as cursor:
            assert [row[0] for row in await cursor.fetchall()] == [
                'game_completed', 'minesweeper_completed', 'minesweeper_easy_win', 'minesweeper_win',
            ]
        ranking = await game.rankings(db, user_id=976001, difficulty="easy")
        assert ranking["personal"] and ranking["personal"]["best_elapsed_ms"] == state["elapsed_ms"]

        hard = await game.start_run(db, user_id=976003, difficulty="hard")
        hard_state = await game.act(db, user_id=976003, run_id=hard["run_id"], action_id="hard-start", expected_revision=0, kind="open", cell=40)
        hard_layout = await layout_for(db, hard["run_id"])
        counter = 0
        while hard_state["status"] == "active":
            revealed = set(hard_state["revealed"])
            safe = next(cell for cell in range(81) if cell not in hard_layout["mines"] and cell not in revealed)
            counter += 1
            hard_state = await game.act(db, user_id=976003, run_id=hard["run_id"], action_id=f"hard-safe-{counter}", expected_revision=hard_state["revision"], kind="open", cell=safe)
        assert hard_state["status"] == "won"
        async with db.execute("SELECT metric FROM quest_v1_metric_receipts WHERE user_id=? AND event_id=? ORDER BY metric", (976003, f"minesweeper:{hard['run_id']}")) as cursor:
            assert [row[0] for row in await cursor.fetchall()] == [
                'game_completed', 'minesweeper_completed', 'minesweeper_hard_win', 'minesweeper_win',
            ]
    finally:
        await transaction.rollback(); await connection.close()


parser = argparse.ArgumentParser(); parser.add_argument("--dsn", required=True, type=local_dsn)
args = parser.parse_args(); asyncio.run(run(args.dsn))
print("minesweeper_v2: PostgreSQL ownership, replay, terminal state and ranking OK")
