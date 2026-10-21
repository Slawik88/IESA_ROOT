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
from infrastructure.repositories import minesweeper_v2 as mines_repo
from services import leaderboards_v1
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
        # Stable ordinary board: random first-open auto-wins are tested below.
        await db.execute("UPDATE minesweeper_v2_runs SET seed=? WHERE run_id=?", (bytes(range(32)), first["run_id"]))
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
        resumed = await game.start_run(db, user_id=976001, difficulty="hard", resume_existing=True)
        assert resumed["run_id"] == first["run_id"] and resumed["difficulty"] == "easy"
        assert resumed["revision"] == state["revision"] and resumed["revealed"] == state["revealed"]
        assert {c["cell"] for c in resumed["changed"]} == set(state["revealed"]), "resume sends every known number"
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
        await db.execute("UPDATE minesweeper_v2_runs SET seed=? WHERE run_id=?", (bytes(range(32)), winner["run_id"]))
        wins_before = await mines_repo.win_position(db, user_id=976001)
        state = await game.act(db, user_id=976001, run_id=winner["run_id"], action_id="start-win", expected_revision=0, kind="open", cell=14)
        layout = await layout_for(db, winner["run_id"])
        counter = 0
        while state["status"] == "active":
            revealed = set(state["revealed"])
            safe = next(cell for cell in range(36) if cell not in layout["mines"] and cell not in revealed)
            counter += 1
            state = await game.act(db, user_id=976001, run_id=winner["run_id"], action_id=f"safe-{counter}", expected_revision=state["revision"], kind="open", cell=safe)
        assert state["status"] == "won" and state["elapsed_ms"] is not None
        wins_after = await mines_repo.win_position(db, user_id=976001)
        assert (wins_after["wins"] if wins_after else 0) == (wins_before["wins"] if wins_before else 0) + 1
        game_top = await leaderboards_v1.game_top(db, user_id=976001, game="minesweeper")
        assert game_top["personal"] and game_top["personal"]["count"] == wins_after["wins"], "the game top counts wins"
        assert game_top["items"] and all({"name", "ref", "count", "is_me"} <= set(row) for row in game_top["items"])
        async with db.execute("SELECT metric FROM quest_v1_metric_receipts WHERE user_id=? AND event_id=? ORDER BY metric", (976001, f"minesweeper:{winner['run_id']}")) as cursor:
            assert [row[0] for row in await cursor.fetchall()] == [
                'game_completed', 'minesweeper_completed', 'minesweeper_easy_win', 'minesweeper_win',
            ]
        ranking = await game.rankings(db, user_id=976001, difficulty="easy")
        assert ranking["personal"] and ranking["personal"]["best_elapsed_ms"] == state["elapsed_ms"]
        assert ranking["top"] and all({"look", "mark", "is_vip"} <= set(row["player"]) and "user_id" not in row["player"] for row in ranking["top"]) and all("is_me" in row for row in ranking["top"]), "game boards carry the same skin and own-row fields as the message tops"

        # Automatic wins remain valid and idempotent, but cannot displace a
        # player's real best time. Filter before DISTINCT ON, including history.
        for user in (976001, 976002):
            auto = await game.start_run(db, user_id=user, difficulty="easy")
            await db.execute("UPDATE minesweeper_v2_runs SET seed=? WHERE run_id=?", ((536).to_bytes(32, "big"), auto["run_id"]))
            args = dict(user_id=user, run_id=auto["run_id"], action_id="auto", expected_revision=0, kind="open", cell=14)
            result = await game.act(db, **args)
            assert result["status"] == "won" and result["elapsed_ms"] == 0 and not result["speed_ranked"]
            assert not (await game.current_run(db, user_id=user, run_id=auto["run_id"]))["speed_ranked"]
            assert (await game.act(db, **args))["idempotent_replay"]
            async with db.execute("SELECT COUNT(*) FROM quest_v1_metric_receipts WHERE user_id=? AND metric='minesweeper_win' AND event_id=?", (user, f"minesweeper:{auto['run_id']}")) as cursor:
                assert (await cursor.fetchone())[0] == 1
        ranking = await game.rankings(db, user_id=976001, difficulty="easy")
        assert ranking["personal"]["best_elapsed_ms"] == state["elapsed_ms"]
        assert (await game.rankings(db, user_id=976002, difficulty="easy"))["personal"] is None
        # Subsecond multi-open wins are legitimate; do not round or clamp them.
        await db.execute("UPDATE minesweeper_v2_runs SET elapsed_ms=250,opened_actions=2 WHERE run_id=?", (auto["run_id"],))
        assert (await game.rankings(db, user_id=976002, difficulty="easy"))["personal"]["best_elapsed_ms"] == 250

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
        # Explicit New Game cancels and freezes the old timer; resume never does.
        previous = await game.start_run(db, user_id=976009, difficulty="normal")
        active = await game.act(db, user_id=976009, run_id=previous["run_id"], action_id="open-before-reload", expected_revision=0, kind="open", cell=0)
        closed = next(c for c in range(81) if c not in active["revealed"])
        flagged = await game.act(db, user_id=976009, run_id=previous["run_id"], action_id="flag-before-reload", expected_revision=active["revision"], kind="toggle_flag", cell=closed)
        saved = await game.start_run(db, user_id=976009, difficulty="easy", resume_existing=True)
        assert saved["run_id"] == previous["run_id"] and saved["flags"] == flagged["flags"]
        await game.start_run(db, user_id=976009, difficulty="hard")
        cancelled1 = await game.current_run(db, user_id=976009, run_id=previous["run_id"])
        await connection.execute("SELECT pg_sleep(0.03)")
        cancelled2 = await game.current_run(db, user_id=976009, run_id=previous["run_id"])
        assert cancelled1["status"] == "cancelled" and cancelled1["elapsed_ms"] == cancelled2["elapsed_ms"]
    finally:
        await transaction.rollback(); await connection.close()

    # Concurrent fresh browser loads must share one active board.
    from uuid import uuid4
    user = 995000000 + uuid4().int % 1000000
    clients = [await asyncpg.connect(dsn) for _ in range(3)]
    try:
        results = await asyncio.wait_for(asyncio.gather(*(game.start_run(PGAdapter(c), user_id=user, difficulty="normal", resume_existing=True) for c in clients)), 10)
        assert len({r["run_id"] for r in results}) == 1
        assert await clients[0].fetchval("SELECT COUNT(*) FROM minesweeper_v2_runs WHERE user_id=$1 AND status IN ('active','awaiting_first_open')", user) == 1
    finally:
        await asyncio.gather(*(c.close() for c in clients))


parser = argparse.ArgumentParser(); parser.add_argument("--dsn", required=True, type=local_dsn)
args = parser.parse_args(); asyncio.run(run(args.dsn))
print("minesweeper_v2: PostgreSQL ownership, replay, terminal state and ranking OK")
