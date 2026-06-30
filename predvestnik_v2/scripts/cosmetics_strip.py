#!/usr/bin/env python3
"""
scripts/cosmetics_strip.py — Забрать магазинную косметику у игроков (без рефанда).
Рефанд уже сделан вручную. Скрипт только удаляет предметы из инвентаря.

  python predvestnik_v2/scripts/cosmetics_strip.py --dry-run
  python predvestnik_v2/scripts/cosmetics_strip.py
"""
import asyncio
import argparse
import os
import sys
from datetime import datetime

try:
    import asyncpg
    from dotenv import load_dotenv
except ImportError:
    print("pip install asyncpg python-dotenv")
    sys.exit(1)

load_dotenv()

REFUND_CUTOFF = datetime(2026, 6, 30, 23, 59, 59)

SHOP_IDS = [
    "glow_silver", "glow_gold", "glow_crimson", "glow_ember",
    "frame_bronze", "frame_neon", "frame_abyss", "frame_iron",
    "title_wanderer", "title_patron",
    "halo_glow", "halo_pulse", "halo_runic",
    "pbg_carbon", "pbg_nebula", "pbg_abyss", "pbg_forest", "pbg_ocean",
    "pbg_ember", "pbg_galaxy", "pbg_dusk",
    "cfx_sparks", "cfx_snow", "cfx_petals", "cfx_stars",
]


async def run(dry_run: bool) -> None:
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    prefix = "[DRY RUN] " if dry_run else ""

    rows = await conn.fetch(
        """
        SELECT uc.user_id, uc.cosmetic_id, uc.acquired_at::timestamp AS acquired_at,
               u.user_tg_username
        FROM predvestnik.user_cosmetics uc
        LEFT JOIN predvestnik.users u ON u.user_tg_id = uc.user_id
        WHERE uc.cosmetic_id = ANY($1::text[])
          AND uc.acquired_at::timestamp <= $2
        ORDER BY uc.user_id, uc.cosmetic_id
        """,
        SHOP_IDS, REFUND_CUTOFF,
    )

    if not rows:
        print("Нет записей для удаления.")
        await conn.close()
        return

    print(f"{prefix}Найдено: {len(rows)} записей")
    print("=" * 60)
    for r in rows:
        print(f"  @{r['user_tg_username'] or r['user_id']:<20} | {r['cosmetic_id']}")
    print("=" * 60)

    if not dry_run:
        for r in rows:
            await conn.execute(
                "DELETE FROM predvestnik.user_cosmetics WHERE user_id = $1 AND cosmetic_id = $2",
                r["user_id"], r["cosmetic_id"],
            )
            await conn.execute(
                "DELETE FROM predvestnik.user_cosmetic_loadout WHERE user_id = $1 AND cosmetic_id = $2",
                r["user_id"], r["cosmetic_id"],
            )
        print(f"Удалено: {len(rows)} записей.")
    else:
        print(f"{prefix}Ничего не изменено.")

    await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.dry_run))
