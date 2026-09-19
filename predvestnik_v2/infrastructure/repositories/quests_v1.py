"""Immutable receipts and current-period state for the approved quest loop."""
from __future__ import annotations

import json


def _load(value):
    return json.loads(value) if isinstance(value, str) else value


async def ensure_tables(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS quest_v1_assignments (
            user_id BIGINT NOT NULL,
            period TEXT NOT NULL CHECK (period IN ('daily','weekly')),
            period_key TEXT NOT NULL,
            slot SMALLINT NOT NULL CHECK (slot >= 0),
            quest_id TEXT NOT NULL,
            definition_json JSONB NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0 CHECK (progress >= 0),
            target INTEGER NOT NULL CHECK (target > 0),
            completed_at TIMESTAMPTZ NULL,
            reroll_generation INTEGER NOT NULL DEFAULT 0 CHECK (reroll_generation >= 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP(),
            PRIMARY KEY (user_id, period, period_key, slot),
            UNIQUE (user_id, period, period_key, quest_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS quest_v1_rerolls (
            user_id BIGINT NOT NULL,
            week_key TEXT NOT NULL,
            used_count SMALLINT NOT NULL DEFAULT 0 CHECK (used_count >= 0),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP(),
            PRIMARY KEY (user_id, week_key)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS quest_v1_actions (
            user_id BIGINT NOT NULL,
            action_id TEXT NOT NULL,
            request_json JSONB NOT NULL,
            response_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP(),
            PRIMARY KEY (user_id, action_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS quest_v1_metric_receipts (
            user_id BIGINT NOT NULL,
            metric TEXT NOT NULL,
            event_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP(),
            PRIMARY KEY (user_id, metric, event_id)
        )
    """)
    # A receipt is inserted in the same transaction as the canonical economic
    # ledger credit.  Its stable period-based id is the anti-repeat boundary;
    # client-generated action ids are deliberately not trusted for rewards.
    await db.execute("""
        CREATE TABLE IF NOT EXISTS quest_v1_reward_receipts (
            user_id BIGINT NOT NULL,
            reward_id TEXT NOT NULL,
            reward_kind TEXT NULL,
            quest_policy_version TEXT NULL,
            reward_policy_version TEXT NULL,
            amount_mora BIGINT NULL,
            granted_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP(),
            PRIMARY KEY (user_id, reward_id)
        )
    """)
    for column, sql_type in (
        ('reward_kind', 'TEXT'), ('quest_policy_version', 'TEXT'),
        ('reward_policy_version', 'TEXT'), ('amount_mora', 'BIGINT'),
    ):
        await db.execute(
            f"ALTER TABLE quest_v1_reward_receipts ADD COLUMN IF NOT EXISTS {column} {sql_type} NULL"
        )
    await db.execute("""
        CREATE OR REPLACE FUNCTION reject_quest_reward_receipt_rewrite_v1()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'quest reward receipts are append-only';
        END;
        $$
    """)
    await db.execute("DROP TRIGGER IF EXISTS quest_v1_reward_receipts_append_only ON quest_v1_reward_receipts")
    await db.execute("""
        CREATE TRIGGER quest_v1_reward_receipts_append_only
        BEFORE UPDATE OR DELETE ON quest_v1_reward_receipts
        FOR EACH ROW EXECUTE FUNCTION reject_quest_reward_receipt_rewrite_v1()
    """)
    await db.commit()


async def lock_user(db, user_id: int) -> None:
    async with db.execute("SELECT pg_advisory_xact_lock(?)", (int(user_id),)) as cursor:
        await cursor.fetchone()


async def list_assignments(db, *, user_id: int, period: str, period_key: str) -> list[dict]:
    async with db.execute(
        "SELECT * FROM quest_v1_assignments WHERE user_id=? AND period=? AND period_key=? ORDER BY slot",
        (int(user_id), str(period), str(period_key)),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def create_assignment(db, *, user_id: int, period: str, period_key: str, slot: int, definition: dict,
                            reroll_generation: int = 0) -> None:
    await db.execute(
        "INSERT INTO quest_v1_assignments(user_id,period,period_key,slot,quest_id,definition_json,target,reroll_generation) "
        "VALUES (?,?,?,?,?,?::jsonb,?,?)",
        (int(user_id), str(period), str(period_key), int(slot), str(definition['id']),
         json.dumps(definition, ensure_ascii=False, sort_keys=True), int(definition['target']), int(reroll_generation)),
    )


async def replace_assignment(db, *, user_id: int, period: str, period_key: str, slot: int, definition: dict,
                             generation: int) -> None:
    await db.execute(
        "UPDATE quest_v1_assignments SET quest_id=?,definition_json=?::jsonb,progress=0,target=?,completed_at=NULL,reroll_generation=? "
        "WHERE user_id=? AND period=? AND period_key=? AND slot=?",
        (str(definition['id']), json.dumps(definition, ensure_ascii=False, sort_keys=True), int(definition['target']),
         int(generation), int(user_id), str(period), str(period_key), int(slot)),
    )


async def action(db, *, user_id: int, action_id: str) -> dict | None:
    async with db.execute("SELECT request_json,response_json FROM quest_v1_actions WHERE user_id=? AND action_id=?",
                          (int(user_id), str(action_id))) as cursor:
        row = await cursor.fetchone()
    return {"request": dict(_load(row[0])), "response": dict(_load(row[1]))} if row else None


async def save_action(db, *, user_id: int, action_id: str, request: dict, response: dict) -> None:
    await db.execute(
        "INSERT INTO quest_v1_actions(user_id,action_id,request_json,response_json) VALUES (?,?,?::jsonb,?::jsonb)",
        (int(user_id), str(action_id), json.dumps(request, ensure_ascii=False, sort_keys=True),
         json.dumps(response, ensure_ascii=False, sort_keys=True)),
    )


async def reroll_state(db, *, user_id: int, week_key: str) -> dict:
    await db.execute("INSERT INTO quest_v1_rerolls(user_id,week_key) VALUES (?,?) ON CONFLICT DO NOTHING",
                     (int(user_id), str(week_key)))
    async with db.execute("SELECT * FROM quest_v1_rerolls WHERE user_id=? AND week_key=? FOR UPDATE",
                          (int(user_id), str(week_key))) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise RuntimeError('quest reroll state was not created')
    return dict(row)


async def consume_reroll(db, *, user_id: int, week_key: str) -> None:
    await db.execute("UPDATE quest_v1_rerolls SET used_count=used_count+1,updated_at=CLOCK_TIMESTAMP() WHERE user_id=? AND week_key=?",
                     (int(user_id), str(week_key)))


async def save_metric_receipt(db, *, user_id: int, metric: str, event_id: str) -> bool:
    async with db.execute(
        "INSERT INTO quest_v1_metric_receipts(user_id,metric,event_id) VALUES (?,?,?) ON CONFLICT DO NOTHING RETURNING 1",
        (int(user_id), str(metric), str(event_id)),
    ) as cursor:
        return bool(await cursor.fetchone())


async def reward_receipt_exists(db, *, user_id: int, reward_id: str) -> bool:
    async with db.execute(
        "SELECT 1 FROM quest_v1_reward_receipts WHERE user_id=? AND reward_id=?",
        (int(user_id), str(reward_id)),
    ) as cursor:
        return bool(await cursor.fetchone())


async def reserve_reward_receipt(
    db, *, user_id: int, reward_id: str, reward_kind: str,
    quest_policy_version: str, reward_policy_version: str, amount_mora: int,
) -> bool:
    """Reserve one immutable reward identity in the caller's transaction."""
    async with db.execute(
        "INSERT INTO quest_v1_reward_receipts"
        "(user_id,reward_id,reward_kind,quest_policy_version,reward_policy_version,amount_mora) "
        "VALUES (?,?,?,?,?,?) "
        "ON CONFLICT DO NOTHING RETURNING 1",
        (int(user_id), str(reward_id), str(reward_kind), str(quest_policy_version),
         str(reward_policy_version), int(amount_mora)),
    ) as cursor:
        return bool(await cursor.fetchone())


async def increment_metric(db, *, user_id: int, period: str, period_key: str, metric: str) -> None:
    await db.execute(
        "UPDATE quest_v1_assignments SET progress=LEAST(target,progress+1),"
        "completed_at=CASE WHEN progress+1>=target THEN COALESCE(completed_at,CLOCK_TIMESTAMP()) ELSE completed_at END "
        "WHERE user_id=? AND period=? AND period_key=? AND definition_json->>'metric'=?",
        (int(user_id), str(period), str(period_key), str(metric)),
    )
