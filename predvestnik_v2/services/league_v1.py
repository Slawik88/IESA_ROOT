"""The League: ranked ladders of Minesweeper and Rhythm levels with stars (demo before season 2, public from it).

Minesweeper is server-authoritative (a click is one short request; the board never reaches the phone).
Rhythm is played on the phone level by level and checked by the server in the pause after each level
(services.league_rhythm).  Progress resets every season.  In the demo season experience is only shown; in a
real season it goes to the season pass (services.league_pass), and also advances the same achievements as casual play.
"""
from __future__ import annotations

import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from core import league_mines, league_pass_demo, mines_logic
from core import league_pass as pass_rules
from core import league_v1 as rules
from infrastructure.repositories import league_v1 as repo
from infrastructure.repositories import public_profiles_v1 as public_profiles
from services import league_pass, league_rhythm, achievement_games
from services.vip import is_vip_active_batch


def _season(now: datetime | None = None) -> str:
    return rules.season_key(now or datetime.now(timezone.utc))


class LeagueError(Exception):
    pass


def _levels(rows: list[dict], game: str) -> list[dict]:
    return [r for r in rows if r["game"] == game]


def unlocked(rows: list[dict], game: str) -> int:
    cleared = [r["level"] for r in _levels(rows, game) if r["stars"] > 0]
    return min(rules.MAX_LEVEL, max(cleared, default=0) + 1)


async def overview(db, *, user_id: int) -> dict:
    await repo.ensure_tables(db)
    season = _season()
    rows = await repo.progress(db, user_id=user_id, season=season)
    # Resolve each player once even if they rank in both games.
    tops = {game: await repo.top(db, season=season, game=game) for game in rules.GAMES}
    names = await public_profiles.player_projection(
        db, user_ids=sorted({int(r["user_id"]) for top in tops.values() for r in top}),
    )
    vips = await is_vip_active_batch(db,list(names))
    pet_xp = await repo.pet_xp(db, user_id=user_id, season=season) if rules.is_demo(season) else 0
    games = {}
    for game in rules.GAMES:
        mine = _levels(rows, game)
        top = tops[game]
        games[game] = {
            "unlocked": unlocked(rows, game), "stars": sum(r["stars"] for r in mine),
            "levels": {str(r["level"]): {"stars": r["stars"], "attempts": r["attempts"]} for r in mine},
            "top": [{"place": i + 1, "name": names[int(r["user_id"])]["display_name"], "level": int(r["best_level"]),
                     "stars": int(r["stars"]), "me": int(r["user_id"]) == int(user_id),
                     "profile_ref":names[int(r["user_id"])]["profile_ref"],"is_vip":int(r["user_id"]) in vips} for i, r in enumerate(top)],
        }
    demo = rules.is_demo(season)
    return {"season": season, "demo": demo, "games": games, "xp_by_stars": rules.XP_BY_STARS,
            "pass": league_pass_demo.view(sum(r["xp"] for r in rows) + pet_xp) if demo else None,
            "pets": {"xp": dict(pass_rules.PET_XP), "cap": pass_rules.PET_DAILY_CAP}, "pet_xp": pet_xp}


async def _cancel_active(db, *, user_id: int, game: str) -> None:
    row = await repo.active_run(db, user_id=user_id, game=game)
    if row:
        await repo.update_run(db, run_id=row["run_id"], status="cancelled", state=repo.load(row["state_json"]),
                              revision=int(row["revision"]) + 1, finished=True)
        await repo.save_level(db, user_id=user_id, season=row["season"], game=game, level=int(row["level"]), stars=0, xp=0, best=None)


