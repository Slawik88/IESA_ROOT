"""Dedicated loopback v2 visual stand. Never reads production DSNs or secrets."""

import asyncio
import os
import time

from ui_stand import PERSONA_ID, Stand

DSN = "postgresql://predvestnik_preprod@127.0.0.1:55438/predvestnik_preprod"
os.environ["COIN_MARKET_V2_SECRET"] = (
    "visual-stand-only-market-secret-not-for-any-production-use"
)


async def seed():
    import asyncpg
    from core.coin_market_v2 import RULES_VERSION
    from infrastructure.pg_adapter import PGAdapter
    from infrastructure.repositories import coin_market_v2 as repo
    from infrastructure.repositories import system_flags
    from services import coin_market_v2 as service

    conn = await asyncpg.connect(DSN)
    try:
        await conn.execute("SET search_path TO predvestnik,public")
        # Fresh visual fixture lacks the separately deployed family lifecycle
        # column already read by the profile. No real families live here.
        await conn.execute(
            "ALTER TABLE marriages ADD COLUMN IF NOT EXISTS ended_at TIMESTAMPTZ"
        )
        await conn.execute(
            "UPDATE users SET tos_accepted_at=NOW() WHERE user_tg_id=$1", PERSONA_ID
        )
        db = PGAdapter(conn)
        await repo.ensure_tables(db)
        _, key = service.configuration()
        await repo.bootstrap(
            db,
            service.SYSTEM_COINS,
            key,
            RULES_VERSION,
            await repo.current_tick(db) - 576,
            source="isolated_visual_fixture", issuance_authorization="disposable_visual_fixture_only",
        )
        await service.maintenance(db)
        await system_flags.set_flag(db, "coin_market_v2", True)
        await system_flags.set_flag(db, "coin_market_v2_shorts", True)
        await conn.execute(
            "UPDATE users SET user_balance_mora=5000,user_balance_zarniki=10000 WHERE user_tg_id=$1",
            PERSONA_ID,
        )
    finally:
        await conn.close()


if __name__ == "__main__":
    with Stand(8423, DSN, rich=False, trail="none", season_pass="none") as stand:
        from FastAPI import main
        from FastAPI.static_assets import prepare

        # Only this test process moves the existing preprod persona UI port.
        # Production sources and authentication checks are unchanged.
        app_js = main._STORE["app.js"]
        main._STORE["app.js"] = prepare(app_js.body.decode("utf-8").replace(
            "location.port === '8403'", "location.port === '8423'"
        ), app_js.media_type)
        asyncio.run(seed())
        asyncio.run_coroutine_threadsafe(main._run_coin_market_v2(), stand._loop)
        print("COIN_MARKET_V2_STAND " + stand.url, flush=True)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
