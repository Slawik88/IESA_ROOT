#!/usr/bin/env python3
"""
scripts/skins_v3_refund_plan.py — READ-ONLY plan of the Skins V3 launch refund.

Shows who will get Zarniki back for the retired skins and cosmetics and how much, exactly as
services/skins_v3_migration.py will compute it at launch. Nothing is written: the connection is opened
in a READ ONLY transaction, no tables are created, nothing is sent.

  python predvestnik_v2/scripts/skins_v3_refund_plan.py              # totals + top 20 players
  python predvestnik_v2/scripts/skins_v3_refund_plan.py --csv plan.csv   # full list (user_id, username, refund)
  python predvestnik_v2/scripts/skins_v3_refund_plan.py --summary-only   # totals only (safe to paste anywhere)

Needs DATABASE_URL (from the environment or .env). The connection string is never printed.
"""
import argparse
import asyncio
import csv
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

try:
    import asyncpg
    from dotenv import load_dotenv
except ImportError:
    print("ERROR: pip install asyncpg python-dotenv")
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from infrastructure.pg_adapter import PGAdapter  # noqa: E402
from services import skins_v3_migration as migration  # noqa: E402

load_dotenv()


async def main(csv_path: str | None, summary_only: bool) -> None:
    dsn = os.getenv("DATABASE_URL", "")
    if not dsn:
        print("ERROR: DATABASE_URL is not set", file=sys.stderr)
        sys.exit(1)
    conn = await asyncpg.connect(dsn, server_settings={"search_path": "predvestnik,public"})
    try:
        async with conn.transaction(readonly=True):
            db = PGAdapter(conn)
            plans = await migration.build_plan(db)
            names: dict[int, str] = {}
            if plans:
                rows = await conn.fetch("SELECT user_tg_id, user_tg_username FROM users WHERE user_tg_id = ANY($1::bigint[])", [p.user_id for p in plans])
                names = {int(r["user_tg_id"]): r["user_tg_username"] or "" for r in rows}
    finally:
        await conn.close()
    paying = [p for p in plans if p.refund > 0]
    print(f"Players with old skins or cosmetics to archive: {len(plans)}")
    print(f"Players who get Zarniki back:                  {len(paying)}")
    print(f"Total refund:                                  {sum(p.refund for p in paying)} Zarniki")
    if paying:
        print(f"Largest single refund:                         {max(p.refund for p in paying)} Zarniki")
    if not summary_only:
        print("\nTop 20 refunds:")
        for p in sorted(paying, key=lambda x: -x.refund)[:20]:
            print(f"  id={p.user_id:<12} @{names.get(p.user_id, ''):<24} {p.refund}")
    if csv_path:
        with open(csv_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["user_id", "username", "refund_zarniki", "has_old_ownership"])
            for p in plans:
                writer.writerow([p.user_id, names.get(p.user_id, ""), p.refund, int(p.has_old_ownership)])
        print(f"\nFull list written to {csv_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read-only plan of the Skins V3 launch refund")
    parser.add_argument("--csv", help="write the full per-player list to this CSV file")
    parser.add_argument("--summary-only", action="store_true", help="print totals only")
    args = parser.parse_args()
    asyncio.run(main(args.csv, args.summary_only))
