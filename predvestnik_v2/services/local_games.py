"""Resilient Mini App runs: immutable packets and atomic journal settlement.

The owner explicitly accepts client timing and exposed layouts in exchange for
network-independent play. Ownership, replay and exactly-once rewards still hold.
"""
from __future__ import annotations

import copy
from dataclasses import asdict
from datetime import timedelta
from uuid import UUID

from core import rhythm_v2 as rhythm_rules, minesweeper_v2 as mine_rules, rhythm_analysis
from infrastructure.repositories import rhythm_v2 as rr, minesweeper_v2 as mr
from services import rhythm_v2 as rhythm, minesweeper_v2 as mine

PACKET_ID = "local:packet:v1"
RESULT_ID = "local:result:v1"
PROTOCOL = "resilient-local-v1"
MAX_ACTIONS = 100_000


def _parts(game):
    if game == "rhythm":
        return rr, rhythm.RhythmConflict, rr.get_action, rr.insert_action
    return mr, mine.MinesweeperConflict, mr.action, mr.save_action


async def packet(db, *, game: str, user_id: int, run_id: str) -> dict:
    repo, conflict, get, save = _parts(game)
    async with db.connection.transaction():
        row = await repo.lock_owned_run(db, run_id=run_id, user_id=user_id)
        if not row:
            raise conflict("Партия не найдена.")
        saved = await get(db, run_id=run_id, action_id=PACKET_ID)
        if saved:
            return repo.load(saved["result_json"])
        if row["status"] not in {"active", "awaiting_first_open"}:
            raise conflict("Партия уже завершена.")
        result = {"protocol": PROTOCOL, "game": game, "run_id": run_id,
                  "owner": str(user_id), "seed": bytes(row["seed"]).hex()}
        if game == "rhythm":
            state = rhythm._state(row)
            # Migration from an interrupted live run preserves hearts. Never
            # apply wall-clock expiry while taking over a disconnected game.
            state["signal_opened_at"] = state["finished_at"] = None
            await rr.update_run(db, run_id=run_id, state=state)
            await rr.set_integrity(db, run_id=run_id, status="offline_exposed",
                                   reason=PROTOCOL, evidence={"protocol": PROTOCOL})
            await db.execute("UPDATE rhythm_v2_runs SET transport_lease=NULL,transport_lease_expires_at=NULL WHERE run_id=?", (run_id,))
            result.update(state=state, catalog=[asdict(p) for p in rhythm_rules.PERKS],
                          ruleset_version=row["ruleset_version"], legacy=row["ruleset_version"] != rhythm_rules.RULESET_VERSION)
        else:
            state = mine._public(row, now=row["server_now"])
            spec = mine._spec(row)
            first = row["first_cell"]
            layouts = {str(c): sorted(mine_rules.board(bytes(row["seed"]), spec, c, ruleset_version=row["ruleset_version"])["mines"])
                       for c in (range(spec.size * spec.size) if first is None else [int(first)])}
            result.update(state=state, first_cell=first, layouts=layouts)
        await save(db, run_id=run_id, action_id=PACKET_ID, request={"protocol": PROTOCOL}, result=result)
        return result


