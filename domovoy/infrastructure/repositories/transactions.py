"""Общий журнал денег и атомарное применение проверенного импорта."""
from infrastructure.db import db, now_utc


async def all_rows(house_id: int) -> list:
    async with db.acquire() as conn:
        return await conn.fetch(
            """
            SELECT 'expense' AS kind, e.id AS id, e.tg_id, m.display_name,
                   e.spent_on AS date, SUBSTR(e.spent_on, 1, 7) AS month,
                   e.amount_kop, c.name AS category, e.mode, 'confirmed' AS status,
                   e.reimbursed, e.description, i.source_key
            FROM expenses e
            LEFT JOIN memberships m ON m.house_id = e.house_id AND m.tg_id = e.tg_id
            LEFT JOIN categories c ON c.id = e.category_id
            LEFT JOIN money_import_items i ON i.house_id = e.house_id AND i.kind = 'expense' AND i.target_id = e.id
            WHERE e.house_id = ?
            UNION ALL
            SELECT 'contribution' AS kind, c.id AS id, c.tg_id, m.display_name,
                   c.paid_on AS date, c.month, c.amount_kop, '' AS category, '' AS mode,
                   c.status, 0 AS reimbursed, '' AS description, i.source_key
            FROM contributions c
            LEFT JOIN memberships m ON m.house_id = c.house_id AND m.tg_id = c.tg_id
            LEFT JOIN money_import_items i ON i.house_id = c.house_id
                 AND i.kind = 'contribution' AND i.target_id = c.id
            WHERE c.house_id = ?
            ORDER BY date DESC, kind, id DESC
            """, house_id, house_id,
        )


async def imported_keys(house_id: int) -> dict[str, str]:
    async with db.acquire() as conn:
        rows = await conn.fetch(
            "SELECT source_key, fingerprint FROM money_import_items WHERE house_id = ?", house_id,
        )
    return {row["source_key"]: row["fingerprint"] for row in rows}


async def apply_import(house_id: int, actor: int, rows: list[dict]) -> tuple[int, int]:
    added = skipped = 0
    async with db.transaction() as conn:
        for row in rows:
            claimed = await conn.execute(
                """INSERT INTO money_import_items
                   (house_id, source_key, fingerprint, imported_by, imported_at, kind)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT (house_id, source_key) DO NOTHING""",
                house_id, row["source_key"], row["fingerprint"], actor, now_utc(), row["kind"],
            )
            if not claimed:
                previous = await conn.fetchrow(
                    "SELECT fingerprint FROM money_import_items WHERE house_id = ? AND source_key = ?",
                    house_id, row["source_key"],
                )
                if previous["fingerprint"] != row["fingerprint"]:
                    raise ValueError("Файл конфликтует с ранее загруженной операцией")
                skipped += 1
                continue
            if row["kind"] == "expense":
                category_id = None
                if row["category"]:
                    await conn.execute(
                        "INSERT INTO categories (house_id, name, is_default, sort) VALUES (?, ?, 0, 100) "
                        "ON CONFLICT (house_id, name) DO NOTHING", house_id, row["category"],
                    )
                    category = await conn.fetchrow(
                        "SELECT id FROM categories WHERE house_id = ? AND name = ?", house_id, row["category"],
                    )
                    category_id = category["id"]
                target_id = await conn.insert(
                    """INSERT INTO expenses
                       (house_id, tg_id, amount_kop, category_id, spent_on, mode, reimbursed, description, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    house_id, row["member_tg_id"], row["amount_kop"], category_id, row["date"],
                    row["mode"], row["reimbursed"], row["description"], now_utc(),
                )
            else:
                resolved = row["status"] != "declared"
                target_id = await conn.insert(
                    """INSERT INTO contributions
                       (house_id, tg_id, amount_kop, month, status, paid_on, declared_at, confirmed_by, confirmed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    house_id, row["member_tg_id"], row["amount_kop"], row["month"], row["status"],
                    row["date"], now_utc(), actor if resolved else None, now_utc() if resolved else None,
                )
            await conn.execute(
                "UPDATE money_import_items SET target_id = ? WHERE house_id = ? AND source_key = ?",
                target_id, house_id, row["source_key"],
            )
            added += 1
    return added, skipped
