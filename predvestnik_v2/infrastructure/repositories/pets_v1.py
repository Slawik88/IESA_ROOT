"""Durable state for the approved pet system; legacy pet fields are read only."""
from __future__ import annotations

import json
from typing import Any


async def ensure_tables(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS pet_v1_profiles (
            user_id BIGINT PRIMARY KEY,
            active_pet_id BIGINT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS pet_v1_state (
            user_id BIGINT NOT NULL, pet_id BIGINT NOT NULL,
            level INTEGER NOT NULL DEFAULT 1 CHECK(level BETWEEN 1 AND 16),
            endurance INTEGER NOT NULL DEFAULT 100 CHECK(endurance BETWEEN 0 AND 100),
            endurance_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(user_id, pet_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS pet_v1_actions (
            user_id BIGINT NOT NULL, action_id TEXT NOT NULL,
            request_json TEXT NOT NULL, response_json TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(user_id, action_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS pet_v1_runs (
            id TEXT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            pet_id BIGINT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('trek','expedition')),
            duration_hours SMALLINT NOT NULL CHECK(duration_hours IN (3,6,9)),
            status TEXT NOT NULL CHECK(status IN ('active','ready','claimed','cancelled')),
            starts_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ends_at TIMESTAMPTZ NOT NULL,
            ready_at TIMESTAMPTZ NULL,
            revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0)
        )
    """)
    await db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_pet_v1_one_active_run
        ON pet_v1_runs(user_id) WHERE status IN ('active','ready')
    """)
    async with db.execute("SELECT to_regclass('chest_key_grants_v1')") as cursor:
        chest_grants_ready = (await cursor.fetchone())[0] is not None
    if chest_grants_ready:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pet_v1_activity_rewards (
                run_id TEXT PRIMARY KEY REFERENCES pet_v1_runs(id) ON DELETE RESTRICT,
                user_id BIGINT NOT NULL, activity_kind TEXT NOT NULL CHECK(activity_kind IN ('trek','expedition')),
                key_grant_id TEXT NOT NULL UNIQUE REFERENCES chest_key_grants_v1(id) ON DELETE RESTRICT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP()
            )
        """)
        await db.execute("""
            CREATE OR REPLACE FUNCTION reject_pet_v1_activity_reward_rewrite()
            RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'pet activity rewards are append-only'; END; $$
        """)
        await db.execute("DROP TRIGGER IF EXISTS pet_v1_activity_rewards_append_only ON pet_v1_activity_rewards")
        await db.execute("""
            CREATE TRIGGER pet_v1_activity_rewards_append_only BEFORE UPDATE OR DELETE ON pet_v1_activity_rewards
            FOR EACH ROW EXECUTE FUNCTION reject_pet_v1_activity_reward_rewrite()
        """)
    await db.execute("ALTER TABLE pet_v1_runs ADD COLUMN IF NOT EXISTS decision TEXT NULL CHECK(decision IN ('careful','steady','bold'))")
    await db.execute("ALTER TABLE pet_v1_runs ADD COLUMN IF NOT EXISTS decided_at TIMESTAMPTZ NULL")
    await db.execute("""
        CREATE TABLE IF NOT EXISTS pet_v1_duplicate_sources (
            user_id BIGINT NOT NULL,
            source_event_id TEXT NOT NULL,
            pet_id BIGINT NOT NULL,
            source_kind TEXT NOT NULL CHECK(source_kind = 'chest_v1'),
            source_snapshot JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(user_id, source_event_id)
        )
    """)
    await db.execute("""
        CREATE OR REPLACE FUNCTION reject_pet_v1_duplicate_source_rewrite()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'pet_v1_duplicate_sources is append-only';
        END;
        $$
    """)
    await db.execute("DROP TRIGGER IF EXISTS pet_v1_duplicate_sources_append_only ON pet_v1_duplicate_sources")
    await db.execute("""
        CREATE TRIGGER pet_v1_duplicate_sources_append_only
        BEFORE UPDATE OR DELETE ON pet_v1_duplicate_sources
        FOR EACH ROW EXECUTE FUNCTION reject_pet_v1_duplicate_source_rewrite()
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS pet_v1_duplicate_progressions (
            id TEXT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            source_event_id TEXT NOT NULL,
            pet_id BIGINT NOT NULL,
            level_before INTEGER NOT NULL CHECK(level_before BETWEEN 1 AND 16),
            level_after INTEGER NOT NULL CHECK(level_after BETWEEN 1 AND 16),
            level_cap INTEGER NOT NULL CHECK(level_cap = 16),
            outcome TEXT NOT NULL CHECK(outcome IN ('level_up','max_compensated')),
            echo_amount SMALLINT NOT NULL CHECK(echo_amount IN (0,1)),
            policy_version TEXT NOT NULL,
            source_snapshot JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, source_event_id),
            CHECK(
                (outcome = 'level_up' AND level_before BETWEEN 1 AND 15 AND level_after = level_before + 1 AND echo_amount = 0)
                OR
                (outcome = 'max_compensated' AND level_before = 16 AND level_after = 16 AND echo_amount = 1)
            )
        )
    """)
    await db.execute("""
        CREATE OR REPLACE FUNCTION reject_pet_v1_duplicate_progression_rewrite()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'pet_v1_duplicate_progressions is append-only';
        END;
        $$
    """)
    await db.execute("DROP TRIGGER IF EXISTS pet_v1_duplicate_progressions_append_only ON pet_v1_duplicate_progressions")
    await db.execute("""
        CREATE TRIGGER pet_v1_duplicate_progressions_append_only
        BEFORE UPDATE OR DELETE ON pet_v1_duplicate_progressions
        FOR EACH ROW EXECUTE FUNCTION reject_pet_v1_duplicate_progression_rewrite()
    """)
    await db.commit()


async def lock_user(db, user_id: int) -> None:
    async with db.execute("SELECT pg_advisory_xact_lock(?)", (int(user_id),)) as c:
        await c.fetchone()


async def get_owned_pet(db, user_id: int, pet_id: int) -> dict[str, Any] | None:
    async with db.execute("SELECT id FROM pets WHERE owner_id=? AND id=?", (int(user_id), int(pet_id))) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def get_profile(db, user_id: int) -> dict[str, Any] | None:
    async with db.execute("SELECT * FROM pet_v1_profiles WHERE user_id=?", (int(user_id),)) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def list_owned_pets(db, user_id: int) -> list[dict[str, Any]]:
    async with db.execute(
        "SELECT p.id,p.name,p.species_id,p.rarity,s.level,s.endurance,s.endurance_updated_at,NOW() AS server_now "
        "FROM pets p LEFT JOIN pet_v1_state s ON s.user_id=p.owner_id AND s.pet_id=p.id "
        "WHERE p.owner_id=? ORDER BY p.created_at,p.id", (int(user_id),)
    ) as c:
        return [dict(row) for row in await c.fetchall()]


async def get_state(db, user_id: int, pet_id: int) -> dict[str, Any]:
    await db.execute("INSERT INTO pet_v1_state(user_id,pet_id) VALUES (?,?) ON CONFLICT DO NOTHING", (int(user_id), int(pet_id)))
    async with db.execute("SELECT *, NOW() AS server_now FROM pet_v1_state WHERE user_id=? AND pet_id=? FOR UPDATE", (int(user_id), int(pet_id))) as c:
        row = await c.fetchone()
    if not row: raise RuntimeError("Pet state was not created")
    return dict(row)


async def save_profile(db, user_id: int, pet_id: int) -> None:
    await db.execute("INSERT INTO pet_v1_profiles(user_id,active_pet_id) VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET active_pet_id=EXCLUDED.active_pet_id,updated_at=NOW()", (int(user_id),int(pet_id)))


async def save_endurance(db, user_id: int, pet_id: int, endurance: int) -> None:
    await db.execute("UPDATE pet_v1_state SET endurance=?, endurance_updated_at=NOW() WHERE user_id=? AND pet_id=?", (int(endurance),int(user_id),int(pet_id)))


async def find_duplicate_progression(db, user_id: int, source_event_id: str) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT * FROM pet_v1_duplicate_progressions WHERE user_id=? AND source_event_id=?",
        (int(user_id), str(source_event_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def find_terminal_duplicate_source(db, user_id: int, source_event_id: str) -> dict[str, Any] | None:
    """Return only a receipt that a future verified chest writer created."""
    async with db.execute(
        "SELECT * FROM pet_v1_duplicate_sources WHERE user_id=? AND source_event_id=? FOR KEY SHARE",
        (int(user_id), str(source_event_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def save_duplicate_progression(
    db, *, progression_id: str, user_id: int, source_event_id: str, pet_id: int,
    level_before: int, level_after: int, outcome: str, echo_amount: int,
    policy_version: str, source_snapshot: dict[str, Any],
) -> None:
    encoded = json.dumps(source_snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    await db.execute(
        "INSERT INTO pet_v1_duplicate_progressions "
        "(id,user_id,source_event_id,pet_id,level_before,level_after,level_cap,outcome,echo_amount,policy_version,source_snapshot) "
        "VALUES (?,?,?,?,?,?,16,?,?,?,?::jsonb)",
        (str(progression_id), int(user_id), str(source_event_id), int(pet_id), int(level_before),
         int(level_after), str(outcome), int(echo_amount), str(policy_version), encoded),
    )


async def set_level(db, user_id: int, pet_id: int, level: int) -> None:
    await db.execute(
        "UPDATE pet_v1_state SET level=? WHERE user_id=? AND pet_id=?",
        (int(level), int(user_id), int(pet_id)),
    )


async def cached_action(db, user_id: int, action_id: str) -> dict | None:
    async with db.execute("SELECT request_json,response_json FROM pet_v1_actions WHERE user_id=? AND action_id=?", (int(user_id),action_id)) as c:
        row=await c.fetchone()
    return {"request":json.loads(row[0]),"response":json.loads(row[1])} if row else None


async def save_action(db,user_id:int,action_id:str,request:dict,response:dict)->None:
    await db.execute("INSERT INTO pet_v1_actions(user_id,action_id,request_json,response_json) VALUES (?,?,?,?)", (int(user_id),action_id,json.dumps(request,sort_keys=True),json.dumps(response,sort_keys=True)))


async def advance_due_runs(db, user_id: int) -> None:
    # A trek is deliberately just a timer.  Leaving it in ``ready`` would
    # soft-lock the one shared activity slot because there is no follow-up
    # player action for a trek.  Expeditions alone wait for a route decision.
    await db.execute(
        "UPDATE pet_v1_runs SET status='claimed',ready_at=NOW(),revision=revision+1 "
        "WHERE user_id=? AND kind='trek' AND status='active' AND ends_at<=NOW()", (int(user_id),)
    )
    await db.execute(
        "UPDATE pet_v1_runs SET status='ready',ready_at=NOW(),revision=revision+1 "
        "WHERE user_id=? AND kind='expedition' AND status='active' AND ends_at<=NOW()", (int(user_id),)
    )


async def active_run(db, user_id: int) -> dict | None:
    async with db.execute(
        "SELECT id,pet_id,kind,duration_hours,status,starts_at,ends_at,ready_at,decision,decided_at,revision,NOW() AS server_now "
        "FROM pet_v1_runs WHERE user_id=? AND status IN ('active','ready') FOR UPDATE", (int(user_id),)
    ) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def create_run(db, *, run_id: str, user_id: int, pet_id: int, kind: str, hours: int) -> dict:
    async with db.execute(
        "INSERT INTO pet_v1_runs(id,user_id,pet_id,kind,duration_hours,status,ends_at) "
        "VALUES (?,?,?,?,?,'active',NOW()+make_interval(hours => ?)) "
        "RETURNING id,pet_id,kind,duration_hours,status,starts_at,ends_at,ready_at,decision,decided_at,revision,NOW() AS server_now",
        (str(run_id), int(user_id), int(pet_id), str(kind), int(hours), int(hours)),
    ) as c:
        row = await c.fetchone()
    if not row:
        raise RuntimeError("Pet run was not created")
    return dict(row)


async def choose_expedition(db, *, user_id: int, choice: str) -> dict | None:
    async with db.execute(
        # A route is the terminal interaction of the currently released
        # expedition slice.  It awards no inventory/currency, but it must
        # release the shared timer; otherwise one choice permanently locks all
        # later treks and expeditions for this player.
        "UPDATE pet_v1_runs SET decision=?,decided_at=NOW(),status='claimed',revision=revision+1 "
        "WHERE user_id=? AND kind='expedition' AND status='ready' AND decision IS NULL "
        "RETURNING id,pet_id,kind,duration_hours,status,starts_at,ends_at,ready_at,decision,decided_at,revision,NOW() AS server_now",
        (str(choice), int(user_id)),
    ) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def unrewarded_completed_runs(db, user_id: int) -> list[dict[str, Any]]:
    async with db.execute(
        "SELECT r.* FROM pet_v1_runs r LEFT JOIN pet_v1_activity_rewards reward ON reward.run_id=r.id "
        "WHERE r.user_id=? AND r.status='claimed' AND reward.run_id IS NULL "
        "ORDER BY r.starts_at,r.id FOR UPDATE OF r",
        (int(user_id),),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def save_activity_reward(
    db, *, run_id: str, user_id: int, activity_kind: str, key_grant_id: str,
) -> None:
    await db.execute(
        "INSERT INTO pet_v1_activity_rewards(run_id,user_id,activity_kind,key_grant_id) VALUES (?,?,?,?)",
        (str(run_id), int(user_id), str(activity_kind), str(key_grant_id)),
    )


async def consume_food(
    db, *, user_id: int, pet_id: int, food_id: str, restore: int,
) -> tuple[int, int]:
    state = await get_state(db, int(user_id), int(pet_id))
    current, _ = __import__("core.pets_v1", fromlist=["endurance_after_elapsed"]).endurance_after_elapsed(
        int(state["endurance"]), last_updated_at=state["endurance_updated_at"], now=state["server_now"],
    )
    if current >= 100:
        raise ValueError("Выносливость уже полная.")
    async with db.execute(
        "UPDATE chest_food_balances_v1 SET quantity=quantity-1,updated_at=CLOCK_TIMESTAMP() "
        "WHERE user_id=? AND food_id=? AND quantity>0 RETURNING quantity",
        (int(user_id), str(food_id)),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise ValueError("Такой еды нет в инвентаре.")
    after = min(100, current + int(restore))
    await save_endurance(db, int(user_id), int(pet_id), after)
    return after, int(row[0])