def replay_rhythm(packet: dict, actions: list[dict]) -> dict:
    state = copy.deepcopy(packet["state"])
    seed = bytes.fromhex(packet["seed"])
    state["analysis"] = rhythm_analysis.fresh()
    for action in actions:
        if state["status"] != "active":
            raise ValueError("Действие после завершения забега.")
        if rhythm._draft_pending(state):
            offered = rhythm_rules.perk_offers(seed, len(state["selected"]) + 1,
                      health=state["health"], perks=state["perks"], legacy=packet["legacy"])
            if action.get("kind") != "pick" or action.get("perk_id") not in offered:
                raise ValueError("Нужно выбрать предложенный дар.")
            choice = action["perk_id"]
            state["health"], state["perks"] = rhythm_rules.apply_perk(choice, health=state["health"], perks=state["perks"])
            state["selected"].append(choice)
            continue
        elapsed, rune = action.get("elapsed_ms"), action.get("rune")
        if (action.get("kind") != "tap" or action.get("signal_no") != state["next_signal_no"]
                or type(elapsed) is not int or not 0 <= elapsed <= 60_000 or rune not in (*rhythm_rules.RUNES, None)):
            raise ValueError("Некорректный такт.")
        signal = state["next_signal_no"]
        window = rhythm_rules.window_ms(signal, state["perks"])
        correct = rune == rhythm_rules.expected_rune(seed, signal) and elapsed <= window
        before = state["health"]
        if correct:
            state["score"] += rhythm_rules.score_for_correct(elapsed_ms=elapsed, allowed_window_ms=window,
                combo_before=state["combo"], perks=state["perks"], health=state["health"])
            state["combo"] += 1
            state["correct_streak"] += 1
            state["correct_taps"] += 1
            state["health"], state["perks"] = rhythm_rules.after_correct(state["perks"], health=state["health"], streak_after=state["correct_streak"])
        else:
            state["health"], state["perks"] = rhythm_rules.after_error(health=state["health"], perks=state["perks"], timed_out=rune is None or elapsed > window)
            state["combo"] = state["correct_streak"] = 0
            state["mistakes"] += 1
        rhythm_analysis.record(state["analysis"], signal=signal, chunk_size=rhythm_rules.CHUNK_SIZE,
            window=window, correct=correct, elapsed=elapsed, streak=state["correct_streak"],
            timeout=rune is None or elapsed > window, hearts_lost=before-state["health"] if before>state["health"] else 0)
        state["next_signal_no"] += 1
        if state["health"] == 0:
            state["status"] = "finished"
    if state["status"] != "finished":
        raise ValueError("Забег ещё не завершён.")
    return state


def replay_mine(packet: dict, actions: list[dict]) -> dict:
    row = copy.deepcopy(packet["state"])
    spec = mine_rules.difficulty(row["difficulty"])
    first = packet["first_cell"]
    revealed, flags = set(row["revealed"]), set(row["flags"])
    elapsed = int(row.get("elapsed_ms") or 0)
    for action in actions:
        cell, kind, at = action.get("cell"), action.get("kind"), action.get("elapsed_ms")
        if (row["status"] not in {"active", "awaiting_first_open"} or type(cell) is not int
                or not 0 <= cell < spec.size*spec.size or kind not in {"open", "toggle_flag"}
                or type(at) is not int or not elapsed <= at <= 604_800_000):
            raise ValueError("Некорректный ход Сапёра.")
        if first is None:
            if kind != "open":
                raise ValueError("Сначала открой клетку.")
            first = cell
        layout = mine_rules.board(bytes.fromhex(packet["seed"]), spec, first,
                                 ruleset_version=row.get("ruleset_version", mine_rules.LEGACY_RULESET_VERSION))
        row["opened_actions"] += int(kind == "open" and cell not in revealed and cell not in flags)
        revealed, flags, status, _ = mine_rules.apply_action(spec=spec, layout=layout, revealed=revealed, flags=flags, kind=kind, cell=cell)
        row["status"], row["revision"], elapsed = status, row["revision"]+1, at
    if row["status"] not in {"won", "lost"}:
        raise ValueError("Партия ещё не завершена.")
    row.update(first_cell=first, revealed_json=sorted(revealed), flags_json=sorted(flags), elapsed_ms=elapsed)
    return row


