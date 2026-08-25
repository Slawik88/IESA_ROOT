"""Персистентность Reconstruction 3.0.

Все таблицы изолированы от старой экономики. ``revision`` защищает состояние
боя от двух параллельных действий, а ``gameplay_run_actions`` возвращает тот же
ответ при сетевом retry с тем же ``action_id``.
"""
from __future__ import annotations

import json
from typing import Any


async def ensure_tables(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS gameplay_progress (
            user_id            BIGINT NOT NULL,
            game_version       TEXT NOT NULL,
            current_encounter  TEXT NOT NULL,
            completed_json     TEXT NOT NULL DEFAULT '[]',
            memories_json      TEXT NOT NULL DEFAULT '[]',
            route_choices_json TEXT NOT NULL DEFAULT '{}',
            last_difficulty_profile TEXT NOT NULL DEFAULT 'standard',
            started_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, game_version)
        )
    """)
    await db.execute(
        "ALTER TABLE gameplay_progress ADD COLUMN IF NOT EXISTS "
        "route_choices_json TEXT NOT NULL DEFAULT '{}'"
    )
    await db.execute(
        "ALTER TABLE gameplay_progress ADD COLUMN IF NOT EXISTS "
        "last_difficulty_profile TEXT NOT NULL DEFAULT 'standard'"
    )
    await db.execute("""
        CREATE TABLE IF NOT EXISTS gameplay_runs (
            id                 BIGSERIAL PRIMARY KEY,
            user_id            BIGINT NOT NULL,
            game_version       TEXT NOT NULL,
            balance_version    TEXT NOT NULL,
            encounter_id       TEXT NOT NULL,
            state_json         TEXT NOT NULL,
            status             TEXT NOT NULL DEFAULT 'active',
            revision           INTEGER NOT NULL DEFAULT 0,
            started_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at       TIMESTAMPTZ NULL
        )
    """)
    await db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_gameplay_active_run "
        "ON gameplay_runs(user_id, game_version) WHERE status = 'active'"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_gameplay_runs_user "
        "ON gameplay_runs(user_id, started_at DESC)"
    )
    await db.execute("""
        CREATE TABLE IF NOT EXISTS gameplay_stats (
            user_id            BIGINT NOT NULL,
            game_version       TEXT NOT NULL,
            runs_started       INTEGER NOT NULL DEFAULT 0,
            runs_won           INTEGER NOT NULL DEFAULT 0,
            runs_lost          INTEGER NOT NULL DEFAULT 0,
            total_taps         BIGINT NOT NULL DEFAULT 0,
            correct_taps       BIGINT NOT NULL DEFAULT 0,
            mistakes           BIGINT NOT NULL DEFAULT 0,
            missed_signals     BIGINT NOT NULL DEFAULT 0,
            critical_taps      BIGINT NOT NULL DEFAULT 0,
            discharges         BIGINT NOT NULL DEFAULT 0,
            best_combo         INTEGER NOT NULL DEFAULT 0,
            fastest_win_ms     BIGINT NULL,
            total_play_ms      BIGINT NOT NULL DEFAULT 0,
            upgrades_json      TEXT NOT NULL DEFAULT '{}',
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, game_version)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS gameplay_run_actions (
            run_id          BIGINT NOT NULL REFERENCES gameplay_runs(id) ON DELETE CASCADE,
            action_id       TEXT NOT NULL,
            request_json    TEXT NOT NULL,
            response_json   TEXT NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (run_id, action_id)
        )
    """)
    await db.commit()


async def lock_user(db, user_id: int) -> None:
    """Сериализовать мутации одного игрока внутри внешней транзакции."""
    async with db.execute("SELECT pg_advisory_xact_lock(?)", (int(user_id),)) as cursor:
        await cursor.fetchone()


def empty_stats() -> dict[str, Any]:
    return {
        "runs_started": 0,
        "runs_won": 0,
        "runs_lost": 0,
        "total_taps": 0,
        "correct_taps": 0,
        "mistakes": 0,
        "missed_signals": 0,
        "critical_taps": 0,
        "discharges": 0,
        "best_combo": 0,
        "fastest_win_ms": None,
        "total_play_ms": 0,
        "upgrades": {},
        "accuracy": None,
    }


async def get_stats(db, user_id: int, game_version: str) -> dict[str, Any]:
    async with db.execute(
        "SELECT * FROM gameplay_stats WHERE user_id = ? AND game_version = ?",
        (user_id, game_version),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        return empty_stats()
    data = dict(row)
    data["upgrades"] = json.loads(data.pop("upgrades_json") or "{}")
    attempts = int(data["correct_taps"]) + int(data["mistakes"]) + int(data["missed_signals"])
    data["accuracy"] = (
        round(int(data["correct_taps"]) / attempts * 100, 1) if attempts else None
    )
    return data


async def record_run_started(db, user_id: int, game_version: str) -> dict[str, Any]:
    await db.execute(
        "INSERT INTO gameplay_stats (user_id, game_version, runs_started) VALUES (?, ?, 1) "
        "ON CONFLICT (user_id, game_version) DO UPDATE SET "
        "runs_started = gameplay_stats.runs_started + 1, updated_at = NOW()",
        (user_id, game_version),
    )
    return await get_stats(db, user_id, game_version)


async def record_run_completed(
    db,
    user_id: int,
    game_version: str,
    *,
    outcome: str,
    mastery: dict[str, Any],
    best_combo: int,
    upgrades: list[str],
) -> dict[str, Any]:
    await db.execute(
        "INSERT INTO gameplay_stats (user_id, game_version) VALUES (?, ?) "
        "ON CONFLICT (user_id, game_version) DO NOTHING",
        (user_id, game_version),
    )
    current = await get_stats(db, user_id, game_version)
    upgrade_counts = dict(current["upgrades"])
    for upgrade_id in upgrades:
        upgrade_counts[upgrade_id] = int(upgrade_counts.get(upgrade_id, 0)) + 1
    elapsed_ms = max(0, int(mastery.get("elapsed_ms", 0)))
    fastest_win_ms = current.get("fastest_win_ms")
    if outcome == "won" and (fastest_win_ms is None or elapsed_ms < int(fastest_win_ms)):
        fastest_win_ms = elapsed_ms
    await db.execute(
        "UPDATE gameplay_stats SET "
        "runs_won = runs_won + ?, runs_lost = runs_lost + ?, "
        "total_taps = total_taps + ?, correct_taps = correct_taps + ?, "
        "mistakes = mistakes + ?, missed_signals = missed_signals + ?, "
        "critical_taps = critical_taps + ?, discharges = discharges + ?, "
        "best_combo = GREATEST(best_combo, ?), fastest_win_ms = ?, "
        "total_play_ms = total_play_ms + ?, upgrades_json = ?, updated_at = NOW() "
        "WHERE user_id = ? AND game_version = ?",
        (
            1 if outcome == "won" else 0,
            1 if outcome == "lost" else 0,
            max(0, int(mastery.get("total_taps", 0))),
            max(0, int(mastery.get("correct_taps", 0))),
            max(0, int(mastery.get("mistakes", 0))),
            max(0, int(mastery.get("missed_signals", 0))),
            max(0, int(mastery.get("critical_taps", 0))),
            max(0, int(mastery.get("discharges", 0))),
            max(0, int(best_combo)),
            fastest_win_ms,
            elapsed_ms,
            json.dumps(upgrade_counts, ensure_ascii=False, separators=(",", ":")),
            user_id,
            game_version,
        ),
    )
    return await get_stats(db, user_id, game_version)


def _decode_progress(row: Any) -> dict[str, Any] | None:
    if not row:
        return None
    data = dict(row)
    data["completed"] = json.loads(data.pop("completed_json") or "[]")
    data["memories"] = json.loads(data.pop("memories_json") or "[]")
    data["route_choices"] = json.loads(data.pop("route_choices_json") or "{}")
    data["last_difficulty_profile"] = str(data.get("last_difficulty_profile") or "standard")
    return data


async def get_progress(db, user_id: int, game_version: str) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT * FROM gameplay_progress WHERE user_id = ? AND game_version = ?",
        (user_id, game_version),
    ) as cursor:
        return _decode_progress(await cursor.fetchone())


async def ensure_progress(
    db, user_id: int, game_version: str, first_encounter: str
) -> dict[str, Any]:
    await db.execute(
        "INSERT INTO gameplay_progress (user_id, game_version, current_encounter) "
        "VALUES (?, ?, ?) ON CONFLICT (user_id, game_version) DO NOTHING",
        (user_id, game_version, first_encounter),
    )
    progress = await get_progress(db, user_id, game_version)
    if not progress:
        raise RuntimeError("Не удалось создать прогресс Reconstruction 3.0.")
    return progress


async def save_progress(
    db,
    user_id: int,
    game_version: str,
    *,
    current_encounter: str,
    completed: list[str],
    memories: list[str],
    route_choices: dict[str, str],
) -> None:
    await db.execute(
        "UPDATE gameplay_progress SET current_encounter = ?, completed_json = ?, "
        "memories_json = ?, route_choices_json = ?, updated_at = NOW() "
        "WHERE user_id = ? AND game_version = ?",
        (
            current_encounter,
            json.dumps(completed, ensure_ascii=False),
            json.dumps(memories, ensure_ascii=False),
            json.dumps(route_choices, ensure_ascii=False, sort_keys=True),
            user_id,
            game_version,
        ),
    )


async def set_last_difficulty_profile(
    db, user_id: int, game_version: str, difficulty_id: str
) -> None:
    await db.execute(
        "UPDATE gameplay_progress SET last_difficulty_profile = ?, updated_at = NOW() "
        "WHERE user_id = ? AND game_version = ?",
        (str(difficulty_id), int(user_id), game_version),
    )


def _decode_run(row: Any) -> dict[str, Any] | None:
    if not row:
        return None
    data = dict(row)
    data["state"] = json.loads(data.pop("state_json") or "{}")
    return data


async def get_active_run(db, user_id: int, game_version: str) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT * FROM gameplay_runs WHERE user_id = ? AND game_version = ? "
        "AND status = 'active' ORDER BY id DESC LIMIT 1",
        (user_id, game_version),
    ) as cursor:
        return _decode_run(await cursor.fetchone())


async def get_run(db, run_id: int, user_id: int) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT * FROM gameplay_runs WHERE id = ? AND user_id = ?",
        (run_id, user_id),
    ) as cursor:
        return _decode_run(await cursor.fetchone())


async def create_run(
    db,
    user_id: int,
    game_version: str,
    balance_version: str,
    encounter_id: str,
    state_json: str,
) -> int:
    async with db.execute(
        "INSERT INTO gameplay_runs "
        "(user_id, game_version, balance_version, encounter_id, state_json) "
        "VALUES (?, ?, ?, ?, ?) RETURNING id",
        (user_id, game_version, balance_version, encounter_id, state_json),
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0])


async def save_run_state(
    db,
    run_id: int,
    expected_revision: int,
    state_json: str,
    status: str,
) -> int | None:
    completed_sql = ", completed_at = NOW()" if status in ("won", "lost", "cancelled") else ""
    async with db.execute(
        "UPDATE gameplay_runs SET state_json = ?, status = ?, revision = revision + 1, "
        f"updated_at = NOW(){completed_sql} "
        "WHERE id = ? AND revision = ? AND status = 'active' RETURNING revision",
        (state_json, status, run_id, expected_revision),
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else None


async def get_action_response(db, run_id: int, action_id: str) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT response_json FROM gameplay_run_actions WHERE run_id = ? AND action_id = ?",
        (run_id, action_id),
    ) as cursor:
        row = await cursor.fetchone()
    return json.loads(row[0]) if row else None


async def save_action_response(
    db,
    run_id: int,
    action_id: str,
    request: dict[str, Any],
    response: dict[str, Any],
) -> None:
    await db.execute(
        "INSERT INTO gameplay_run_actions (run_id, action_id, request_json, response_json) "
        "VALUES (?, ?, ?, ?) ON CONFLICT (run_id, action_id) DO NOTHING",
        (
            run_id,
            action_id,
            json.dumps(request, ensure_ascii=False, separators=(",", ":")),
            json.dumps(response, ensure_ascii=False, separators=(",", ":")),
        ),
    )
