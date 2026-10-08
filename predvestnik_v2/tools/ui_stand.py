#!/usr/bin/env python3
"""Local stand that runs the production topology, for looking at the real app and for the UI smoke suite (tools/ui_smoke.py).

What is the same as production: the real FastAPI app behind the real prefix middleware (/predvestnik), uvicorn with lifespan="off", the same start-up
schema step (bot/startup_schema.py), the real routers, services and PostgreSQL. What differs on purpose: the database is the isolated preprod one on loopback,
the player is the synthetic preprod persona (cookie login, no Telegram), payments are off.

The persona can wear ANY look and carry production-sized numbers, which is what a plain stand never showed (a look whose effects reach past the screen edge widened
the page on the owner's phone, but not on a stand with a default persona):

    python tools/ui_stand.py --skin void --tier SSS --rich          # prints the login URL and keeps serving
    python tools/ui_stand.py --skin scarlet_star --tier SSS --rich --name "Очень Длинное Имя Игрока"

Needs a local PostgreSQL named predvestnik_preprod (DATABASE_URL, default postgresql://predvestnik_preprod@127.0.0.1:5433/predvestnik_preprod).
Not used by the automatic test run: it needs a database and, for the smoke suite, Chromium.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PERSONA_ID = 990_000_001
PEER_ID = 990_000_002          # a second player whose public card the persona can open
DEFAULT_DSN = "postgresql://predvestnik_preprod@127.0.0.1:5433/predvestnik_preprod"
RICH = {"mora": 48_210_000, "diamonds": 12_345, "dark_mora": 8_800, "zarniki": 123_456, "essence": 98_765}
POOR = {"mora": 1_200, "diamonds": 3, "dark_mora": 0, "zarniki": 40, "essence": 20}


def _env(port: int, dsn: str) -> Path | None:
    """The preprod guard demands a local .env.test; create a throwaway one when there is none and report it for removal."""
    os.environ.update({"PREDVESTNIK_ENV": "preprod", "DATABASE_URL": dsn, "BOT_TOKEN": os.environ.get("BOT_TOKEN", "123456:stand"), "PORT": str(port),
                       "ROOT_PATH": "/predvestnik", "PREPROD_ALLOWED_TG_IDS": str(PERSONA_ID), "MINIAPP_URL": f"http://127.0.0.1:{port}/predvestnik"})
    os.environ.pop("PREDVESTNIK_DATABASE_URL", None)
    path = ROOT / ".env.test"
    if path.exists():
        return None
    path.write_text("# throwaway file of tools/ui_stand.py (git-ignored)\n", encoding="utf-8")
    return path


GAME_FLAGS = ("content_chests_v1", "game_mafia_v1", "game_minesweeper_v2", "game_rhythm_v2", "economy_player_exchange_v1", "economy_player_exchange_shorts_v1")


async def set_game_flags(dsn: str, enabled: bool) -> None:
    """The owner switches these modules in the admin panel; production may have any mix. The stand can show both extremes."""
    import asyncpg
    from infrastructure.pg_adapter import PGAdapter
    from infrastructure.repositories import system_flags
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("SET search_path TO predvestnik, public")
        db = PGAdapter(conn)
        if enabled:       # the exchange keeps its own tables behind its flag; production creates them when the owner opens it
            from infrastructure.repositories import player_exchange_v1
            await player_exchange_v1.ensure_tables(db)
        for key in GAME_FLAGS:
            await system_flags.set_flag(db, key, enabled)
    finally:
        await conn.close()


async def seed_persona(dsn: str, *, skin: str | None, tier: str, rich: bool, name: str | None, vip: bool, owned: tuple[str, ...]) -> None:
    """Make the synthetic player wear a look and carry numbers. Idempotent: running it again resets the persona."""
    import asyncpg
    from infrastructure.pg_adapter import PGAdapter
    from infrastructure.repositories import marks_v1 as marks_repo
    from infrastructure.repositories import skins_v3 as skins_repo
    from infrastructure.repositories import vip_v2 as vip_repo
    from core.skins_v3_catalog import SKINS

    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("SET search_path TO predvestnik, public")
        db = PGAdapter(conn)
        await skins_repo.ensure_tables(db)
        await marks_repo.ensure_tables(db)
        await vip_repo.ensure_tables(db)
        money = RICH if rich else POOR
        await conn.execute(
            "INSERT INTO users(user_tg_id, user_tg_username, onboarded, ai_hint_shown, user_balance_mora, user_balance_diamonds, user_balance_dark_mora, user_balance_zarniki) "
            "VALUES ($1,$2,TRUE,FALSE,$3,$4,$5,$6) ON CONFLICT (user_tg_id) DO UPDATE SET user_tg_username=EXCLUDED.user_tg_username, onboarded=TRUE, "
            "user_balance_mora=EXCLUDED.user_balance_mora, user_balance_diamonds=EXCLUDED.user_balance_diamonds, user_balance_dark_mora=EXCLUDED.user_balance_dark_mora, "
            "user_balance_zarniki=EXCLUDED.user_balance_zarniki",
            PERSONA_ID, name or "stand_player", money["mora"], money["diamonds"], money["dark_mora"], money["zarniki"])
        await conn.execute("UPDATE users SET tos_accepted_at = COALESCE(tos_accepted_at, NOW()) WHERE user_tg_id=$1", PERSONA_ID)
        await conn.execute("DELETE FROM skins_v3_owned WHERE user_id=$1", PERSONA_ID)
        await conn.execute("DELETE FROM skins_v3_equipped WHERE user_id=$1", PERSONA_ID)
        for sid in dict.fromkeys(([skin] if skin else []) + list(owned)):
            if sid in SKINS:
                await skins_repo.grant(db, PERSONA_ID, sid)
                await skins_repo.set_tier(db, PERSONA_ID, sid, tier if sid == skin else "D")
        if skin in SKINS:
            await skins_repo.set_equipped(db, PERSONA_ID, skin)
        bal = await skins_repo.essence_balance(db, PERSONA_ID)
        if money["essence"] != bal:
            await skins_repo.essence_apply(db, PERSONA_ID, money["essence"] - bal, reason="stand_seed", reference=None, idempotency_key=f"stand-{time.time_ns()}")
        await conn.execute("DELETE FROM vip_subscriptions WHERE user_id=$1", PERSONA_ID)
        if vip:
            await conn.execute("INSERT INTO vip_subscriptions(user_id, tier, expires_at) VALUES ($1,'1m', NOW() + INTERVAL '23 days')", PERSONA_ID)
        for mark in ("developer", "tester"):
            await marks_repo.grant(db, PERSONA_ID, mark, PERSONA_ID, "stand")
        await conn.execute("INSERT INTO users(user_tg_id, user_tg_username, onboarded, ai_hint_shown) VALUES ($1,'stand_peer',TRUE,FALSE) "
                           "ON CONFLICT (user_tg_id) DO UPDATE SET onboarded=TRUE", PEER_ID)
        await conn.execute("DELETE FROM skins_v3_owned WHERE user_id=$1", PEER_ID)
        await conn.execute("DELETE FROM skins_v3_equipped WHERE user_id=$1", PEER_ID)
        peer_look = next((s for s in ("frost", "lotus_pond") if s in SKINS), None)
        if peer_look:
            await skins_repo.grant(db, PEER_ID, peer_look)
            await skins_repo.set_tier(db, PEER_ID, peer_look, "SS")
            await skins_repo.set_equipped(db, PEER_ID, peer_look)
    finally:
        await conn.close()


class Stand:
    """The production topology on a loopback port, served from a background thread. Use as a context manager; `url` and `ticket` open the app logged in."""

    def __init__(self, port: int = 8403, dsn: str = DEFAULT_DSN, **persona):
        self.port, self.dsn, self.persona = port, dsn, persona
        self._created_env: Path | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._error: BaseException | None = None
        self._stop: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}/predvestnik"

    @property
    def ticket(self) -> str:
        from FastAPI.auth import create_preprod_browser_ticket
        return create_preprod_browser_ticket(PERSONA_ID)

    @property
    def url(self) -> str:
        return f"{self.base}/__preprod/activate?ticket={self.ticket}"

    def _serve(self) -> None:
        async def main() -> None:
            import uvicorn
            from FastAPI.main import app
            from FastAPI.prefix import strip_prefix_middleware
            from bot.core.database import init_db
            from bot.startup_schema import ensure_runtime_schema
            from infrastructure.database import create_pool
            pool = await create_pool()
            await init_db()
            await ensure_runtime_schema(pool)
            await seed_persona(self.dsn, **{"skin": None, "tier": "D", "rich": True, "name": None, "vip": True, "owned": (), **self.persona})
            server = uvicorn.Server(uvicorn.Config(strip_prefix_middleware(app, "/predvestnik"), host="127.0.0.1", port=self.port, log_level="warning", lifespan="off"))
            self._stop = asyncio.Event(); self._loop = asyncio.get_running_loop()
            task = asyncio.create_task(server.serve())
            while not server.started and not task.done():
                await asyncio.sleep(.05)
            self._ready.set()
            await self._stop.wait()
            server.should_exit = True
            await task
        try:
            asyncio.run(main())
        except BaseException as exc:      # noqa: BLE001 - reported to the caller through start()
            self._error = exc
            self._ready.set()

    def start(self) -> "Stand":
        self._created_env = _env(self.port, self.dsn)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        if not self._ready.wait(120) or self._error:
            raise RuntimeError(f"stand did not start: {self._error!r}")
        return self

    def stop(self) -> None:
        if self._loop and self._stop:
            self._loop.call_soon_threadsafe(self._stop.set)
        if self._thread:
            self._thread.join(15)
        if self._created_env and self._created_env.exists():
            self._created_env.unlink()

    def __enter__(self) -> "Stand":
        return self.start()

    def __exit__(self, *_exc) -> None:
        self.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8403)
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL", DEFAULT_DSN))
    parser.add_argument("--skin", help="skin id to wear, e.g. void, scarlet_star, forest")
    parser.add_argument("--tier", default="SSS", help="tier of the worn skin (D…SSS)")
    parser.add_argument("--rich", action="store_true", help="production-sized balances (default: a newcomer)")
    parser.add_argument("--no-vip", action="store_true")
    parser.add_argument("--name", help="nickname of the persona")
    parser.add_argument("--flags", choices=("on", "off", "keep"), default="keep", help="switch the game/economy modules (chests, games, exchange) on or off")
    parser.add_argument("--own", default="", help="comma separated extra skin ids to own at tier D")
    args = parser.parse_args()
    if args.flags != "keep":
        asyncio.run(set_game_flags(args.dsn, args.flags == "on"))
    with Stand(args.port, args.dsn, skin=args.skin, tier=args.tier, rich=args.rich, vip=not args.no_vip, name=args.name,
               owned=tuple(x for x in args.own.split(",") if x)) as stand:
        print(f"Stand is up. Open this URL once (it logs the persona in, valid 2 minutes):\n  {stand.url}\nCtrl+C to stop.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
