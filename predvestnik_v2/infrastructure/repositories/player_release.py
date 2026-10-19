"""Atomic one-time flags; later operator pauses are never overwritten."""
import json

async def ensure_tables(db):
    await db.connection.execute("CREATE TABLE IF NOT EXISTS player_release_receipts(id TEXT PRIMARY KEY,flags JSONB NOT NULL,applied_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp())")

async def apply_once(db, release_id, flags):
    async with db.connection.transaction():
        await db.connection.execute("SELECT pg_advisory_xact_lock(hashtextextended('player-release',0))")
        if await db.connection.fetchval('SELECT 1 FROM player_release_receipts WHERE id=$1',release_id):return False
        found=await db.connection.fetch('SELECT key FROM system_flags WHERE key=ANY($1::text[]) FOR UPDATE',list(flags))
        if {x['key'] for x in found}!=set(flags):raise RuntimeError('Player release flags missing')
        await db.connection.execute('UPDATE system_flags SET enabled=1 WHERE key=ANY($1::text[])',list(flags))
        await db.connection.execute('INSERT INTO player_release_receipts(id,flags) VALUES($1,$2::jsonb)',release_id,json.dumps(list(flags)))
        return True

async def required_storage(db):
    names=['season_pass_progress','season_pass_days','season_pass_receipts',
      'pet_v2_state','pet_v2_runs','rhythm_v2_runs','minesweeper_v2_runs','coin_market_v2_orders']
    return not await db.connection.fetchval('SELECT EXISTS(SELECT 1 FROM unnest($1::text[]) n WHERE to_regclass(n) IS NULL)',names)

async def status(db, flags):
    ready=await db.connection.fetchval("SELECT to_regclass('player_release_receipts') IS NOT NULL")
    applied=[] if not ready else [x['id'] for x in await db.connection.fetch('SELECT id FROM player_release_receipts ORDER BY applied_at')]
    rows=await db.connection.fetch('SELECT key,enabled FROM system_flags WHERE key=ANY($1::text[])',list(flags))
    return {'applied':applied,'features':{x['key']:bool(x['enabled']) for x in rows}}


async def applied(db, release_id):
    return bool(await db.connection.fetchval('SELECT 1 FROM player_release_receipts WHERE id=$1',release_id))
