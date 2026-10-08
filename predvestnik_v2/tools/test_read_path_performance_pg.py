"""Real PostgreSQL proof of cheap reads, cold races and economic schema guards."""
import argparse
import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import asyncpg
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import quests_v1, achievements_v1, public_profiles_v1 as refs
from FastAPI.routers import profile


class CountDB(PGAdapter):
    def __init__(self, connection):
        super().__init__(connection)
        self.sql = []

    def execute(self, sql, *args, **kwargs):
        self.sql.append(sql)
        return super().execute(sql, *args, **kwargs)


def local_dsn(value):
    if urlparse(value).hostname not in ('localhost', '127.0.0.1', '::1'):
        raise argparse.ArgumentTypeError("loopback only")
    return value


async def run(dsn):
    a, b = await asyncio.gather(asyncpg.connect(dsn), asyncpg.connect(dsn))
    schema = f'read_perf_{os.getpid()}'
    try:
        await a.execute(f'CREATE SCHEMA "{schema}"')
        for connection in (a, b):
            await connection.execute(f'SET search_path TO "{schema}"')
        db, other = CountDB(a), CountDB(b)
        for repo in (quests_v1, achievements_v1):
            await asyncio.gather(repo.ensure_read_schema(db), repo.ensure_read_schema(other))
            db.sql.clear()
            await repo.ensure_read_schema(db)
            assert len(db.sql) == 1 and 'CREATE ' not in db.sql[0], db.sql
        await a.execute('ALTER TABLE quest_v1_reward_receipts DISABLE TRIGGER quest_v1_reward_receipts_append_only')
        await quests_v1.ensure_read_schema(db)
        enabled = await a.fetchval("SELECT tgenabled::text FROM pg_trigger WHERE tgname='quest_v1_reward_receipts_append_only' AND tgrelid='quest_v1_reward_receipts'::regclass")
        assert enabled == 'O'
        await a.execute("INSERT INTO quest_v1_reward_receipts(user_id,reward_id) VALUES(1,'proof')")
        try:
            await a.execute("DELETE FROM quest_v1_reward_receipts WHERE user_id=1")
        except asyncpg.RaiseError:
            pass
        else:
            raise AssertionError('append-only guard missing')

        # Readiness never leaks through rollback or a different schema.
        tx = a.transaction()
        await tx.start()
        await a.execute(f'CREATE SCHEMA "{schema}_rollback"')
        await a.execute(f'SET LOCAL search_path TO "{schema}_rollback"')
        await achievements_v1.ensure_read_schema(db)
        await tx.rollback()
        await a.execute(f'CREATE SCHEMA "{schema}_rollback"')
        await a.execute(f'SET search_path TO "{schema}_rollback"')
        await achievements_v1.ensure_read_schema(db)
        assert await a.fetchval("SELECT to_regclass('achievement_v1_progress')")
        await a.execute(f'SET search_path TO "{schema}"')

        ids = list(range(1, 31))
        first, second = await asyncio.gather(refs.ensure_references(db, ids), refs.ensure_references(other, ids))
        assert first == second and len(set(first.values())) == len(ids)
        db.sql.clear()
        assert await refs.ensure_references(db, ids) == first
        assert len(db.sql) == 2, len(db.sql)
        original = refs.secrets.token_urlsafe
        calls = 0
        def collision_then_unique(size):
            nonlocal calls
            calls += 1
            return first[1] if calls == 1 else original(size)
        refs.secrets.token_urlsafe = collision_then_unique
        try:
            assert (await refs.ensure_references(db, [99]))[99] not in first.values()
        finally:
            refs.secrets.token_urlsafe = original

        await a.execute("""CREATE TABLE users(
            user_tg_id bigint PRIMARY KEY,user_balance_mora double precision,
            user_balance_diamonds double precision,user_balance_dark_mora double precision,
            user_balance_zarniki double precision,account_xp bigint)""")
        await a.execute("INSERT INTO users VALUES(7,120,3.5,4,200,100)")
        db.sql.clear()
        balances = await profile.my_balances(db=db, user={'id': 7})
        assert len(db.sql) == 1 and balances['diamonds'] == 3.5 and balances['zarniki'] == 200
        assert 'cosmetics' not in balances and 'account_level' in balances

        profile._AVATAR_CACHE.clear()
        fetch = profile._fetch_tg_avatar
        network_calls = 0
        async def no_photo(uid):
            nonlocal network_calls
            network_calls += 1
            await asyncio.sleep(.01)
            return None
        profile._fetch_tg_avatar = no_photo
        try:
            assert await asyncio.gather(profile._load_avatar_cached(7), profile._load_avatar_cached(7)) == [None, None]
            await profile._load_avatar_cached(7)
            assert network_calls == 1
        finally:
            profile._fetch_tg_avatar = fetch
        print('OK: hot schema reads 1 SQL each; concurrent/rollback/disabled-trigger recovery; refs 2 SQL for 30 users; balances 1 SQL; avatar singleflight')
    finally:
        await a.execute('SET search_path TO public')
        await b.execute('SET search_path TO public')
        await a.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await a.execute(f'DROP SCHEMA IF EXISTS "{schema}_rollback" CASCADE')
        await a.close()
        await b.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dsn', required=True, type=local_dsn)
    asyncio.run(run(parser.parse_args().dsn))
