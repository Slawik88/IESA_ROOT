"""Server-authoritative Minesweeper flow. No rewards or economy writers."""
from __future__ import annotations

from datetime import datetime, timezone
import secrets
from uuid import uuid4

from asyncpg.exceptions import UniqueViolationError

from core import minesweeper_v2 as rules
from infrastructure.repositories import minesweeper_v2 as repo
from services import achievements_v1 as achievements
from services import quests_v1 as quests


class MinesweeperError(Exception):
    pass


class MinesweeperConflict(MinesweeperError):
    pass


async def _record_completed_quest(db, *, user_id: int, run_id: str, difficulty: str, won: bool) -> None:
    """One terminal run advances clear quests and long-horizon achievements."""
    event_id = f"minesweeper:{run_id}"
    sources = await quests.available_sources(db, user_id=user_id)
    for metric in ("game_completed", "minesweeper_completed"):
        await quests.record_metric(db, user_id=user_id, metric=metric, event_id=event_id,
                                   vip_active=False, sources=sources)
    if won:
        for metric in ("minesweeper_win", f"minesweeper_{difficulty}_win"):
            await quests.record_metric(db, user_id=user_id, metric=metric, event_id=event_id,
                                       vip_active=False, sources=sources)
    await achievements.record_terminal(
        db, user_id=user_id, metric="minesweeper_completed", source_event_id=run_id,
        source_snapshot={"run_id": run_id},
    )


def _spec(row):
    return rules.difficulty(str(row["difficulty"]))


def _layout(row):
    first = row["first_cell"]
    if first is None:
        return None
    return rules.board(bytes(row["seed"]), _spec(row), int(first))


def _public(row: dict, *, revealed: set[int] | None = None, flags: set[int] | None = None,
            changed: tuple[int, ...] | None = None, mines: tuple[int, ...] = (), now: datetime | None = None) -> dict:
    spec = _spec(row)
    revealed = set(repo.load(row["revealed_json"]) if revealed is None else revealed)
    flags = set(repo.load(row["flags_json"]) if flags is None else flags)
    layout = _layout(row)
    if not mines and row["status"] == "lost" and layout:
        # GET /runs/{id} is the recovery authority after an action response is
        # lost. A terminal loss must reveal the same layout as the POST.
        mines = tuple(layout["mines"])
    cells = []
    if changed is None:
        changed = tuple(revealed)
    if layout:
        cells = [{"cell": cell, "adjacent": layout["adjacent"][cell]} for cell in changed]
    started_at = row.get("started_at")
    elapsed_ms = row.get("elapsed_ms")
    if elapsed_ms is None and started_at and now:
        elapsed_ms = max(0, int((now - started_at).total_seconds() * 1000))
    return {
        "run_id": row["run_id"], "difficulty": spec.id, "label": spec.label, "size": spec.size, "mine_count": spec.mines,
        "ruleset_version": row["ruleset_version"], "status": row["status"], "revision": int(row["revision"]),
        "revealed": sorted(revealed), "flags": sorted(flags), "changed": cells,
        "mines": sorted(mines), "opened_actions": int(row["opened_actions"]), "flags_left": spec.mines - len(flags),
        "elapsed_ms": elapsed_ms,
    }


async def start_run(db, *, user_id: int, difficulty: str) -> dict:
    try:
        spec = rules.difficulty(difficulty)
    except rules.MinesweeperRuleError as exc:
        raise MinesweeperError(str(exc)) from exc
    await repo.ensure_tables(db)
    run_id = str(uuid4())
    async with db.connection.transaction():
        async with db.execute("SELECT run_id FROM minesweeper_v2_runs WHERE user_id=? AND status IN ('awaiting_first_open','active') FOR UPDATE", (int(user_id),)) as cursor:
            existing = await cursor.fetchone()
        if existing:
            await db.execute("UPDATE minesweeper_v2_runs SET status='cancelled',finished_at=CLOCK_TIMESTAMP(),revision=revision+1 WHERE run_id=?", (str(existing["run_id"]),))
        try:
            await db.execute("INSERT INTO minesweeper_v2_runs(run_id,user_id,difficulty,ruleset_version,seed,status) VALUES (?,?,?,?,?,'awaiting_first_open')", (run_id, int(user_id), spec.id, rules.RULESET_VERSION, secrets.token_bytes(32)))
        except UniqueViolationError as exc:
            raise MinesweeperConflict("another Minesweeper run is still closing") from exc
        row = {"run_id": run_id, "difficulty": spec.id, "ruleset_version": rules.RULESET_VERSION, "seed": b"", "first_cell": None,
               "revealed_json": [], "flags_json": [], "status": "awaiting_first_open", "revision": 0, "opened_actions": 0,
               "started_at": None, "elapsed_ms": None}
        return _public(row)


