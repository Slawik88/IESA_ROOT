"""
fix_double_active_pets.py — одноразовый скрипт.
Находит всех юзеров с 2+ активными питомцами и переводит
лишних (все кроме первого, самого старого) на склад.

Запускать: python fix_double_active_pets.py
"""
import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from infrastructure.database import create_pool, get_pool
from infrastructure.pg_adapter import PGAdapter


async def main():
    await create_pool()
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)

        # Find users with 2+ active pets
        async with db.execute(
            "SELECT owner_id, COUNT(*) AS cnt "
            "FROM pets WHERE placement = 'active' "
            "GROUP BY owner_id HAVING COUNT(*) > 1"
        ) as c:
            offenders = await c.fetchall()

        if not offenders:
            print("✅ Нет юзеров с 2+ активными питомцами.")
            return

        print(f"⚠️  Найдено {len(offenders)} юзер(ов) с избытком активных питомцев:")
        total_fixed = 0

        for row in offenders:
            owner_id = row["owner_id"]
            cnt = row["cnt"]

            # Get all active pets ordered by id (oldest first = keep, rest → storage)
            async with db.execute(
                "SELECT id, name, species_id FROM pets "
                "WHERE owner_id = ? AND placement = 'active' "
                "ORDER BY id ASC",
                (owner_id,),
            ) as c2:
                pets = await c2.fetchall()

            keep = pets[0]
            demote = pets[1:]

            print(f"  user {owner_id}: {cnt} активных → держим '{keep['name']}' (id={keep['id']})")
            for p in demote:
                await db.execute(
                    "UPDATE pets SET placement = 'storage' WHERE id = ?",
                    (p["id"],),
                )
                print(f"    📦 Переведён на склад: '{p['name']}' (id={p['id']}, species={p['species_id']})")
                total_fixed += 1

        await db.commit()
        print(f"\n✅ Готово. {total_fixed} лишних активных питомец(цев) переведено на склад.")


if __name__ == "__main__":
    asyncio.run(main())
