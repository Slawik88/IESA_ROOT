"""Durable, expiring and replay-safe divorce settlement."""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from uuid import uuid4

from asyncpg.exceptions import UndefinedTableError
from core.economy_contract import as_ledger_amount
from infrastructure.repositories.family_wallet_v1 import transfer_between_personal_and_family


class DivorceError(RuntimeError):
    pass


@dataclass(frozen=True)
class DivorceSettlement:
    receipt_id: str
    marriage_id: int
    actor_id: int
    partner_id: int
    applied: bool


@dataclass(frozen=True)
class PropertyAllocation:
    receipt_id: str
    divorce_receipt_id: str
    marriage_id: int
    actor_id: int
    partner_id: int
    allocations: dict
    pet_owners: dict[int, int]
    applied: bool


_CURRENCIES = ("mora", "diamonds", "dark_mora", "zarniki")


def _split_amount(amount: Decimal, first_user: int, second_user: int, currency: str) -> dict[int, Decimal]:
    quantum = Decimal("1") if currency == "zarniki" else Decimal("0.000001")
    second = (amount / 2).quantize(quantum, rounding=ROUND_DOWN)
    return {first_user: amount - second, second_user: second}


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
        async with db.execute(
            "SELECT user_id FROM marriage_members WHERE marriage_id=? ORDER BY user_id FOR UPDATE",
            (marriage_id,),
        ) as cursor:
            members = await cursor.fetchall()
        if len(members) != 2:
            raise DivorceError("Состав семьи изменился. Запустите развод заново.")
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


