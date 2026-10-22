"""Durable state for pets v2 «Тропа». Питомцы остаются в `pets`; здесь — прокачка, энергия, занятия и суточный учёт."""
from __future__ import annotations

import json
from typing import Any


async def ensure_tables(db) -> None:
    # /me and debounced /preview are hot read paths. Even ALTER IF NOT EXISTS
    # takes a table lock; use catalog reads once the installation is complete.
    if await _schema_ready(db):
        return
    async with db.connection.transaction():
        await db.execute("SELECT pg_advisory_xact_lock(hashtextextended('ensure_tables:pets_v2', 0))")
        if not await _schema_ready(db):
            await _ensure_tables_unlocked(db)


async def _schema_ready(db) -> bool:
    # No process cache: a recreated database or partially applied rollout must
    # be detected by the next request, including in an already running worker.
    async with db.execute("""
        SELECT NOT EXISTS (
            SELECT 1 FROM unnest(ARRAY[
                'pet_v2_build_presets', 'pet_v2_state', 'pet_v2_talismans',
                'pet_v2_bond_days', 'pet_v2_daily', 'pet_v2_runs',
                'pet_v2_stage_rewards', 'pet_v2_camp', 'pet_v2_camp_jobs',
                'pet_v2_tracks', 'pet_v2_trials', 'pet_v2_actions', 'pet_v2_parts', 'pet_v2_outings', 'uq_pet_v2_outing_active', 'idx_pet_v2_outing_day',
                'idx_pet_v2_talismans_user', 'uq_pet_v2_one_open_run',
                'idx_pet_v2_runs_user_day', 'idx_pet_v2_tracks_user_day'
            ]) AS name WHERE to_regclass(name) IS NULL
        ) AND NOT EXISTS (
            SELECT 1 FROM (VALUES
                ('pet_v2_state', 'calling'), ('pet_v2_state', 'traits'),
                ('pet_v2_state', 'calling_changed_at'), ('pet_v2_state', 'traits_changed_at'),
                ('pet_v2_state', 'fed_favorite_on'), ('pet_v2_state', 'fed_xp_on'),
                ('pet_v2_runs', 'companion_id'), ('pet_v2_state', 'equipment')
            ) AS required(tbl, col) WHERE NOT EXISTS (
                SELECT 1 FROM pg_attribute WHERE attrelid=to_regclass(required.tbl)
                    AND attname=required.col AND NOT attisdropped
            )
        )
    """) as cursor:
        return bool((await cursor.fetchone())[0])