async def _import_local_run(db, *, game: str, user_id: int, run_id: str, origin: dict) -> None:
    """Register a game started from cached rules while offline.

    A client may choose the seed/timing under the owner-approved availability
    policy. It still cannot choose another owner or submit result totals.
    The row starts cancelled so a late upload never replaces a live game.
    """
    repo, conflict, get, save = _parts(game)
    try:
        if str(UUID(run_id, version=4)) != run_id:
            raise ValueError("invalid run id")
        seed = bytes.fromhex(origin["seed"])
        version = origin.get("ruleset_version")
        supported = {rhythm_rules.RULESET_VERSION, "rhythm-v2-rules-5", "rhythm-v2-rules-6"} if game == "rhythm" else mine_rules.SUPPORTED_RULESETS
        if len(seed) != 32 or version not in supported:
            raise ValueError("Обнови правила игры при подключении.")
        spec = mine_rules.difficulty(origin.get("difficulty", "normal")) if game != "rhythm" else None
    except (ValueError, KeyError, TypeError) as exc:
        raise conflict(str(exc)) from exc
    # Idempotent even when two connections race to deliver the same local UUID.
    if game == "rhythm":
        await db.execute("INSERT INTO rhythm_v2_runs(run_id,user_id,mode,ruleset_version,seed,offers_json,status,health) "
                         "VALUES (?,?,'normal',?,?, '{}'::jsonb,'cancelled',5) ON CONFLICT (run_id) DO NOTHING",
                         (run_id, user_id, version, seed))
    else:
        await db.execute("INSERT INTO minesweeper_v2_runs(run_id,user_id,difficulty,ruleset_version,seed,status) "
                         "VALUES (?,?,?,?,?,'cancelled') ON CONFLICT (run_id) DO NOTHING", (run_id, user_id, spec.id, version, seed))
    row = await repo.lock_owned_run(db, run_id=run_id, user_id=user_id)
    if not row:
        raise conflict("Партия принадлежит другому игроку.")
    if await get(db, run_id=run_id, action_id=PACKET_ID):
        return
    # Use exactly the same server-created packet contract as an online start.
    row["status"] = "active" if game == "rhythm" else "awaiting_first_open"
    p = {"protocol": PROTOCOL, "game": game, "run_id": run_id, "owner": str(user_id), "seed": seed.hex()}
    if game == "rhythm":
        p.update(state=rhythm._state(row), catalog=[asdict(g) for g in rhythm_rules.PERKS], ruleset_version=version, legacy=version != rhythm_rules.RULESET_VERSION)
        await rr.set_integrity(db, run_id=run_id, status="offline_exposed", reason=PROTOCOL, evidence={"protocol": PROTOCOL})
    else:
        p.update(state=mine._public(row), first_cell=None)
    await save(db, run_id=run_id, action_id=PACKET_ID, request={"protocol": PROTOCOL}, result=p)


async def finalize(db, *, game: str, user_id: int, run_id: str, actions: list[dict], origin: dict | None = None) -> dict:
    repo, conflict, get, save = _parts(game)
    if not actions or len(actions) > MAX_ACTIONS:
        raise conflict("Некорректный журнал партии.")
    request = {"protocol": PROTOCOL, "actions": actions}
    async with db.connection.transaction():
        row = await repo.lock_owned_run(db, run_id=run_id, user_id=user_id)
        if not row and origin:
            await _import_local_run(db, game=game, user_id=user_id, run_id=run_id, origin=origin)
            row = await repo.lock_owned_run(db, run_id=run_id, user_id=user_id)
        if not row:
            raise conflict("Партия не найдена.")
        previous = await get(db, run_id=run_id, action_id=RESULT_ID)
        if previous:
            if repo.load(previous["request_json"]) != request:
                raise conflict("Результат этой партии уже сохранён.")
            return repo.load(previous["result_json"])
        saved = await get(db, run_id=run_id, action_id=PACKET_ID)
        if not saved or row["status"] not in {"active", "awaiting_first_open", "cancelled"}:
            raise conflict("Эта партия не поддерживает локальный результат.")
        packet_value = repo.load(saved["result_json"])
        try:
            state = replay_rhythm(packet_value, actions) if game == "rhythm" else replay_mine(packet_value, actions)
        except (ValueError, KeyError, TypeError) as exc:
            raise conflict(str(exc)) from exc
        now = row["server_now"]
        if game == "rhythm":
            state["finished_at"] = now
            await rr.update_run(db, run_id=run_id, state=state)
            await rhythm._settle_finished_run(db, row=row, state=state, user_id=user_id,
                integrity_status="clear", integrity_reason=PROTOCOL, integrity_evidence={"protocol": PROTOCOL, "client_timed": True})
            await rr.update_run(db, run_id=run_id, state=state)
            result = rhythm._view(row, state, now=now)
        else:
            row.update(state, started_at=now-timedelta(milliseconds=state["elapsed_ms"]), finished_at=now)
            await mr.update_run(db, run_id=run_id, first_cell=row["first_cell"], revealed=set(row["revealed_json"]),
                flags=set(row["flags_json"]), status=row["status"], revision=row["revision"], opened_actions=row["opened_actions"],
                started_at=row["started_at"], finished_at=now, elapsed_ms=row["elapsed_ms"])
            if row["status"] == "won":
                await mr.upsert_leaderboard(db, run_id=run_id, user_id=user_id, difficulty=row["difficulty"],
                    ruleset_version=row["ruleset_version"], elapsed_ms=row["elapsed_ms"], opened_actions=row["opened_actions"])
            await mine._record_completed_quest(db, user_id=user_id, run_id=run_id, difficulty=row["difficulty"], won=row["status"] == "won")
            result = mine._public(row, now=now)
        await save(db, run_id=run_id, action_id=RESULT_ID, request=request, result=result)
        return result