async def allocate_property(db, *, intent_id: str, actor_id: int) -> PropertyAllocation:
    """Atomically split all family custody and end the marriage.

    Currency is split equally; an indivisible remainder goes to the lower user
    id. Family pets, ordered by immutable id, alternate between both partners.
    """
    async with db.connection.transaction():
        async with db.execute(
            "SELECT marriage_id,actor_id,partner_id,status,expires_at<=NOW() AS expired,receipt_id "
            "FROM divorce_intents WHERE id=? FOR UPDATE", (intent_id,),
        ) as cursor:
            intent = await cursor.fetchone()
        if not intent or int(intent[1]) != int(actor_id):
            raise DivorceError("Распределение не найдено или принадлежит другому игроку.")
        async with db.execute(
            "SELECT receipt_id,allocation_json,pet_owners_json FROM divorce_property_receipts "
            "WHERE intent_id=?", (intent_id,),
        ) as cursor:
            replay = await cursor.fetchone()
        if replay:
            replay_allocations = json.loads(replay[1]) if isinstance(replay[1], str) else dict(replay[1])
            replay_pets = json.loads(replay[2]) if isinstance(replay[2], str) else dict(replay[2])
            return PropertyAllocation(
                str(replay[0]), str(intent[5] or ""), int(intent[0]),
                int(intent[1]), int(intent[2]), replay_allocations,
                {int(k): int(v) for k, v in replay_pets.items()}, False,
            )
        if str(intent[3]) != "pending" or bool(intent[4]):
            raise DivorceError("Подтверждение больше не действует. Запустите развод заново.")
        marriage_id = int(intent[0])
        users = sorted((int(intent[1]), int(intent[2])))
        async with db.execute(
            "SELECT family_balance,COALESCE(family_balance_diamonds,0),"
            "COALESCE(family_balance_dark_mora,0),COALESCE(family_balance_zarniki,0) "
            "FROM marriages WHERE id=? AND ended_at IS NULL FOR UPDATE", (marriage_id,),
        ) as cursor:
            legacy = await cursor.fetchone()
        if not legacy:
            raise DivorceError("Брак уже завершён другим действием.")
        async with db.execute(
            "SELECT user_id FROM marriage_members WHERE marriage_id=? ORDER BY user_id FOR UPDATE",
            (marriage_id,),
        ) as cursor:
            members = await cursor.fetchall()
        if [int(row[0]) for row in members] != users:
            raise DivorceError("Состав семьи изменился. Средства не изменены.")
        async with db.execute(
            "SELECT id FROM pets WHERE marriage_id=? ORDER BY id FOR UPDATE", (marriage_id,),
        ) as cursor:
            pets = [int(row[0]) for row in await cursor.fetchall()]
        async with db.execute(
            "SELECT mora,diamonds,dark_mora,zarniki FROM family_wallet_balances "
            "WHERE marriage_id=? FOR UPDATE", (marriage_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            raise DivorceError("Семейный кошелёк не подготовлен. Средства не изменены.")
        balances = {currency: as_ledger_amount(row[index]) for index, currency in enumerate(_CURRENCIES)}
        if any(
            as_ledger_amount(legacy[index]) != balances[currency]
            for index, currency in enumerate(_CURRENCIES)
        ):
            raise DivorceError("Баланс семьи требует проверки. Средства не изменены.")
        allocations: dict[str, dict[str, str]] = {}
        allocation_legs: list[tuple[str, int, Decimal, str, str]] = []
        for currency, balance in balances.items():
            shares = _split_amount(balance, users[0], users[1], currency)
            allocations[currency] = {str(uid): str(amount) for uid, amount in shares.items()}
            for uid in users:
                amount = shares[uid]
                if amount <= 0:
                    continue
                result = await transfer_between_personal_and_family(
                    db, actor_id=uid, currency=currency, amount=amount,
                    action="withdrawal",
                    idempotency_key=f"divorce-allocation:{intent_id}:{currency}:{uid}",
                )
                async with db.execute(
                    "SELECT source_personal_operation_id FROM family_wallet_ledger "
                    "WHERE operation_id=? AND currency=?", (result.operation_id, currency),
                ) as cursor:
                    personal_row = await cursor.fetchone()
                if not personal_row or not personal_row[0]:
                    raise RuntimeError("Family allocation personal ledger link is missing.")
                allocation_legs.append((currency, uid, amount, result.operation_id, str(personal_row[0])))
        pet_owners = {pet_id: users[index % 2] for index, pet_id in enumerate(pets)}
        for pet_id, owner_id in pet_owners.items():
            await db.execute(
                "UPDATE pets SET owner_id=?,marriage_id=NULL WHERE id=? AND marriage_id=?",
                (owner_id, pet_id, marriage_id),
            )
        receipt_id = str(uuid4())
        divorce_receipt_id = str(uuid4())
        await db.execute(
            "INSERT INTO divorce_property_receipts"
            "(receipt_id,intent_id,marriage_id,actor_id,allocation_json,pet_owners_json) "
            "VALUES (?,?,?,?,?::jsonb,?::jsonb)",
            (receipt_id, intent_id, marriage_id, actor_id,
             json.dumps(allocations, sort_keys=True), json.dumps(pet_owners, sort_keys=True)),
        )
        for currency, beneficiary_id, amount, family_operation_id, personal_operation_id in allocation_legs:
            await db.execute(
                "INSERT INTO divorce_property_allocation_legs"
                "(receipt_id,currency,initiator_id,beneficiary_id,amount,family_operation_id,personal_operation_id) "
                "VALUES (?,?,?,?,?,?,?)",
                (receipt_id, currency, actor_id, beneficiary_id, amount,
                 family_operation_id, personal_operation_id),
            )
        await db.execute("UPDATE marriages SET ended_at=NOW() WHERE id=?", (marriage_id,))
        await db.execute("DELETE FROM marriage_members WHERE marriage_id=?", (marriage_id,))
        await db.execute(
            "INSERT INTO divorce_receipts(id,intent_id,marriage_id,actor_id,partner_id) VALUES (?,?,?,?,?)",
            (divorce_receipt_id, intent_id, marriage_id, int(intent[1]), int(intent[2])),
        )
        await db.execute(
            "UPDATE divorce_intents SET status='completed',receipt_id=?,completed_at=NOW() WHERE id=?",
            (divorce_receipt_id, intent_id),
        )
    return PropertyAllocation(
        receipt_id, divorce_receipt_id, marriage_id, int(intent[1]), int(intent[2]),
        allocations, pet_owners, True,
    )


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
    await db.execute("""
        CREATE TABLE IF NOT EXISTS divorce_property_receipts (
            receipt_id TEXT PRIMARY KEY,
            intent_id TEXT NOT NULL UNIQUE REFERENCES divorce_intents(id) ON DELETE RESTRICT,
            marriage_id BIGINT NOT NULL REFERENCES marriages(id) ON DELETE RESTRICT,
            actor_id BIGINT NOT NULL,
            allocation_json JSONB NOT NULL,
            pet_owners_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("""
        CREATE OR REPLACE FUNCTION reject_divorce_property_receipt_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'divorce_property_receipts is append-only';
        END $$
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS divorce_property_allocation_legs (
            receipt_id TEXT NOT NULL REFERENCES divorce_property_receipts(receipt_id) ON DELETE RESTRICT,
            currency TEXT NOT NULL,
            initiator_id BIGINT NOT NULL,
            beneficiary_id BIGINT NOT NULL,
            amount NUMERIC(24,6) NOT NULL CHECK(amount > 0),
            family_operation_id TEXT NOT NULL,
            personal_operation_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(receipt_id,currency,beneficiary_id)
        )
    """)
    await db.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname='trg_divorce_property_receipts_immutable'
                  AND tgrelid='divorce_property_receipts'::regclass
            ) THEN
                CREATE TRIGGER trg_divorce_property_receipts_immutable
                BEFORE UPDATE OR DELETE ON divorce_property_receipts
                FOR EACH ROW EXECUTE FUNCTION reject_divorce_property_receipt_mutation();
            END IF;
        END $$
    """)
    await db.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname='trg_divorce_property_legs_immutable'
                  AND tgrelid='divorce_property_allocation_legs'::regclass
            ) THEN
                CREATE TRIGGER trg_divorce_property_legs_immutable
                BEFORE UPDATE OR DELETE ON divorce_property_allocation_legs
                FOR EACH ROW EXECUTE FUNCTION reject_divorce_property_receipt_mutation();
            END IF;
        END $$
    """)
