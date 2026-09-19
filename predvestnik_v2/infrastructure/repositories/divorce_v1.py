"""Durable, expiring and replay-safe divorce settlement."""
from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import uuid4

from asyncpg.exceptions import UndefinedTableError


class DivorceError(RuntimeError):
    pass


@dataclass(frozen=True)
class DivorceSettlement:
    receipt_id: str
    marriage_id: int
    actor_id: int
    partner_id: int
    applied: bool


async def create_intent(db, *, actor_id: int) -> dict:
    intent_id = str(uuid4())
    async with db.connection.transaction():
        async with db.execute(
            "SELECT m.id,m.user1_id,m.user2_id,m.user1_name,m.user2_name,"
            "COALESCE(m.family_balance,0),COALESCE(m.family_balance_diamonds,0),"
            "COALESCE(m.family_balance_dark_mora,0),COALESCE(m.family_balance_zarniki,0) "
            "FROM marriage_members mm JOIN marriages m ON m.id=mm.marriage_id "
            "WHERE mm.user_id=? AND m.ended_at IS NULL FOR SHARE",
            (actor_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            raise DivorceError("Активный брак не найден.")
        marriage_id = int(row[0])
        partner_id = int(row[2] if int(row[1]) == int(actor_id) else row[1])
        partner_name = str(row[4] if int(row[1]) == int(actor_id) else row[3])
        legacy_balances = [float(value or 0) for value in row[5:9]]
        async with db.execute(
            "SELECT COUNT(*) FROM pets WHERE marriage_id=?", (marriage_id,),
        ) as cursor:
            pet_count = int((await cursor.fetchone())[0])
        custody = [0.0, 0.0, 0.0, 0.0]
        try:
            async with db.execute(
                "SELECT mora,diamonds,dark_mora,zarniki FROM family_wallet_balances "
                "WHERE marriage_id=? FOR SHARE", (marriage_id,),
            ) as cursor:
                custody_row = await cursor.fetchone()
            if custody_row:
                custody = [float(value or 0) for value in custody_row]
        except UndefinedTableError:
            pass
        snapshot = {
            "legacy_balances": legacy_balances,
            "custody_balances": custody,
            "family_pet_count": pet_count,
        }
        await db.execute(
            "INSERT INTO divorce_intents(id,marriage_id,actor_id,partner_id,snapshot_json,expires_at) "
            "VALUES (?,?,?,?,?::jsonb,NOW()+INTERVAL '15 minutes')",
            (intent_id, marriage_id, actor_id, partner_id, json.dumps(snapshot, sort_keys=True)),
        )
    return {
        "id": intent_id, "marriage_id": marriage_id, "partner_id": partner_id,
        "partner_name": partner_name, **snapshot,
    }


async def settle_intent(db, *, intent_id: str, actor_id: int) -> DivorceSettlement:
    async with db.connection.transaction():
        async with db.execute(
            "SELECT marriage_id,actor_id,partner_id,status,expires_at<=NOW() AS expired,receipt_id "
            "FROM divorce_intents WHERE id=? FOR UPDATE", (intent_id,),
        ) as cursor:
            intent = await cursor.fetchone()
        if not intent or int(intent[1]) != int(actor_id):
            raise DivorceError("Подтверждение развода не найдено или принадлежит другому игроку.")
        if str(intent[3]) == "completed" and intent[5]:
            return DivorceSettlement(str(intent[5]), int(intent[0]), int(intent[1]), int(intent[2]), False)
        if str(intent[3]) != "pending":
            raise DivorceError("Это подтверждение больше не действует.")
        if bool(intent[4]):
            await db.execute("UPDATE divorce_intents SET status='expired' WHERE id=?", (intent_id,))
            raise DivorceError("Подтверждение истекло. Запустите развод заново.")
        marriage_id = int(intent[0])
        async with db.execute(
            "SELECT COALESCE(family_balance,0),COALESCE(family_balance_diamonds,0),"
            "COALESCE(family_balance_dark_mora,0),COALESCE(family_balance_zarniki,0) "
            "FROM marriages WHERE id=? AND ended_at IS NULL FOR UPDATE", (marriage_id,),
        ) as cursor:
            marriage = await cursor.fetchone()
        if not marriage:
            raise DivorceError("Брак уже завершён другим действием.")
        if any(float(value or 0) != 0 for value in marriage):
            raise DivorceError("Сначала распределите семейный кошелёк. Ничего не списано.")
        async with db.execute("SELECT 1 FROM pets WHERE marriage_id=? LIMIT 1 FOR SHARE", (marriage_id,)) as cursor:
            if await cursor.fetchone():
                raise DivorceError("Сначала распределите семейных питомцев. Ничего не удалено.")
        try:
            async with db.execute(
                "SELECT mora,diamonds,dark_mora,zarniki FROM family_wallet_balances "
                "WHERE marriage_id=? FOR UPDATE", (marriage_id,),
            ) as cursor:
                custody = await cursor.fetchone()
            if custody and any(float(value or 0) != 0 for value in custody):
                raise DivorceError("Сначала распределите семейный кошелёк. Ничего не списано.")
        except UndefinedTableError:
            pass
        receipt_id = str(uuid4())
        await db.execute("UPDATE marriages SET ended_at=NOW() WHERE id=?", (marriage_id,))
        await db.execute("DELETE FROM marriage_members WHERE marriage_id=?", (marriage_id,))
        await db.execute(
            "INSERT INTO divorce_receipts(id,intent_id,marriage_id,actor_id,partner_id) VALUES (?,?,?,?,?)",
            (receipt_id, intent_id, marriage_id, int(intent[1]), int(intent[2])),
        )
        await db.execute(
            "UPDATE divorce_intents SET status='completed',receipt_id=?,completed_at=NOW() WHERE id=?",
            (receipt_id, intent_id),
        )
    return DivorceSettlement(receipt_id, marriage_id, int(intent[1]), int(intent[2]), True)


async def cancel_intent(db, *, intent_id: str, actor_id: int) -> bool:
    async with db.execute(
        "UPDATE divorce_intents SET status='cancelled' WHERE id=? AND actor_id=? AND status='pending' RETURNING id",
        (intent_id, actor_id),
    ) as cursor:
        return await cursor.fetchone() is not None


async def install_schema(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS divorce_intents (
            id TEXT PRIMARY KEY, marriage_id BIGINT NOT NULL REFERENCES marriages(id) ON DELETE RESTRICT,
            actor_id BIGINT NOT NULL, partner_id BIGINT NOT NULL,
            snapshot_json JSONB NOT NULL, status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending','cancelled','expired','completed')),
            expires_at TIMESTAMPTZ NOT NULL, receipt_id TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), completed_at TIMESTAMPTZ NULL
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS divorce_receipts (
            id TEXT PRIMARY KEY, intent_id TEXT NOT NULL UNIQUE REFERENCES divorce_intents(id) ON DELETE RESTRICT,
            marriage_id BIGINT NOT NULL REFERENCES marriages(id) ON DELETE RESTRICT,
            actor_id BIGINT NOT NULL, partner_id BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_divorce_intents_actor ON divorce_intents(actor_id,created_at DESC)"
    )