async def _ensure_tables_unlocked(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS pet_v2_build_presets (
            user_id BIGINT NOT NULL, pet_id BIGINT NOT NULL,
            slot SMALLINT NOT NULL CHECK(slot BETWEEN 1 AND 3),
            name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 40),
            build JSONB NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(user_id, pet_id, slot)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS pet_v2_state (
            user_id BIGINT NOT NULL, pet_id BIGINT NOT NULL,
            level SMALLINT NOT NULL DEFAULT 1 CHECK(level BETWEEN 1 AND 30),
            xp DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK(xp >= 0),
            energy DOUBLE PRECISION NOT NULL CHECK(energy >= 0),
            energy_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            pity SMALLINT NOT NULL DEFAULT 0 CHECK(pity BETWEEN 0 AND 3),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(user_id, pet_id)
        )
    """)
    await db.execute("ALTER TABLE pet_v2_state ADD COLUMN IF NOT EXISTS calling TEXT NULL")
    await db.execute("ALTER TABLE pet_v2_state ADD COLUMN IF NOT EXISTS traits JSONB NOT NULL DEFAULT '[]'::jsonb")
    await db.execute("ALTER TABLE pet_v2_state ADD COLUMN IF NOT EXISTS calling_changed_at DATE NULL")
    await db.execute("ALTER TABLE pet_v2_state ADD COLUMN IF NOT EXISTS traits_changed_at DATE NULL")
    await db.execute("ALTER TABLE pet_v2_state ADD COLUMN IF NOT EXISTS fed_favorite_on DATE NULL")
    await db.execute("ALTER TABLE pet_v2_state ADD COLUMN IF NOT EXISTS fed_xp_on DATE NULL")
    await db.execute("ALTER TABLE pet_v2_state ADD COLUMN IF NOT EXISTS equipment JSONB NOT NULL DEFAULT '{}'::jsonb")
    await db.execute("CREATE TABLE IF NOT EXISTS pet_v2_parts (user_id BIGINT PRIMARY KEY, amount INTEGER NOT NULL DEFAULT 0 CHECK(amount>=0))")
    await db.execute("""CREATE TABLE IF NOT EXISTS pet_v2_outings (
        id TEXT PRIMARY KEY, user_id BIGINT NOT NULL, pet_id BIGINT NOT NULL, day DATE NOT NULL,
        active BOOLEAN NOT NULL DEFAULT TRUE, state JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_pet_v2_outing_active ON pet_v2_outings(user_id) WHERE active")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_pet_v2_outing_day ON pet_v2_outings(user_id,day)")
    await db.execute("""
        CREATE TABLE IF NOT EXISTS pet_v2_talismans (
            id TEXT PRIMARY KEY, user_id BIGINT NOT NULL, kind TEXT NOT NULL,
            tier SMALLINT NOT NULL DEFAULT 1 CHECK(tier BETWEEN 1 AND 3),
            pet_id BIGINT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("CREATE INDEX IF NOT EXISTS idx_pet_v2_talismans_user ON pet_v2_talismans(user_id, pet_id)")
    await db.execute("""
        CREATE TABLE IF NOT EXISTS pet_v2_bond_days (
            user_id BIGINT NOT NULL, pet_id BIGINT NOT NULL, day DATE NOT NULL,
            PRIMARY KEY(user_id, pet_id, day)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS pet_v2_daily (
            user_id BIGINT NOT NULL, day DATE NOT NULL,
            raw DOUBLE PRECISION NOT NULL DEFAULT 0,
            credited DOUBLE PRECISION NOT NULL DEFAULT 0,
            finds JSONB NOT NULL DEFAULT '{}'::jsonb,
            PRIMARY KEY(user_id, day)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS pet_v2_runs (
            id TEXT PRIMARY KEY,
            user_id BIGINT NOT NULL, pet_id BIGINT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('trek','expedition','watch')),
            hours SMALLINT NOT NULL CHECK(hours IN (3,6,9,12,24)),
            route TEXT NULL CHECK(route IN ('forest','pass','ruins','swamp')),
            status TEXT NOT NULL CHECK(status IN ('active','claimed')),
            starts_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ends_at TIMESTAMPTZ NOT NULL,
            claimed_at TIMESTAMPTZ NULL,
            result JSONB NULL
        )
    """)
    await db.execute("ALTER TABLE pet_v2_runs ADD COLUMN IF NOT EXISTS companion_id BIGINT NULL")
    await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_pet_v2_one_open_run ON pet_v2_runs(user_id, pet_id) WHERE status='active'")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_pet_v2_runs_user_day ON pet_v2_runs(user_id, claimed_at)")
    await db.execute("""
        CREATE TABLE IF NOT EXISTS pet_v2_stage_rewards (
            user_id BIGINT NOT NULL, pet_id BIGINT NOT NULL, stage SMALLINT NOT NULL,
            essence INTEGER NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(user_id, pet_id, stage)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS pet_v2_camp (
            user_id BIGINT NOT NULL, building TEXT NOT NULL CHECK(building IN ('lounge','markers','workshop')),
            level SMALLINT NOT NULL DEFAULT 0 CHECK(level BETWEEN 0 AND 5),
            PRIMARY KEY(user_id, building)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS pet_v2_camp_jobs (
            user_id BIGINT PRIMARY KEY, building TEXT NOT NULL, to_level SMALLINT NOT NULL CHECK(to_level BETWEEN 1 AND 5),
            ends_at TIMESTAMPTZ NOT NULL
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS pet_v2_tracks (
            id TEXT PRIMARY KEY, user_id BIGINT NOT NULL, pet_id BIGINT NOT NULL, day DATE NOT NULL,
            hidden SMALLINT NOT NULL CHECK(hidden BETWEEN 0 AND 8),
            opened JSONB NOT NULL DEFAULT '[]'::jsonb, points SMALLINT NOT NULL CHECK(points >= 0),
            status TEXT NOT NULL CHECK(status IN ('open','won','lost')), result JSONB NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("CREATE INDEX IF NOT EXISTS idx_pet_v2_tracks_user_day ON pet_v2_tracks(user_id, day)")
    await db.execute("""
        CREATE TABLE IF NOT EXISTS pet_v2_trials (
            user_id BIGINT NOT NULL, week DATE NOT NULL, pet_id BIGINT NOT NULL,
            difficulty SMALLINT NOT NULL CHECK(difficulty BETWEEN 1 AND 3), essence INTEGER NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY(user_id, week)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS pet_v2_actions (
            user_id BIGINT NOT NULL, action_id TEXT NOT NULL,
            request_json TEXT NOT NULL, response_json TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(user_id, action_id)
        )
    """)
    await db.commit()


async def build_presets(db, user_id: int) -> list[dict]:
    async with db.execute("SELECT p.pet_id,p.slot,p.name,p.build FROM pet_v2_build_presets p "
                          "JOIN pets owned ON owned.id=p.pet_id AND owned.owner_id=p.user_id "
                          "WHERE p.user_id=? ORDER BY p.pet_id,p.slot", (int(user_id),)) as cursor:
        return [{"pet_id": int(r["pet_id"]), "slot": int(r["slot"]), "name": r["name"],
                 "build": json.loads(r["build"]) if isinstance(r["build"], str) else r["build"]} for r in await cursor.fetchall()]


async def put_build_preset(db, user_id: int, pet_id: int, slot: int, name: str, build: dict) -> None:
    await db.execute("INSERT INTO pet_v2_build_presets(user_id,pet_id,slot,name,build) VALUES (?,?,?,?,?::jsonb) "
                     "ON CONFLICT(user_id,pet_id,slot) DO UPDATE SET name=EXCLUDED.name,build=EXCLUDED.build,updated_at=NOW()",
                     (int(user_id), int(pet_id), int(slot), name, json.dumps(build)))


async def lock_user(db, user_id: int) -> None:
    async with db.execute("SELECT pg_advisory_xact_lock(?)", (int(user_id),)) as c:
        await c.fetchone()


async def clock(db) -> dict[str, Any]:
    async with db.execute("SELECT NOW() AS now, (NOW() AT TIME ZONE 'UTC')::date AS day") as c:
        return dict(await c.fetchone())


async def cached_action(db, user_id: int, action_id: str) -> dict | None:
    async with db.execute("SELECT request_json,response_json FROM pet_v2_actions WHERE user_id=? AND action_id=?", (int(user_id), action_id)) as c:
        row = await c.fetchone()
    return {"request": json.loads(row["request_json"]), "response": json.loads(row["response_json"])} if row else None


async def save_action(db, user_id: int, action_id: str, request: dict, response: dict) -> None:
    await db.execute(
        "INSERT INTO pet_v2_actions(user_id,action_id,request_json,response_json) VALUES (?,?,?,?)",
        (int(user_id), action_id, json.dumps(request, sort_keys=True), json.dumps(response, sort_keys=True)),
    )


async def list_owned_pets(db, user_id: int) -> list[dict[str, Any]]:
    async with db.execute(
        "SELECT p.id,p.name,p.species_id,p.rarity,s.level,s.xp,s.energy,s.energy_at,s.pity,s.calling,s.traits,s.fed_favorite_on,"
        "s.fed_xp_on,s.calling_changed_at,s.traits_changed_at,s.equipment "
        "FROM pets p LEFT JOIN pet_v2_state s ON s.user_id=p.owner_id AND s.pet_id=p.id "
        "WHERE p.owner_id=? ORDER BY p.created_at,p.id", (int(user_id),)
    ) as c:
        return [dict(row) for row in await c.fetchall()]


async def get_owned_pet(db, user_id: int, pet_id: int) -> dict[str, Any] | None:
    async with db.execute("SELECT id,name,species_id,rarity FROM pets WHERE owner_id=? AND id=?", (int(user_id), int(pet_id))) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def ensure_state(db, user_id: int, pet_id: int, energy: float) -> dict[str, Any]:
    await db.execute(
        "INSERT INTO pet_v2_state(user_id,pet_id,energy) VALUES (?,?,?) ON CONFLICT DO NOTHING",
        (int(user_id), int(pet_id), float(energy)),
    )
    async with db.execute("SELECT * FROM pet_v2_state WHERE user_id=? AND pet_id=? FOR UPDATE", (int(user_id), int(pet_id))) as c:
        return dict(await c.fetchone())


async def save_state(db, user_id: int, pet_id: int, *, level: int, xp: float, energy: float, pity: int) -> None:
    await db.execute(
        "UPDATE pet_v2_state SET level=?,xp=?,energy=?,energy_at=NOW(),pity=? WHERE user_id=? AND pet_id=?",
        (int(level), float(xp), float(energy), int(pity), int(user_id), int(pet_id)),
    )


async def bond_days(db, user_id: int, pet_id: int) -> int:
    async with db.execute("SELECT COUNT(*) AS n FROM pet_v2_bond_days WHERE user_id=? AND pet_id=?", (int(user_id), int(pet_id))) as c:
        return int((await c.fetchone())["n"])


async def bond_days_all(db, user_id: int) -> tuple[dict[int, int], dict[str, int]]:
    """Дни Связи одним запросом: по питомцам и суммой по видам (для звёзд Привязанности)."""
    async with db.execute(
        "SELECT b.pet_id,p.species_id,COUNT(*) AS n FROM pet_v2_bond_days b JOIN pets p ON p.id=b.pet_id AND p.owner_id=b.user_id "
        "WHERE b.user_id=? GROUP BY b.pet_id,p.species_id", (int(user_id),)
    ) as c:
        rows = await c.fetchall()
    by_species: dict[str, int] = {}
    for row in rows:
        by_species[row["species_id"]] = by_species.get(row["species_id"], 0) + int(row["n"])
    return {int(row["pet_id"]): int(row["n"]) for row in rows}, by_species


async def species_bond_days(db, user_id: int, species_id: str) -> int:
    async with db.execute(
        "SELECT COUNT(*) AS n FROM pet_v2_bond_days b JOIN pets p ON p.id=b.pet_id AND p.owner_id=b.user_id "
        "WHERE b.user_id=? AND p.species_id=?", (int(user_id), str(species_id)),
    ) as c:
        return int((await c.fetchone())["n"])


async def add_bond_day(db, user_id: int, pet_id: int, day) -> None:
    await db.execute("INSERT INTO pet_v2_bond_days(user_id,pet_id,day) VALUES (?,?,?) ON CONFLICT DO NOTHING", (int(user_id), int(pet_id), day))


async def get_daily(db, user_id: int, day) -> dict[str, Any]:
    async with db.execute("SELECT raw,credited,finds FROM pet_v2_daily WHERE user_id=? AND day=?", (int(user_id), day)) as c:
        row = await c.fetchone()
    if not row:
        return {"raw": 0.0, "credited": 0.0, "finds": {}}
    finds = row["finds"]
    return {"raw": float(row["raw"]), "credited": float(row["credited"]), "finds": json.loads(finds) if isinstance(finds, str) else dict(finds)}


async def save_daily(db, user_id: int, day, *, raw: float, credited: float, finds: dict) -> None:
    await db.execute(
        "INSERT INTO pet_v2_daily(user_id,day,raw,credited,finds) VALUES (?,?,?,?,?::jsonb) "
        "ON CONFLICT(user_id,day) DO UPDATE SET raw=EXCLUDED.raw,credited=EXCLUDED.credited,finds=EXCLUDED.finds",
        (int(user_id), day, float(raw), float(credited), json.dumps(finds, sort_keys=True)),
    )


async def week_find_total(db, user_id: int, day, category: str) -> float:
    async with db.execute(
        "SELECT COALESCE(SUM((finds->>?)::double precision),0) AS n FROM pet_v2_daily "
        "WHERE user_id=? AND day>=date_trunc('week', ?::date)::date AND day<=?",
        (category, int(user_id), day, day),
    ) as c:
        return float((await c.fetchone())["n"])


async def routes_claimed_today(db, user_id: int, day, route: str) -> int:
    async with db.execute(
        "SELECT COUNT(*) AS n FROM pet_v2_runs WHERE user_id=? AND status='claimed' AND route=? "
        "AND (claimed_at AT TIME ZONE 'UTC')::date=?", (int(user_id), route, day),
    ) as c:
        return int((await c.fetchone())["n"])


async def route_claims_today(db, user_id: int, day) -> dict[str, int]:
    """Сколько раз сегодня закрыт каждый маршрут: по нему считается затухание повторов."""
    async with db.execute(
        "SELECT route, COUNT(*) AS n FROM pet_v2_runs WHERE user_id=? AND status='claimed' AND route IS NOT NULL "
        "AND (claimed_at AT TIME ZONE 'UTC')::date=? GROUP BY route", (int(user_id), day),
    ) as c:
        return {row["route"]: int(row["n"]) for row in await c.fetchall()}


async def open_runs(db, user_id: int) -> list[dict[str, Any]]:
    async with db.execute(
        "SELECT *, ends_at<=NOW() AS ready FROM pet_v2_runs WHERE user_id=? AND status='active' ORDER BY starts_at", (int(user_id),)
    ) as c:
        return [dict(row) for row in await c.fetchall()]


async def get_run(db, user_id: int, run_id: str) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT *, ends_at<=NOW() AS ready FROM pet_v2_runs WHERE user_id=? AND id=? FOR UPDATE", (int(user_id), str(run_id))
    ) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def create_run(db, *, run_id: str, user_id: int, pet_id: int, kind: str, hours: int, route: str | None,
                     companion_id: int | None = None) -> dict[str, Any]:
    async with db.execute(
        "INSERT INTO pet_v2_runs(id,user_id,pet_id,kind,hours,route,status,ends_at,companion_id) "
        "VALUES (?,?,?,?,?,?,'active',NOW()+(?*INTERVAL '1 hour'),?) RETURNING *",
        (run_id, int(user_id), int(pet_id), kind, int(hours), route, int(hours), companion_id),
    ) as c:
        return dict(await c.fetchone())


async def finish_run(db, run_id: str, result: dict) -> None:
    await db.execute(
        "UPDATE pet_v2_runs SET status='claimed',claimed_at=NOW(),result=?::jsonb WHERE id=? AND status='active'",
        (json.dumps(result, sort_keys=True), str(run_id)),
    )


async def save_stage_reward(db, user_id: int, pet_id: int, stage: int, essence: int) -> bool:
    async with db.execute(
        "INSERT INTO pet_v2_stage_rewards(user_id,pet_id,stage,essence) VALUES (?,?,?,?) ON CONFLICT DO NOTHING RETURNING stage",
        (int(user_id), int(pet_id), int(stage), int(essence)),
    ) as c:
        return await c.fetchone() is not None


async def add_food(db, user_id: int, food_id: str, quantity: int) -> None:
    await db.execute(
        "INSERT INTO chest_food_balances_v1(user_id,food_id,quantity) VALUES (?,?,?) "
        "ON CONFLICT(user_id,food_id) DO UPDATE SET quantity=chest_food_balances_v1.quantity+EXCLUDED.quantity,updated_at=CLOCK_TIMESTAMP()",
        (int(user_id), str(food_id), int(quantity)),
    )


async def add_talisman(db, user_id: int, talisman_id: str, kind: str, tier: int = 1) -> None:
    await db.execute(
        "INSERT INTO pet_v2_talismans(id,user_id,kind,tier) VALUES (?,?,?,?) ON CONFLICT DO NOTHING",
        (str(talisman_id), int(user_id), kind, int(tier)),
    )


async def list_talismans(db, user_id: int) -> list[dict[str, Any]]:
    async with db.execute("SELECT id,kind,tier,pet_id FROM pet_v2_talismans WHERE user_id=? ORDER BY created_at,id", (int(user_id),)) as c:
        return [dict(row) for row in await c.fetchall()]


async def equipped_talismans(db, user_id: int, pet_id: int) -> list[dict[str, Any]]:
    async with db.execute("SELECT id,kind,tier FROM pet_v2_talismans WHERE user_id=? AND pet_id=? ORDER BY id", (int(user_id), int(pet_id))) as c:
        return [dict(row) for row in await c.fetchall()]


async def set_talismans(db, user_id: int, pet_id: int, talisman_ids: list[str]) -> None:
    await db.execute("UPDATE pet_v2_talismans SET pet_id=NULL WHERE user_id=? AND pet_id=?", (int(user_id), int(pet_id)))
    for talisman_id in talisman_ids:
        await db.execute("UPDATE pet_v2_talismans SET pet_id=? WHERE user_id=? AND id=?", (int(pet_id), int(user_id), talisman_id))


async def save_build(db, user_id: int, pet_id: int, *, calling, traits: list[str], calling_changed, traits_changed) -> None:
    await db.execute(
        "UPDATE pet_v2_state SET calling=?,traits=?::jsonb,calling_changed_at=?,traits_changed_at=? WHERE user_id=? AND pet_id=?",
        (calling, json.dumps(traits), calling_changed, traits_changed, int(user_id), int(pet_id)),
    )


async def camp_levels(db, user_id: int) -> dict[str, int]:
    """Уровни построек с учётом уже завершённой стройки (без записи)."""
    levels = {"lounge": 0, "markers": 0, "workshop": 0}
    async with db.execute("SELECT building,level FROM pet_v2_camp WHERE user_id=?", (int(user_id),)) as c:
        for row in await c.fetchall():
            levels[row["building"]] = int(row["level"])
    async with db.execute("SELECT building,to_level FROM pet_v2_camp_jobs WHERE user_id=? AND ends_at<=NOW()", (int(user_id),)) as c:
        row = await c.fetchone()
    if row:
        levels[row["building"]] = max(levels[row["building"]], int(row["to_level"]))
    return levels


async def camp_job(db, user_id: int) -> dict[str, Any] | None:
    async with db.execute("SELECT building,to_level,ends_at,ends_at<=NOW() AS done FROM pet_v2_camp_jobs WHERE user_id=?", (int(user_id),)) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def settle_camp(db, user_id: int) -> None:
    job = await camp_job(db, user_id)
    if job and job["done"]:
        await db.execute(
            "INSERT INTO pet_v2_camp(user_id,building,level) VALUES (?,?,?) "
            "ON CONFLICT(user_id,building) DO UPDATE SET level=GREATEST(pet_v2_camp.level,EXCLUDED.level)",
            (int(user_id), job["building"], int(job["to_level"])),
        )
        await db.execute("DELETE FROM pet_v2_camp_jobs WHERE user_id=?", (int(user_id),))


async def start_camp_job(db, user_id: int, building: str, to_level: int, hours: int) -> None:
    await db.execute(
        "INSERT INTO pet_v2_camp_jobs(user_id,building,to_level,ends_at) VALUES (?,?,?,NOW()+(?*INTERVAL '1 hour'))",
        (int(user_id), building, int(to_level), int(hours)),
    )


async def get_talisman(db, user_id: int, talisman_id: str) -> dict[str, Any] | None:
    async with db.execute("SELECT id,kind,tier,pet_id FROM pet_v2_talismans WHERE user_id=? AND id=? FOR UPDATE", (int(user_id), str(talisman_id))) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def set_talisman_tier(db, user_id: int, talisman_id: str, tier: int) -> None:
    await db.execute("UPDATE pet_v2_talismans SET tier=? WHERE user_id=? AND id=?", (int(tier), int(user_id), str(talisman_id)))


async def tracks_today(db, user_id: int, day, *, lock: bool = True) -> list[dict[str, Any]]:
    async with db.execute(
        f"SELECT * FROM pet_v2_tracks WHERE user_id=? AND day=? ORDER BY created_at,id{' FOR UPDATE' if lock else ''}", (int(user_id), day)
    ) as c:
        rows = [dict(row) for row in await c.fetchall()]
    for row in rows:
        row["opened"] = json.loads(row["opened"]) if isinstance(row["opened"], str) else list(row["opened"])
    return rows


async def create_track(db, *, track_id: str, user_id: int, pet_id: int, day, hidden: int, opened: list, points: int) -> None:
    await db.execute(
        "INSERT INTO pet_v2_tracks(id,user_id,pet_id,day,hidden,opened,points,status) VALUES (?,?,?,?,?,?::jsonb,?,'open')",
        (track_id, int(user_id), int(pet_id), day, int(hidden), json.dumps(opened), int(points)),
    )


async def save_track(db, track_id: str, *, opened: list, points: int, status: str, result: dict | None) -> None:
    await db.execute(
        "UPDATE pet_v2_tracks SET opened=?::jsonb,points=?,status=?,result=?::jsonb WHERE id=?",
        (json.dumps(opened), int(points), status, json.dumps(result) if result is not None else None, track_id),
    )


async def trial_done(db, user_id: int, week) -> bool:
    async with db.execute("SELECT 1 FROM pet_v2_trials WHERE user_id=? AND week=?", (int(user_id), week)) as c:
        return await c.fetchone() is not None


async def save_trial(db, user_id: int, week, pet_id: int, difficulty: int, essence: int) -> None:
    await db.execute(
        "INSERT INTO pet_v2_trials(user_id,week,pet_id,difficulty,essence) VALUES (?,?,?,?,?)",
        (int(user_id), week, int(pet_id), int(difficulty), int(essence)),
    )


async def species_count(db, user_id: int) -> int:
    async with db.execute("SELECT COUNT(DISTINCT species_id) AS n FROM pets WHERE owner_id=?", (int(user_id),)) as c:
        return int((await c.fetchone())["n"])


async def food_stock(db, user_id: int) -> dict[str, int]:
    async with db.execute("SELECT food_id,quantity FROM chest_food_balances_v1 WHERE user_id=? AND quantity>0", (int(user_id),)) as c:
        return {str(row["food_id"]): int(row["quantity"]) for row in await c.fetchall()}


async def consume_food(db, user_id: int, food_id: str) -> int:
    """Списать 1 еду; ValueError, если нечего кормить. Возвращает остаток."""
    async with db.execute(
        "UPDATE chest_food_balances_v1 SET quantity=quantity-1,updated_at=CLOCK_TIMESTAMP() "
        "WHERE user_id=? AND food_id=? AND quantity>0 RETURNING quantity", (int(user_id), str(food_id)),
    ) as c:
        row = await c.fetchone()
    if not row:
        raise ValueError("Нет такой еды.")
    return int(row["quantity"])


async def save_feeding(db, user_id: int, pet_id: int, *, energy: float, fed_favorite_on, fed_xp_on, xp: float, level: int) -> None:
    await db.execute(
        "UPDATE pet_v2_state SET energy=?,energy_at=NOW(),fed_favorite_on=?,fed_xp_on=?,xp=?,level=? WHERE user_id=? AND pet_id=?",
        (float(energy), fed_favorite_on, fed_xp_on, float(xp), int(level), int(user_id), int(pet_id)),
    )
