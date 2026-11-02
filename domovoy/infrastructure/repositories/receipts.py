"""Атомарное резервирование загрузок и изменения чеков в пределах траты."""
from datetime import datetime, timedelta, timezone

from core.receipt_limits import RECEIPT_RESERVATION_LEASE_SECONDS
from infrastructure.db import db, now_utc


async def _lock_expense(conn, expense_id: int):
    suffix = " FOR UPDATE" if db.is_postgres else ""
    return await conn.fetchrow("SELECT id, house_id, reimbursed FROM expenses WHERE id = ?" + suffix, expense_id)


def _lease_cutoff() -> str:
    oldest = datetime.now(timezone.utc) - timedelta(seconds=RECEIPT_RESERVATION_LEASE_SECONDS)
    return oldest.strftime("%Y-%m-%d %H:%M:%S")


async def _expire_leases(conn, expense_id: int) -> None:
    await conn.execute(
        "UPDATE web_receipt_uploads SET state = 'expired' "
        "WHERE expense_id = ? AND state = 'reserved' AND created_at <= ?",
        expense_id, _lease_cutoff(),
    )


async def pending_count(expense_id: int) -> int:
    async with db.acquire() as conn:
        count = await conn.fetchrow(
            "SELECT COUNT(*) AS n FROM web_receipt_uploads "
            "WHERE expense_id = ? AND state = 'reserved' AND created_at > ?",
            expense_id, _lease_cutoff(),
        )
        return int(count["n"])


async def reserve_upload(house_id: int, expense_id: int, actor: int, request_id: str,
                         fingerprint: str, limit: int) -> tuple[dict | None, bool]:
    async with db.transaction() as conn:
        expense = await _lock_expense(conn, expense_id)
        if expense is None or expense["house_id"] != house_id or expense["reimbursed"]:
            return None, False
        await _expire_leases(conn, expense_id)
        existing = await conn.fetchrow("SELECT * FROM web_receipt_uploads WHERE request_id = ?", request_id)
        if existing:
            return dict(existing), False
        count = await conn.fetchrow(
            "SELECT (SELECT COUNT(*) FROM expense_photos WHERE expense_id = ?) + "
            "(SELECT COUNT(*) FROM web_receipt_uploads WHERE expense_id = ? "
            "AND state = 'reserved') AS n",
            expense_id, expense_id,
        )
        if int(count["n"]) >= limit:
            return None, False
        inserted = await conn.execute(
            "INSERT INTO web_receipt_uploads "
            "(request_id, house_id, expense_id, actor_id, fingerprint, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (request_id) DO NOTHING",
            request_id, house_id, expense_id, actor, fingerprint, now_utc(),
        )
        result = await conn.fetchrow("SELECT * FROM web_receipt_uploads WHERE request_id = ?", request_id)
        return dict(result), inserted > 0


async def complete_upload(request_id: str, expense_id: int, house_id: int, file_id: str, limit: int) -> int | None:
    async with db.transaction() as conn:
        expense = await _lock_expense(conn, expense_id)
        if expense is None or expense["house_id"] != house_id or expense["reimbursed"]:
            return None
        await _expire_leases(conn, expense_id)
        upload = await conn.fetchrow("SELECT state FROM web_receipt_uploads WHERE request_id = ?", request_id)
        if upload is None or upload["state"] != "reserved":
            return None
        count = await conn.fetchrow("SELECT COUNT(*) AS n FROM expense_photos WHERE expense_id = ?", expense_id)
        if int(count["n"]) >= limit:
            await conn.execute("UPDATE web_receipt_uploads SET state = 'failed' WHERE request_id = ?", request_id)
            return None
        photo_id = await conn.insert("INSERT INTO expense_photos (expense_id, file_id) VALUES (?, ?)",
                                     expense_id, file_id)
        await conn.execute("UPDATE web_receipt_uploads SET state = 'complete', photo_id = ? WHERE request_id = ?",
                           photo_id, request_id)
        return photo_id


async def fail_upload(request_id: str, *, uncertain: bool) -> None:
    async with db.acquire() as conn:
        await conn.execute("UPDATE web_receipt_uploads SET state = ? WHERE request_id = ? AND state = 'reserved'",
                           "uncertain" if uncertain else "failed", request_id)


async def get_photo(expense_id: int, photo_id: int):
    async with db.acquire() as conn:
        return await conn.fetchrow("SELECT id, file_id FROM expense_photos WHERE expense_id = ? AND id = ?",
                                   expense_id, photo_id)


async def delete_expense_if_unchanged(house_id: int, expense_id: int, before: dict) -> bool:
    async with db.acquire() as conn:
        changed = await conn.execute(
            "DELETE FROM expenses WHERE id = ? AND house_id = ? AND tg_id = ? AND amount_kop = ? "
            "AND COALESCE(category_id, 0) = ? AND spent_on = ? AND mode = ? AND description = ? AND reimbursed = 0",
            expense_id, house_id, before["tg_id"], before["amount_kop"], before["category_id"] or 0,
            before["spent_on"], before["mode"], before["description"],
        )
        return changed > 0
