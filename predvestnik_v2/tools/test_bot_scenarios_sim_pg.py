#!/usr/bin/env python3
"""Whole-bot scenarios on the Telegram simulator (tools/mafia_sim): the real Dispatcher, routers and middlewares against an
in-memory Telegram and a throw-away local PostgreSQL.  Covers /start and deep links, the everyday commands in a DM and in a
group, buttons, Telegram Stars payments, the bot joining and leaving chats, forum topics, Telegram Business updates and the
failures that hit real bots (blocked DM, flood limit).

    BOT_TOKEN=1:x PYTHONPATH=. python tools/test_bot_scenarios_sim_pg.py --dsn postgresql://predvestnik_preprod@127.0.0.1:5433/predvestnik_preprod
    ... --only start_deeplinks,stars_purchase_success     # some scenarios
    ... --list                                            # scenario names
    ... --transcript before.json                          # also save what the bot did, per scenario

Every scenario also gets a fingerprint of everything the bot sent (texts, buttons, targets, answers to Telegram).  A library bump
or a bot change must leave the fingerprints of the untouched scenarios as they were.  Some answers depend on the player id (daily
quests, the article of the day), so compare runs made with the same ids, each on a freshly bootstrapped database:

    ... --fixed-ids --transcript on-3.22.json     (old library, fresh database)
    ... --fixed-ids --transcript on-3.31.json     (new library, fresh database)
    python tools/test_bot_scenarios_sim_pg.py --compare on-3.22.json on-3.31.json
"""
from __future__ import annotations

import argparse
import asyncio
import difflib
import itertools
import json
import os
import random
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _parse() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--only", default="")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--transcript", default="")
    parser.add_argument("--compare", nargs=2, metavar=("A", "B"))
    parser.add_argument("--fixed-ids", action="store_true", help="always use the same player and chat ids (fresh database only)")
    return parser.parse_args()


def compare(first: str, second: str) -> int:
    a, b = (json.load(open(path, encoding="utf-8")) for path in (first, second))
    names = [n for n in a["scenarios"] if n in b["scenarios"]]
    print(f"aiogram {a['aiogram']} vs {b['aiogram']}: {len(names)} scenarios in common")
    failed = [f"{n} ({label})" for label, side in (("first", a), ("second", b)) for n in names if not side["scenarios"][n].get("passed", True)]
    for item in failed:
        print(f"  FAILED {item}")
    different = [n for n in names if a["scenarios"][n]["fingerprint"] != b["scenarios"][n]["fingerprint"]]   # "random" == "random"
    for name in different:
        print(f"  DIFFERENT {name}")
        left, right = (x["scenarios"][name]["calls"].splitlines() for x in (a, b))
        for line in list(difflib.unified_diff(left, right, "first", "second", lineterm="", n=1))[:30]:
            print("    " + line)
    only = sorted(set(a["scenarios"]) ^ set(b["scenarios"]))
    if only:
        print(f"  present in only one file: {only}")
    print("IDENTICAL" if not different and not only and not failed else f"{len(different)} scenario(s) differ, {len(failed)} failed")
    return 1 if different or only or failed else 0


async def _prepare(args: argparse.Namespace):
    """Open the harness and give this run its own player/chat ids (None when --fixed-ids meets a used database)."""
    from tools.mafia_sim.harness import Harness

    harness = await Harness().open()
    # ids no earlier run used, so leftovers in a shared database cannot change what a scenario sees
    stamp = 1 if args.fixed_ids else (time.time_ns() // 1_000_000) % 10_000_000   # a run uses well under 1000 users and chats
    if args.fixed_ids:
        used = await harness.sql("SELECT count(*) AS n FROM predvestnik.users WHERE user_tg_id BETWEEN 990000000000 AND 990999999999")
        if used[0]["n"]:
            await harness.close()
            return None
    harness._users = itertools.count(990_000_000_000 + stamp * 1000)
    harness._chats = itertools.count(10_000 + stamp * 1000)
    harness.run_tag = f"{stamp:07d}"   # makes payment receipts of this run unique (a charge id can be used only once, ever)
    return harness


async def _run_one(harness, name: str) -> tuple[bool, dict]:
    """Run one scenario; returns (passed, {fingerprint, calls}).  Volatile scenarios are checked but not fingerprinted."""
    from tools.mafia_sim.digest import calls_since, canonical, fingerprint
    from tools.mafia_sim.registry import BOT_SCENARIOS, VOLATILE

    random.seed(name)
    for per_scenario in (harness.world.invoices, harness.world.precheckout_answers, harness.world.answers):
        per_scenario.clear()
    first_call, first_user, first_chat = len(harness.world.calls), len(harness.users_made), len(harness.chats)
    started = time.monotonic()
    passed = True
    try:
        await BOT_SCENARIOS[name](harness)
    except Exception:  # noqa: BLE001 - report and continue with the next scenario
        passed = False
        print(f"  FAIL {name}" + chr(10) + traceback.format_exc(limit=6))
    labels = {u.id: f"user{i + 1}" for i, u in enumerate(harness.users_made[first_user:])}
    labels.update({c: f"chat{i + 1}" for i, c in enumerate(harness.chats[first_chat:])})
    text = canonical(calls_since(harness.world, first_call), labels)
    saved = {"passed": passed, "fingerprint": "random" if name in VOLATILE else fingerprint(text), "calls": "" if name in VOLATILE else text}
    print(f"  {'ok  ' if passed else 'FAIL'} {name} ({time.monotonic() - started:.1f}s) fingerprint {saved['fingerprint']}")
    return passed, saved


async def run(args: argparse.Namespace) -> int:
    from tools.mafia_sim import bot_scenarios  # noqa: F401  (imports register every scenario)
    from tools.mafia_sim.registry import BOT_SCENARIOS
    import aiogram

    wanted = [name for name in args.only.split(",") if name] or list(BOT_SCENARIOS)
    unknown = [name for name in wanted if name not in BOT_SCENARIOS]
    if unknown:
        print(f"unknown scenarios: {unknown}")
        return 2
    harness = await _prepare(args)
    if harness is None:
        print("--fixed-ids needs a freshly bootstrapped database: this one already holds simulator players")
        return 2
    failed: list[str] = []
    saved: dict[str, dict] = {}
    try:
        for name in wanted:
            passed, saved[name] = await _run_one(harness, name)
            if not passed:
                failed.append(name)
    finally:
        await harness.close()
    if args.transcript:
        with open(args.transcript, "w", encoding="utf-8") as out:
            json.dump({"aiogram": aiogram.__version__, "scenarios": saved}, out, ensure_ascii=False)
    print(f"bot scenarios (aiogram {aiogram.__version__}): {len(wanted) - len(failed)}/{len(wanted)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    arguments = _parse()
    if arguments.compare:
        raise SystemExit(compare(*arguments.compare))
    if arguments.list:
        from tools.mafia_sim import bot_scenarios  # noqa: F401
        from tools.mafia_sim.registry import BOT_SCENARIOS
        print("\n".join(BOT_SCENARIOS))
        raise SystemExit(0)
    os.environ.setdefault("BOT_TOKEN", "123456:SIM-TOKEN")
    if not arguments.dsn:
        raise SystemExit("pass --dsn or set DATABASE_URL (loopback predvestnik_preprod only)")
    from tools.mafia_sim.harness import assert_dev_dsn
    assert_dev_dsn(arguments.dsn)
    os.environ["DATABASE_URL"] = arguments.dsn
    raise SystemExit(asyncio.run(run(arguments)))
