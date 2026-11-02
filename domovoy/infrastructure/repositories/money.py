"""
infrastructure/repositories/money.py — категории, взносы, траты, фото-чеки.
Деньги — целые копейки. Баланс считает сервис, здесь только данные.
"""
import json

from infrastructure.db import db, now_utc


# ── Категории ────────────────────────────────────────────────────────────────

async def seed_default_categories(house_id: int, names: tuple[str, ...]) -> None:
    async with db.acquire() as conn:
        for sort, name in enumerate(names):
            await conn.execute(
                """
                INSERT INTO categories (house_id, name, is_default, sort)
                VALUES (?, ?, 1, ?)
                ON CONFLICT (house_id, name) DO NOTHING
                """,
                house_id, name, sort,
            )


async def list_categories(house_id: int) -> list:
    async with db.acquire() as conn:
        return await conn.fetch(
            "SELECT id, house_id, name, is_default, sort FROM categories WHERE house_id = ? ORDER BY sort, id",
            house_id,
        )


async def get_category(category_id: int):
    async with db.acquire() as conn:
        return await conn.fetchrow(
            "SELECT id, house_id, name, is_default, sort FROM categories WHERE id = ?", category_id
        )


async def add_category(house_id: int, name: str) -> int:
    async with db.transaction() as conn:
        suffix = " FOR UPDATE" if db.is_postgres else ""
        await conn.fetchrow("SELECT id FROM houses WHERE id = ?" + suffix, house_id)
        existing = await conn.fetch("SELECT id, name FROM categories WHERE house_id = ?", house_id)
        match = next((category for category in existing if category["name"].casefold() == name.casefold()), None)
        if match:
            return match["id"]
        return await conn.insert(
            "INSERT INTO categories (house_id, name, is_default, sort) VALUES (?, ?, 0, 100)",
            house_id, name,
        )


async def delete_category(category_id: int) -> bool:
    async with db.acquire() as conn:
        rowcount = await conn.execute("DELETE FROM categories WHERE id = ?", category_id)
        return rowcount > 0


async def category_expense_count(category_id: int) -> int:
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) AS n FROM expenses WHERE category_id = ?", category_id
        )
        return int(row["n"]) if row else 0


# ── Взносы ───────────────────────────────────────────────────────────────────

async def declare_contribution(
    house_id: int, tg_id: int, amount_kop: int, month: str,
    confirmation_required: bool = True,
    paid_on: str | None = None,
) -> int:
    async with db.acquire() as conn:
        return await conn.insert(
            """
            INSERT INTO contributions
                (house_id, tg_id, amount_kop, month, status, declared_at, confirmed_by, confirmed_at, paid_on)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            house_id, tg_id, amount_kop, month,
            "declared" if confirmation_required else "confirmed", now_utc(),
            None if confirmation_required else tg_id,
            None if confirmation_required else now_utc(),
            paid_on or now_utc()[:10],
        )


async def get_contribution(contribution_id: int):
    async with db.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT id, house_id, tg_id, amount_kop, month, status, declared_at,
                   confirmed_by, confirmed_at, paid_on
            FROM contributions WHERE id = ?
            """,
            contribution_id,
        )


async def set_contribution_status(contribution_id: int, status: str, confirmed_by: int) -> bool:
    """Подтвердить/отклонить; повторная смена статуса не проходит (только declared → …)."""
    async with db.acquire() as conn:
        rowcount = await conn.execute(
            """
            UPDATE contributions SET status = ?, confirmed_by = ?, confirmed_at = ?
            WHERE id = ? AND status = 'declared'
            """,
            status, confirmed_by, now_utc(), contribution_id,
        )
        return rowcount > 0


async def pending_contributions(house_id: int) -> list:
    async with db.acquire() as conn:
        return await conn.fetch(
            """
            SELECT c.id, c.house_id, c.tg_id, c.amount_kop, c.month, c.status, c.declared_at,
                   m.display_name
            FROM contributions c
            LEFT JOIN memberships m ON m.house_id = c.house_id AND m.tg_id = c.tg_id
            WHERE c.house_id = ? AND c.status = 'declared'
            ORDER BY c.id
            """,
            house_id,
        )


async def month_contributions(house_id: int, month: str) -> list:
    """Все взносы месяца (по полю month — к какому месяцу жилец платит)."""
    async with db.acquire() as conn:
        return await conn.fetch(
            """
            SELECT c.id, c.tg_id, c.amount_kop, c.month, c.status, c.declared_at, m.display_name
            FROM contributions c
            LEFT JOIN memberships m ON m.house_id = c.house_id AND m.tg_id = c.tg_id
            WHERE c.house_id = ? AND c.month = ?
            ORDER BY c.id
            """,
            house_id, month,
        )


async def confirmed_total(house_id: int) -> int:
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COALESCE(SUM(amount_kop), 0) AS total FROM contributions "
            "WHERE house_id = ? AND status = 'confirmed'",
            house_id,
        )
        return int(row["total"]) if row else 0


async def sum_expenses(house_id: int, mode: str, only_reimbursed: bool | None = None) -> int:
    """Сумма трат по режиму; для personal можно взять только возвращённые."""
    sql = "SELECT COALESCE(SUM(amount_kop), 0) AS total FROM expenses WHERE house_id = ? AND mode = ?"
    args: list = [house_id, mode]
    if only_reimbursed is not None:
        sql += " AND reimbursed = ?"
        args.append(1 if only_reimbursed else 0)
    async with db.acquire() as conn:
        row = await conn.fetchrow(sql, *args)
        return int(row["total"]) if row else 0


# ── Траты и чеки ─────────────────────────────────────────────────────────────