async def start(db, *, user_id: int, game: str, level: int) -> dict:
    if game not in rules.GAMES:
        raise LeagueError("Неизвестная игра.")
    try:
        level = rules.check_level(level)
    except rules.LeagueRuleError as exc:
        raise LeagueError(str(exc)) from exc
    await repo.ensure_tables(db)
    # Checked before the (possibly slow) board generation, and again under the lock below.
    season = _season()
    if level > unlocked(await repo.progress(db, user_id=user_id, season=season), game):
        raise LeagueError("Сначала пройди предыдущий уровень.")
    seed = secrets.token_bytes(32)
    await db.release_if_idle()   # board generation is pure CPU: no connection needed while it runs
    board = await asyncio.to_thread(_mines_board, seed, level) if game == "minesweeper" else {"gifts": rules.GIFT_POOL_NOW}
    run_id = str(uuid4())
    async with db.connection.transaction():
        await repo.lock_user(db, user_id=user_id)
        rows = await repo.progress(db, user_id=user_id, season=season)
        if level > unlocked(rows, game):
            raise LeagueError("Сначала пройди предыдущий уровень.")
        await _cancel_active(db, user_id=user_id, game=game)
        state = _mines_initial(board) if game == "minesweeper" else {}
        await repo.insert_run(db, run_id=run_id, user_id=user_id, season=season, game=game, level=level,
                              seed=seed, board=board, state=state)
        row = await repo.lock_run(db, run_id=run_id, user_id=user_id)
    if game == "rhythm":
        return {"run_id": run_id, "game": game, **league_rhythm.packet(season=season, level=level, seed=seed)}
    return _mines_view(row)


# ── Minesweeper ────────────────────────────────────────────────────────────────────────

def _mines_board(seed: bytes, level: int) -> dict:
    spec = rules.mines_level(level)
    board = league_mines.generate(seed, spec)
    return {"width": spec.width, "height": spec.height, "mines": sorted(board.mines), "start": board.start,
            "clicks": board.clicks, "tier": board.tier, "par_s": board.par_s}


def _mines_initial(board: dict) -> dict:
    mines = frozenset(board["mines"])
    adjacent = mines_logic.adjacency(board["width"], board["height"], mines)
    opened = mines_logic.flood(board["width"], board["height"], mines, adjacent, set(), board["start"])
    return {"revealed": sorted(opened), "flags": [], "wrong_flags": 0}


def _mines_view(row: dict, *, result: dict | None = None) -> dict:
    board, state = repo.load(row["board_json"]), repo.load(row["state_json"])
    mines = frozenset(board["mines"])
    adjacent = mines_logic.adjacency(board["width"], board["height"], mines)
    finished = row["status"] in ("won", "lost")
    end = row.get("finished_at") or row["server_now"]
    return {
        "run_id": row["run_id"], "game": "minesweeper", "level": int(row["level"]), "status": row["status"],
        "revision": int(row["revision"]), "width": board["width"], "height": board["height"],
        "mine_count": len(mines), "tier": board["tier"], "par_s": board["par_s"],
        "cells": {str(c): adjacent[c] for c in state["revealed"]}, "flags": state["flags"],
        "mines": sorted(mines) if row["status"] == "lost" else [],
        "elapsed_ms": max(0, int((end - row["started_at"]).total_seconds() * 1000)),
        "wrong_flags": state["wrong_flags"] if finished else None, "result": result,
    }


async def mines_act(db, *, user_id: int, run_id: str, revision: int, kind: str, cell: int) -> dict:
    if kind not in ("open", "flag"):
        raise LeagueError("Неизвестное действие.")
    async with db.connection.transaction():
        row = await repo.lock_run(db, run_id=run_id, user_id=user_id)
        if not row or row["game"] != "minesweeper":
            raise LeagueError("Партия не найдена.")
        if row["status"] != "active":
            return _mines_view(row, result=repo.load(row["result_json"]) or None)
        if int(revision) != int(row["revision"]):
            return {**_mines_view(row), "stale": True}
        board, state = repo.load(row["board_json"]), repo.load(row["state_json"])
        if not 0 <= int(cell) < board["width"] * board["height"]:
            raise LeagueError("Такой клетки нет.")
        status = _mines_apply(board, state, kind, int(cell))
        row.update(status=status, state_json=state, revision=int(row["revision"]) + 1)
        result = await _mines_finish(db, row, board, state) if status != "active" else None
        await repo.update_run(db, run_id=run_id, status=status, state=state, revision=row["revision"],
                              result=result, finished=status != "active")
        if status != "active":
            row["finished_at"] = row["server_now"]
        return _mines_view(row, result=result)


