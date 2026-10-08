"""Durable state for pets v2 «Тропа». Питомцы остаются в `pets`; здесь — прокачка, энергия, занятия и суточный учёт."""
from __future__ import annotations

import json
from typing import Any


async def ensure_tables(db) -> None:
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
        CREATE TABLE IF NOT EXISTS pet_v2_actions (
            user_id BIGINT NOT NULL, action_id TEXT NOT NULL,
            request_json TEXT NOT NULL, response_json TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(user_id, action_id)
        )
    """)
    await db.commit()


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
        "SELECT p.id,p.name,p.species_id,p.rarity,s.level,s.xp,s.energy,s.energy_at,s.pity,s.calling,s.traits "
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


async def create_run(db, *, run_id: str, user_id: int, pet_id: int, kind: str, hours: int, route: str | None) -> dict[str, Any]:
    async with db.execute(
        "INSERT INTO pet_v2_runs(id,user_id,pet_id,kind,hours,route,status,ends_at) "
        "VALUES (?,?,?,?,?,?,'active',NOW()+(?*INTERVAL '1 hour')) RETURNING *",
        (run_id, int(user_id), int(pet_id), kind, int(hours), route, int(hours)),
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
