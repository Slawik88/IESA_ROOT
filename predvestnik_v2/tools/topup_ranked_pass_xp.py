#!/usr/bin/env python3
"""S28a top-up (owner, 06.11.2026): levels of Рейтинг passed under the old star table (60/80/100) get the difference to the
current one (core.league_v1.XP_BY_STARS) in the season pass.  services.league_v1.topup_ranked_xp does the work; every
level has its own receipt, so running it again adds nothing.

    python tools/topup_ranked_pass_xp.py --dsn postgresql://…            # count only: players, levels, experience
    python tools/topup_ranked_pass_xp.py --dsn postgresql://… --apply    # add it

Prints aggregates and player ids only (no names).  The schema is the bot's (predvestnik).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("DATABASE_URL", "postgresql://unused@127.0.0.1/unused")


async def main(dsn: str, apply: bool) -> None:
    import asyncpg
    from infrastructure.pg_adapter import PGAdapter
    from services import league_v1
    conn = await asyncpg.connect(dsn, server_settings={"search_path": "predvestnik,public"}, timeout=15)
    try:
        report = await league_v1.topup_ranked_xp(PGAdapter(conn), apply=apply)
    finally:
        await conn.close()
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.dsn, args.apply))