def _mines_apply(board: dict, state: dict, kind: str, cell: int) -> str:
    mines, revealed, flags = frozenset(board["mines"]), set(state["revealed"]), set(state["flags"])
    if cell in revealed:
        return "active"
    if kind == "flag":
        if cell in flags:
            flags.discard(cell)
        else:
            flags.add(cell)
            state["wrong_flags"] += cell not in mines
        state["flags"] = sorted(flags)
        return "active"
    if cell in flags:
        return "active"
    if cell in mines:
        return "lost"
    adjacent = mines_logic.adjacency(board["width"], board["height"], mines)
    revealed |= mines_logic.flood(board["width"], board["height"], mines, adjacent, revealed, cell)
    state["revealed"] = sorted(revealed)
    return "won" if len(revealed) == board["width"] * board["height"] - len(mines) else "active"


async def _mines_finish(db, row: dict, board: dict, state: dict) -> dict:
    elapsed = max(0, int((row["server_now"] - row["started_at"]).total_seconds() * 1000))
    stars = rules.mines_stars(won=row["status"] == "won", wrong_flags=state["wrong_flags"],
                              elapsed_ms=elapsed, par_s=board["par_s"])
    return await _record(db, row, stars, {"elapsed_ms": elapsed, "wrong_flags": state["wrong_flags"]})


# ── Rhythm ─────────────────────────────────────────────────────────────────────────────

async def rhythm_finish(db, *, user_id: int, run_id: str, actions: list) -> dict:
    async with db.connection.transaction():
        row = await repo.lock_run(db, run_id=run_id, user_id=user_id)
        if not row or row["game"] != "rhythm":
            raise LeagueError("Забег не найден.")
        if row["status"] != "active":
            saved = repo.load(row["result_json"])
            if saved:
                return {**saved, "replay": True}
            raise LeagueError("Этот уровень уже закрыт. Начни его заново.")
        try:
            # A level keeps the gift pool it was started with (older rows carry no marker: the pool before the series gifts).
            pool = int(repo.load(row["board_json"]).get("gifts", rules.GIFT_POOL_BEFORE_SERIES))
            outcome = league_rhythm.replay(season=row["season"], level=int(row["level"]), seed=bytes(row["seed"]),
                                           actions=list(actions), pool_number=pool)
        except rules.LeagueRuleError as exc:
            raise LeagueError(str(exc)) from exc
        lived = row["server_now"] - row["started_at"]
        if lived + timedelta(milliseconds=league_rhythm.CLOCK_TOLERANCE_MS) < timedelta(milliseconds=league_rhythm.played_ms(outcome)):
            raise LeagueError("Журнал пришёл быстрее, чем уровень можно сыграть. Сыграй уровень заново.")
        marks = league_rhythm.review_marks(outcome)
        row["status"] = "finished"
        detail = {k: v for k, v in outcome.items() if not k.startswith("_")}
        result = await _record(db, row, outcome["stars"], {**detail, "review": marks})
        await repo.update_run(db, run_id=run_id, status="finished", state={}, revision=int(row["revision"]) + 1,
                              result=result, finished=True)
        return result


# ── Progress ───────────────────────────────────────────────────────────────────────────

async def _record(db, row: dict, stars: int, detail: dict) -> dict:
    """Count the attempt, keep the best stars, add only the experience of the improvement (to the pass in a real season)."""
    user_id, game, level = int(row["user_id"]), row["game"], int(row["level"])
    await repo.lock_user(db, user_id=user_id)
    before = await repo.level_row(db, user_id=user_id, season=row["season"], game=game, level=level)
    old = int(before["stars"]) if before else 0
    xp = rules.xp_gain(old, stars)
    await repo.save_level(db, user_id=user_id, season=row["season"], game=game, level=level, stars=stars, xp=xp,
                          best=detail if stars > old else None)
    if xp and not rules.is_demo(row["season"]):
        await league_pass.add_xp(db, user_id=user_id, source="league", event_id=f"{row['season']}:{game}:{level}:{stars}",
                                 xp=xp, casual=False, at=row["server_now"], season=int(row["season"].lstrip("s")))
    await achievement_games.record_ranked(db,row)
    return {"run_id": row["run_id"], "game": game, "level": level, "stars": stars, "best_stars": max(old, stars),
            "xp": xp, "next_unlocked": stars > 0, "detail": detail}


async def reset(db, *, user_id: int) -> None:
    await repo.ensure_tables(db)
    async with db.connection.transaction():
        await repo.lock_user(db, user_id=user_id)
        season = _season()
        if not rules.is_demo(season):
            raise LeagueError("Сбросить можно только прогресс демо.")
        await repo.reset(db, user_id=user_id, season=season)