async def current_run(db, *, user_id: int, run_id: str) -> dict:
    async with db.connection.transaction():
        row = await repo.lock_owned_run(db, run_id=run_id, user_id=user_id)
        if not row:
            raise MinesweeperConflict("Minesweeper run was not found")
        return _public(row, now=row["server_now"])


async def act(db, *, user_id: int, run_id: str, action_id: str, expected_revision: int, kind: str, cell: int) -> dict:
    if not action_id or len(action_id) > 96 or kind not in ("open", "toggle_flag") or not isinstance(cell, int) or cell < 0 or not isinstance(expected_revision, int) or expected_revision < 0:
        raise MinesweeperError("invalid Minesweeper action")
    request = {"expected_revision": expected_revision, "kind": kind, "cell": cell}
    async with db.connection.transaction():
        row = await repo.lock_owned_run(db, run_id=run_id, user_id=user_id)
        if not row:
            raise MinesweeperConflict("Minesweeper run was not found")
        recorded = await repo.action(db, run_id=run_id, action_id=action_id)
        if recorded:
            if repo.load(recorded["request_json"]) != request:
                raise MinesweeperConflict("action id was already used with another action")
            result = repo.load(recorded["result_json"]); result["idempotent_replay"] = True
            return result
        if int(row["revision"]) != expected_revision:
            raise MinesweeperConflict("Minesweeper board changed; refresh it before the next action")
        if row["status"] not in ("awaiting_first_open", "active"):
            raise MinesweeperConflict("Minesweeper run is already over")
        now = row["server_now"]
        if row["first_cell"] is None:
            if kind != "open":
                raise MinesweeperConflict("first Minesweeper action must open a cell")
            try:
                rules.board(bytes(row["seed"]), _spec(row), cell)
            except rules.MinesweeperRuleError as exc:
                raise MinesweeperError(str(exc)) from exc
            row["first_cell"], row["started_at"], row["status"] = cell, now, "active"
        layout = _layout(row)
        revealed, flags = set(repo.load(row["revealed_json"])), set(repo.load(row["flags_json"]))
        try:
            next_revealed, next_flags, status, changed = rules.apply_action(spec=_spec(row), layout=layout, revealed=revealed, flags=flags, kind=kind, cell=cell)
        except rules.MinesweeperRuleError as exc:
            raise MinesweeperError(str(exc)) from exc
        opened_actions = int(row["opened_actions"]) + (1 if kind == "open" and cell not in revealed and cell not in flags else 0)
        row["revision"] = int(row["revision"]) + 1
        row["status"] = status
        row["revealed_json"], row["flags_json"], row["opened_actions"] = sorted(next_revealed), sorted(next_flags), opened_actions
        mines: tuple[int, ...] = ()
        if status in ("won", "lost"):
            row["finished_at"] = now
            row["elapsed_ms"] = max(0, int((now - row["started_at"]).total_seconds() * 1000))
            if status == "lost":
                mines = tuple(layout["mines"])
        await repo.update_run(db, run_id=run_id, first_cell=row["first_cell"], revealed=next_revealed, flags=next_flags, status=status,
                              revision=row["revision"], opened_actions=opened_actions, started_at=row.get("started_at"),
                              finished_at=row.get("finished_at"), elapsed_ms=row.get("elapsed_ms"))
        if status == "won":
            await repo.upsert_leaderboard(db, run_id=run_id, user_id=user_id, difficulty=row["difficulty"], ruleset_version=row["ruleset_version"], elapsed_ms=row["elapsed_ms"], opened_actions=opened_actions)
        result = _public(row, revealed=next_revealed, flags=next_flags, changed=changed, mines=mines, now=now)
        if status in ("won", "lost"):
            await _record_completed_quest(
                db, user_id=user_id, run_id=run_id, difficulty=str(row["difficulty"]), won=status == "won",
            )
        await repo.save_action(db, run_id=run_id, action_id=action_id, request=request, result=result)
        return result


async def rankings(db, *, user_id: int, difficulty: str) -> dict:
    try:
        rules.difficulty(difficulty)
    except rules.MinesweeperRuleError as exc:
        raise MinesweeperError(str(exc)) from exc
    await repo.ensure_tables(db)
    return await repo.leaderboard(db, user_id=user_id, difficulty=difficulty, ruleset_version=rules.RULESET_VERSION)
