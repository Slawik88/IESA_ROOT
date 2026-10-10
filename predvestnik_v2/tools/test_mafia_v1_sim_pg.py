#!/usr/bin/env python3
"""Full chat-Mafia simulation on a throw-away local PostgreSQL: no real group, no real players.

Real routers and middlewares run against an in-memory Telegram (tools/mafia_sim).  Usage:

    PYTHONPATH=. python tools/test_mafia_v1_sim_pg.py --dsn postgresql://predvestnik_preprod@127.0.0.1:55432/predvestnik_preprod
    ... --only lobby_basics,town_wins      # run some scenarios
    ... --list                             # show scenario names
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _parse() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--only", default="")
    parser.add_argument("--list", action="store_true")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    from tools.mafia_sim import scenarios  # noqa: F401  (imports register every scenario)
    from tools.mafia_sim.harness import Harness
    from tools.mafia_sim.registry import SCENARIOS

    wanted = [name for name in args.only.split(",") if name] or list(SCENARIOS)
    unknown = [name for name in wanted if name not in SCENARIOS]
    if unknown:
        print(f"unknown scenarios: {unknown}")
        return 2
    harness = await Harness().open()
    failed: list[str] = []
    try:
        for name in wanted:
            started = time.monotonic()
            try:
                await SCENARIOS[name](harness)
                print(f"  ok   {name} ({time.monotonic() - started:.1f}s)")
            except Exception:  # noqa: BLE001 - report and continue with the next scenario
                failed.append(name)
                print(f"  FAIL {name}\n{traceback.format_exc(limit=6)}")
    finally:
        await harness.close()
    print(f"mafia_v1 simulation: {len(wanted) - len(failed)}/{len(wanted)} scenarios passed")
    return 1 if failed else 0


if __name__ == "__main__":
    arguments = _parse()
    if arguments.list:
        from tools.mafia_sim import scenarios  # noqa: F401
        from tools.mafia_sim.registry import SCENARIOS
        print("\n".join(SCENARIOS))
        raise SystemExit(0)
    os.environ.setdefault("BOT_TOKEN", "123456:SIM-TOKEN")
    if not arguments.dsn:
        raise SystemExit("pass --dsn or set DATABASE_URL (loopback predvestnik_preprod only)")
    from tools.mafia_sim.harness import assert_dev_dsn
    assert_dev_dsn(arguments.dsn)
    os.environ["DATABASE_URL"] = arguments.dsn
    raise SystemExit(asyncio.run(run(arguments)))