async def add_expense(
    house_id: int, tg_id: int, amount_kop: int, category_id: int | None,
    spent_on: str, mode: str, description: str, photo_file_ids: list[str] | None = None,
) -> int:
    async with db.transaction() as conn:
        expense_id = await conn.insert(
            """
            INSERT INTO expenses
                (house_id, tg_id, amount_kop, category_id, spent_on, mode, reimbursed, description, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            house_id, tg_id, amount_kop, category_id, spent_on, mode, description, now_utc(),
        )
        for file_id in photo_file_ids or []:
            await conn.insert(
                "INSERT INTO expense_photos (expense_id, file_id, local_path) VALUES (?, ?, ?)",
                expense_id, file_id, None,
            )
        return expense_id


async def get_expense(expense_id: int):
    async with db.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT e.id, e.house_id, e.tg_id, e.amount_kop, e.category_id, e.spent_on, e.mode,
                   e.reimbursed, e.description, e.created_at,
                   m.display_name, c.name AS category_name
            FROM expenses e
            LEFT JOIN memberships m ON m.house_id = e.house_id AND m.tg_id = e.tg_id
            LEFT JOIN categories c ON c.id = e.category_id
            WHERE e.id = ?
            """,
            expense_id,
        )


async def edit_expense(house_id: int, actor: int, before: dict, after: dict) -> bool:
    async with db.transaction() as conn:
        changed = await conn.execute(
            """UPDATE expenses SET amount_kop = ?, category_id = ?, spent_on = ?, mode = ?, description = ?
               WHERE id = ? AND house_id = ? AND reimbursed = 0
                 AND amount_kop = ? AND COALESCE(category_id, 0) = ? AND spent_on = ?
                 AND mode = ? AND description = ?""",
            after["amount_kop"], after["category_id"], after["spent_on"], after["mode"], after["description"],
            before["id"], house_id, before["amount_kop"], before["category_id"] or 0,
            before["spent_on"], before["mode"], before["description"],
        )
        if not changed:
            return False
        await conn.insert(
            """INSERT INTO expense_edits
               (house_id, expense_id, actor, changed_at, before_json, after_json) VALUES (?, ?, ?, ?, ?, ?)""",
            house_id, before["id"], actor, now_utc(), json.dumps(before, ensure_ascii=False),
            json.dumps(after, ensure_ascii=False),
        )
    return True


async def recent_expenses(house_id: int, limit: int) -> list:
    async with db.acquire() as conn:
        return await conn.fetch(
            """
            SELECT e.id, e.tg_id, e.amount_kop, e.category_id, e.spent_on, e.mode, e.reimbursed,
                   e.description, m.display_name, c.name AS category_name
            FROM expenses e
            LEFT JOIN memberships m ON m.house_id = e.house_id AND m.tg_id = e.tg_id
            LEFT JOIN categories c ON c.id = e.category_id
            WHERE e.house_id = ?
            ORDER BY e.spent_on DESC, e.id DESC LIMIT ?
            """,
            house_id, limit,
        )


async def month_expenses(house_id: int, month: str) -> list:
    async with db.acquire() as conn:
        return await conn.fetch(
            """
            SELECT e.id, e.tg_id, e.amount_kop, e.category_id, e.spent_on, e.mode, e.reimbursed,
                   m.display_name, c.name AS category_name
            FROM expenses e
            LEFT JOIN memberships m ON m.house_id = e.house_id AND m.tg_id = e.tg_id
            LEFT JOIN categories c ON c.id = e.category_id
            WHERE e.house_id = ? AND e.spent_on LIKE ?
            ORDER BY e.spent_on DESC, e.id DESC
            """,
            house_id, month + "%",
        )


async def delete_expense(expense_id: int) -> None:
    async with db.acquire() as conn:
        await conn.execute("DELETE FROM expenses WHERE id = ?", expense_id)


async def reimburse_expense(expense_id: int, confirmed_by: int, *, expected: dict | None = None) -> bool:
    """Вернуть «за свои» из котла: одна атомарная смена флага, повтор не проходит."""
    sql = "UPDATE expenses SET reimbursed = 1 WHERE id = ? AND mode = 'personal' AND reimbursed = 0"
    args = [expense_id]
    if expected is not None:
        sql += " AND amount_kop = ? AND COALESCE(category_id, 0) = ? AND spent_on = ? AND description = ?"
        args.extend((expected["amount_kop"], expected["category_id"] or 0,
                     expected["spent_on"], expected["description"]))
    async with db.acquire() as conn:
        rowcount = await conn.execute(sql, *args)
        return rowcount > 0


async def personal_unreimbursed(house_id: int) -> list:
    """Личные траты («за свои»), ещё не возвращённые из котла."""
    async with db.acquire() as conn:
        return await conn.fetch(
            """
            SELECT e.id, e.tg_id, e.amount_kop, e.spent_on, e.description, m.display_name
            FROM expenses e
            LEFT JOIN memberships m ON m.house_id = e.house_id AND m.tg_id = e.tg_id
            WHERE e.house_id = ? AND e.mode = 'personal' AND e.reimbursed = 0
            ORDER BY e.spent_on, e.id
            """,
            house_id,
        )


async def expense_photos(expense_id: int) -> list:
    async with db.acquire() as conn:
        return await conn.fetch(
            "SELECT id, expense_id, file_id, local_path FROM expense_photos WHERE expense_id = ? ORDER BY id",
            expense_id,
        )


async def photos_count(expense_id: int) -> int:
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) AS n FROM expense_photos WHERE expense_id = ?", expense_id
        )
        return int(row["n"]) if row else 0
