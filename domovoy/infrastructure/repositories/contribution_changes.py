"""CAS-правка взноса, история и tombstone удаления в одной транзакции."""
import json

from core.permissions import ROLE_OWNER
from infrastructure.db import db, now_utc

# Повторная проверка участия/права входит в сам SQL-переход, а не только в чтение формы.
_ACTOR_GUARD = """EXISTS (
    SELECT 1 FROM memberships m
    WHERE m.house_id = contributions.house_id AND m.tg_id = ? AND m.status = 'active'
      AND (m.role = ? OR (contributions.tg_id = m.tg_id AND contributions.status = 'declared')
           OR EXISTS (SELECT 1 FROM member_permissions p
                      WHERE p.house_id = m.house_id AND p.tg_id = m.tg_id
                        AND p.permission = 'confirm_contributions'))
)"""
_CONTENT_GUARD = """id = ? AND house_id = ? AND tg_id = ? AND amount_kop = ?
                    AND paid_on = ? AND month = ? AND status = ?"""


def _before_args(house_id: int, before: dict, actor: int) -> tuple:
    return (before["id"], house_id, before["tg_id"], before["amount_kop"], before["paid_on"],
            before["month"], before["status"], actor, ROLE_OWNER)


async def _audit(conn, house_id: int, actor: int, before: dict, version: str, after: dict | None) -> None:
    await conn.insert(
        "INSERT INTO contribution_changes "
        "(house_id, contribution_id, actor, action, before_version, before_json, after_json, changed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        house_id, before["id"], actor, "edit" if after is not None else "delete", version,
        json.dumps(before, ensure_ascii=False), json.dumps(after, ensure_ascii=False) if after is not None else None,
        now_utc(),
    )


async def edit(house_id: int, actor: int, before: dict, after: dict, version: str) -> bool:
    async with db.transaction() as conn:
        changed = await conn.execute(
            "UPDATE contributions SET amount_kop = ?, paid_on = ?, month = ? WHERE "
            + _CONTENT_GUARD + " AND " + _ACTOR_GUARD,
            after["amount_kop"], after["paid_on"], after["month"], *_before_args(house_id, before, actor),
        )
        if not changed:
            return False
        await _audit(conn, house_id, actor, before, version, {**before, **after})
    return True


async def remove(house_id: int, actor: int, before: dict, version: str, canonical: dict) -> bool:
    async with db.transaction() as conn:
        changed = await conn.execute("DELETE FROM contributions WHERE " + _CONTENT_GUARD + " AND " + _ACTOR_GUARD,
                                     *_before_args(house_id, before, actor))
        if not changed:
            return False
        await _audit(conn, house_id, actor, before, version, None)
        # Сохраняем исходные fingerprints web/import-запросов. Для записи из бота
        # резервируем ключ собственного экспорта: старый файл не воскресит удаление.
        linked = await conn.fetchrow(
            "SELECT source_key FROM money_import_items WHERE house_id = ? AND kind = 'contribution' AND target_id = ?",
            house_id, before["id"],
        )
        if linked is None:
            await conn.execute(
                "INSERT INTO money_import_items "
                "(house_id, source_key, fingerprint, imported_by, imported_at, kind, target_id) "
                "VALUES (?, ?, ?, ?, ?, 'contribution', ?) ON CONFLICT (house_id, source_key) DO NOTHING",
                house_id, canonical["source_key"], canonical["fingerprint"], actor, now_utc(), before["id"],
            )
    return True


async def deleted(house_id: int, contribution_id: int, version: str):
    async with db.acquire() as conn:
        return await conn.fetchrow(
            "SELECT actor, before_json FROM contribution_changes "
            "WHERE house_id = ? AND contribution_id = ? AND action = 'delete' AND before_version = ?",
            house_id, contribution_id, version,
        )


async def matching_edit(house_id: int, contribution_id: int, actor: int, version: str, after: dict) -> bool:
    async with db.acquire() as conn:
        rows = await conn.fetch(
            "SELECT after_json FROM contribution_changes "
            "WHERE house_id = ? AND contribution_id = ? AND actor = ? AND action = 'edit' AND before_version = ?",
            house_id, contribution_id, actor, version,
        )
    return any(json.loads(row["after_json"]) == after for row in rows)
