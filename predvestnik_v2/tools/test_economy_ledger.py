#!/usr/bin/env python3
"""Deterministic contract tests for the canonical economic ledger."""
from __future__ import annotations

import asyncio
import copy
from decimal import Decimal
import importlib.util
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# The local audit container intentionally has no runtime web/bot dependencies.
# economy.py only needs the class name for an annotation in this test.
if importlib.util.find_spec("asyncpg") is None:
    sys.modules["asyncpg"] = types.SimpleNamespace(Connection=object)
if importlib.util.find_spec("loguru") is None:
    sys.modules["loguru"] = types.SimpleNamespace(
        logger=types.SimpleNamespace(error=lambda *_args, **_kwargs: None)
    )

from core.economy_contract import (  # noqa: E402
    IdempotencyConflict,
    InsufficientBalance,
    InvalidEconomicMutation,
    as_ledger_amount,
    normalize_deltas,
)
from infrastructure.repositories.economy_ledger import (  # noqa: E402
    apply_balance_change,
    find_balance_replay,
    find_reference_replay,
)
from infrastructure.repositories.economy import (  # noqa: E402
    buy_item,
    exchange_zarniki,
    spend_diamonds,
    spend_mora,
    transfer_currency,
)


class _Cursor:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    async def fetchone(self):
        return self.rows[0] if self.rows else None

    async def fetchall(self):
        return list(self.rows)


class _Execute:
    def __init__(self, db, sql, args):
        self.db = db
        self.sql = sql
        self.args = args
        self.cursor = None

    async def _run(self):
        if self.cursor is None:
            self.cursor = self.db._run(self.sql, self.args)
        return self.cursor

    def __await__(self):
        return self._run().__await__()

    async def __aenter__(self):
        return await self._run()

    async def __aexit__(self, *_):
        return False


class _Transaction:
    def __init__(self, db):
        self.db = db
        self.snapshot = None

    async def __aenter__(self):
        self.snapshot = copy.deepcopy(
            (self.db.users, self.db.operations, self.db.ledger, self.db.wallet, self.db.inventory, self.db.reserves)
        )
        return self

    async def __aexit__(self, exc_type, *_):
        if exc_type:
            (
                self.db.users,
                self.db.operations,
                self.db.ledger,
                self.db.wallet,
                self.db.inventory,
                self.db.reserves,
            ) = self.snapshot
        return False


class FakeLedgerDB:
    """Small SQL-boundary fake; business behavior is still exercised end-to-end."""

    def __init__(self):
        self.connection = self
        self.users = {}
        self.operations = {}
        self.ledger = []
        self.wallet = []
        self.inventory = {}
        self.reserves = {}

    def transaction(self):
        return _Transaction(self)

    def execute(self, sql, args=()):
        return _Execute(self, sql, tuple(args))

    def _run(self, sql, args):
        compact = " ".join(sql.split())
        upper = compact.upper()

        if upper.startswith("INSERT INTO USERS"):
            user_id = int(args[0])
            self.users.setdefault(
                user_id,
                {"mora": 0.0, "diamonds": 0.0, "dark_mora": 0.0, "zarniki": 0.0},
            )
            return _Cursor()

        if upper.startswith("INSERT INTO ECONOMIC_OPERATIONS"):
            operation_id, user_id, key, fingerprint, reason, source, ref_type, ref_id, metadata = args
            unique = (int(user_id), key)
            if unique in self.operations:
                return _Cursor()
            self.operations[unique] = {
                "id": operation_id,
                "request_fingerprint": fingerprint,
                "reason_code": reason,
                "source_type": source,
                "reference_type": ref_type,
                "reference_id": ref_id,
                "metadata_json": metadata,
            }
            return _Cursor([(operation_id,)])

        if upper.startswith("SELECT 1 FROM ECONOMIC_OPERATIONS"):
            operation = self.operations.get((int(args[0]), args[1]))
            return _Cursor([(1,)] if operation else [])

        if upper.startswith("SELECT ID, REQUEST_FINGERPRINT, REASON_CODE"):
            operation = self.operations.get((int(args[0]), args[1]))
            return _Cursor([operation] if operation else [])

        if upper.startswith("SELECT ID, REQUEST_FINGERPRINT FROM ECONOMIC_OPERATIONS"):
            operation = self.operations.get((int(args[0]), args[1]))
            return _Cursor([operation] if operation else [])

        if upper.startswith("SELECT CURRENCY, DELTA, BALANCE_BEFORE, BALANCE_AFTER"):
            operation_id = args[0]
            rows = [row for row in self.ledger if row["operation_id"] == operation_id]
            rows.sort(key=lambda row: row["currency"])
            return _Cursor(rows)

        if upper.startswith("SELECT COALESCE(USER_BALANCE_MORA") and "FOR UPDATE" in upper:
            balances = self.users[int(args[0])]
            return _Cursor([dict(balances)])

        if upper.startswith("SELECT COALESCE(RESERVED_MORA"):
            return _Cursor([(self.reserves.get(int(args[0]), 0.0),)])

        if upper.startswith("UPDATE USERS SET USER_BALANCE_MORA = ?"):
            mora, diamonds, dark_mora, zarniki, user_id = args
            self.users[int(user_id)] = {
                "mora": float(mora),
                "diamonds": float(diamonds),
                "dark_mora": float(dark_mora),
                "zarniki": float(zarniki),
            }
            return _Cursor()

        if upper.startswith("INSERT INTO ECONOMIC_LEDGER"):
            operation_id, user_id, currency, delta, before, after, reason = args
            self.ledger.append(
                {
                    "operation_id": operation_id,
                    "user_id": int(user_id),
                    "currency": currency,
                    "delta": Decimal(delta),
                    "balance_before": Decimal(before),
                    "balance_after": Decimal(after),
                    "reason_code": reason,
                }
            )
            return _Cursor()

        if upper.startswith("SELECT USER_BALANCE_MORA, USER_BALANCE_DIAMONDS"):
            balances = self.users[int(args[0])]
            return _Cursor(
                [(
                    balances["mora"], balances["diamonds"],
                    balances["dark_mora"], balances["zarniki"],
                )]
            )

        if upper.startswith("INSERT INTO WALLET_LOG"):
            self.wallet.append(args)
            return _Cursor()

        if upper.startswith("INSERT INTO INVENTORY"):
            user_id, item_id, quantity, increment = args
            key = (int(user_id), str(item_id))
            if key in self.inventory:
                self.inventory[key] += int(increment)
            else:
                self.inventory[key] = int(quantity)
            return _Cursor()

        raise AssertionError(f"Unexpected SQL in FakeLedgerDB: {compact}")


def _assert_contract_validation():
    assert as_ledger_amount(0.1) == Decimal("0.100000")
    assert normalize_deltas({"zarniki": 0, "mora": 2}) == {"mora": Decimal("2.000000")}
    for invalid in (float("nan"), float("inf"), True):
        try:
            as_ledger_amount(invalid)
        except InvalidEconomicMutation:
            pass
        else:
            raise AssertionError(f"Invalid amount accepted: {invalid!r}")
    for unknown in ({"coins": 1}, {17: 1}):
        try:
            normalize_deltas(unknown)
        except InvalidEconomicMutation:
            pass
        else:
            raise AssertionError("Unknown currency accepted")


def _assert_schema_and_boundaries_wired():
    schema = (ROOT / "infrastructure/repositories/economy_ledger.py").read_text(
        encoding="utf-8"
    )
    for snippet in (
        "CREATE TABLE IF NOT EXISTS economic_operations",
        "UNIQUE (user_id, idempotency_key)",
        "CREATE TABLE IF NOT EXISTS economic_ledger",
        "CHECK (balance_after = balance_before + delta)",
    ):
        assert snippet in schema, f"Missing ledger schema invariant: {snippet}"

    bot_init = (ROOT / "bot/core/database.py").read_text(encoding="utf-8")
    web_init = (ROOT / "FastAPI/main.py").read_text(encoding="utf-8")
    assert "await _ensure_ledger(_LedgerPGAdapter(db))" in bot_init
    assert '(ensure_economy_ledger,           "economy_ledger")' in web_init

    payments = (ROOT / "bot/handlers/payments.py").read_text(encoding="utf-8")
    assert "payment.telegram_payment_charge_id" in payments
    assert 'idempotency_key=f"stars_purchase:{purchase_id}"' in payments
    assert "pay_purchase_commission" not in payments

    referral = (ROOT / "services/referral.py").read_text(encoding="utf-8")
    assert "referral_commission" not in referral
    assert "zarniki=" not in referral

    promo_repository = (ROOT / "infrastructure/repositories/promocodes.py").read_text(
        encoding="utf-8"
    )
    assert "if dark_mora or zarniki:" in promo_repository
    shop_repository = (ROOT / "infrastructure/repositories/economy.py").read_text(
        encoding="utf-8"
    )
    shop_router = (ROOT / "FastAPI/routers/shop.py").read_text(encoding="utf-8")
    shop_client = (ROOT / "FastAPI/static/app.04.js").read_text(encoding="utf-8")
    bot_shop = (ROOT / "bot/handlers/shop.py").read_text(encoding="utf-8")
    assert "cover_with_zarniki" not in shop_repository + shop_router + shop_client
    assert "/shop/checkout-quote" not in shop_router + shop_client
    assert 'Header(alias="Idempotency-Key")' in shop_router
    assert 'idempotency_key=f"shop:telegram:{query.id}"' in bot_shop

    exchange = (ROOT / "FastAPI/routers/exchange.py").read_text(encoding="utf-8")
    assert "Покупка и продажа Алмазов за Мору отключены" in exchange
    assert "Алмазы больше нельзя купить за Мору" in exchange
    assert "Алмазы больше нельзя продать за Мору" in exchange
    assert "exchange_mora_to_dia" not in exchange
    assert "exchange_dia_to_mora" not in exchange

    client_base = (ROOT / "FastAPI/static/app.01.js").read_text(encoding="utf-8")
    client_wallet = (ROOT / "FastAPI/static/app.06.js").read_text(encoding="utf-8")
    assert "function economyRequestKey(scope)" in client_base
    assert "'Idempotency-Key':requestKey" in client_wallet


async def _assert_apply_replay_conflict_and_rollback():
    db = FakeLedgerDB()
    db.users[7] = {"mora": 1000.0, "diamonds": 2.0, "dark_mora": 0.0, "zarniki": 50.0}

    first = await apply_balance_change(
        db,
        7,
        {"mora": -300, "diamonds": 1.25},
        reason_code="exchange_mora_to_dia",
        idempotency_key="web:exchange:case-1",
        source_type="exchange",
        reference_type="currency_pair",
        reference_id="mora_diamonds",
        metadata={"request": "case-1"},
    )
    assert first.applied is True
    assert db.users[7]["mora"] == 700.0
    assert db.users[7]["diamonds"] == 3.25
    assert len(db.ledger) == 2
    assert len(db.wallet) == 1, "A multi-currency mutation must project as one wallet row"
    for entry in db.ledger:
        assert entry["balance_after"] == entry["balance_before"] + entry["delta"]

    replay = await apply_balance_change(
        db,
        7,
        {"mora": -300, "diamonds": 1.25},
        reason_code="exchange_mora_to_dia",
        idempotency_key="web:exchange:case-1",
        source_type="exchange",
        reference_type="currency_pair",
        reference_id="mora_diamonds",
    )
    assert replay.applied is False
    assert replay.operation_id == first.operation_id
    assert db.users[7]["mora"] == 700.0
    assert len(db.ledger) == 2 and len(db.wallet) == 1

    found = await find_balance_replay(
        db,
        7,
        {"mora": -300, "diamonds": 1.25},
        reason_code="exchange_mora_to_dia",
        idempotency_key="web:exchange:case-1",
        source_type="exchange",
        reference_type="currency_pair",
        reference_id="mora_diamonds",
    )
    assert found and found.operation_id == first.operation_id

    try:
        await apply_balance_change(
            db,
            7,
            {"mora": -301, "diamonds": 1.25},
            reason_code="exchange_mora_to_dia",
            idempotency_key="web:exchange:case-1",
            source_type="exchange",
            reference_type="currency_pair",
            reference_id="mora_diamonds",
        )
    except IdempotencyConflict:
        pass
    else:
        raise AssertionError("Idempotency key was accepted for a different mutation")
    assert db.users[7]["mora"] == 700.0 and len(db.ledger) == 2

    db.reserves[7] = 650.0
    try:
        await apply_balance_change(
            db, 7, {"mora": -51}, reason_code="shop_purchase",
            idempotency_key="reserved-mora-block", source_type="shop",
            reference_type="item", reference_id="test",
        )
    except InsufficientBalance:
        pass
    else:
        raise AssertionError("Reserved Mora was spendable by an unrelated operation")
    assert db.users[7]["mora"] == 700.0
    db.reserves[7] = 0.0

    try:
        await apply_balance_change(
            db,
            7,
            {"zarniki": -51},
            reason_code="vip_purchase",
            idempotency_key="insufficient-case",
        )
    except InsufficientBalance:
        pass
    else:
        raise AssertionError("Negative balance mutation was accepted")
    assert db.users[7]["zarniki"] == 50.0
    assert (7, "insufficient-case") not in db.operations, "Failed mutation must roll back gate"
    assert len(db.ledger) == 2 and len(db.wallet) == 1

    try:
        await apply_balance_change(
            db,
            7,
            {"zarniki": 10},
            reason_code="promocode",
            idempotency_key="free-premium",
        )
    except InvalidEconomicMutation as exc:
        assert "Stars" in str(exc)
    else:
        raise AssertionError("A free positive Zarniki source was accepted")
    assert (7, "free-premium") not in db.operations

    purchase = await apply_balance_change(
        db,
        7,
        {"zarniki": 10},
        reason_code="stars_purchase",
        idempotency_key="stars-payment-1",
        source_type="payment",
    )
    assert purchase.applied and db.users[7]["zarniki"] == 60.0


async def _assert_exchange_retry_ignores_consumed_balance():
    db = FakeLedgerDB()
    db.users[11] = {"mora": 0.0, "diamonds": 0.0, "dark_mora": 0.0, "zarniki": 25.0}

    ok, _ = await exchange_zarniki(
        db, 11, 20, "mora", idempotency_key="request-77"
    )
    assert ok is True
    after_first = dict(db.users[11])
    assert after_first["zarniki"] == 5.0
    operation = db.operations[(11, "exchange:zarniki:mora:request-77")]
    assert operation["reason_code"] == "paid_exchange"
    assert operation["source_type"] == "exchange"
    assert '"provenance":"paid_exchange"' in operation["metadata_json"]

    # A retry must resolve from the operation gate before checking the now-spent
    # balance; otherwise a valid replay would incorrectly fail as insufficient.
    ok, message = await exchange_zarniki(
        db, 11, 20, "mora", idempotency_key="request-77"
    )
    assert ok is True and "уже" in message.lower()
    assert db.users[11] == after_first
    assert len(db.wallet) == 1

    ok, message = await exchange_zarniki(
        db, 11, 21, "mora", idempotency_key="request-77"
    )
    assert ok is False and "ключ" in message.lower()
    assert db.users[11] == after_first

    ok, message = await exchange_zarniki(db, 11, 1, "diamonds")
    assert ok is False and "нельзя купить" in message.lower()
    ok, message = await exchange_zarniki(db, 11, 1.5, "mora")
    assert ok is False and "целое число" in message.lower()
    assert db.users[11] == after_first


async def _assert_shop_and_spend_use_one_ledger_operation():
    db = FakeLedgerDB()
    db.users[21] = {"mora": 500.0, "diamonds": 5.0, "dark_mora": 0.0, "zarniki": 20.0}

    ok, message = await buy_item(
        db, 21, "ration", 100, 1, 2, p_zarniki=2,
        idempotency_key="shop:request-21",
    )
    assert ok and message == "Покупка завершена."
    assert db.users[21] == {"mora": 300.0, "diamonds": 3.0, "dark_mora": 0.0, "zarniki": 16.0}
    assert db.inventory[(21, "ration")] == 2
    assert len(db.operations) == 1 and len(db.ledger) == 3 and len(db.wallet) == 1

    ok, message = await buy_item(
        db, 21, "ration", 100, 1, 2, p_zarniki=2,
        idempotency_key="shop:request-21",
    )
    assert ok and message == "Эта покупка уже обработана."
    assert db.inventory[(21, "ration")] == 2
    assert len(db.operations) == 1 and len(db.ledger) == 3 and len(db.wallet) == 1

    assert await spend_mora(db, 21, 50, idempotency_key="spend:mora:1") == (True, "OK")
    assert await spend_diamonds(db, 21, 1, idempotency_key="spend:diamond:1") == (True, "OK")
    assert db.users[21]["mora"] == 250.0 and db.users[21]["diamonds"] == 2.0
    assert len(db.operations) == 3 and len(db.wallet) == 3


async def _assert_dynamic_reference_replay():
    db = FakeLedgerDB()
    db.users[31] = {"mora": 0.0, "diamonds": 0.0, "dark_mora": 0.0, "zarniki": 900.0}
    first = await apply_balance_change(
        db, 31, {"zarniki": -440},
        reason_code="cosmetic_lineup_purchase",
        idempotency_key="lineup:request-31",
        source_type="cosmetics",
        reference_type="lineup",
        reference_id="hanami",
    )
    replay = await find_reference_replay(
        db, 31,
        reason_code="cosmetic_lineup_purchase",
        idempotency_key="lineup:request-31",
        source_type="cosmetics",
        reference_type="lineup",
        reference_id="hanami",
    )
    assert replay and not replay.applied and replay.operation_id == first.operation_id
    try:
        await find_reference_replay(
            db, 31,
            reason_code="cosmetic_lineup_purchase",
            idempotency_key="lineup:request-31",
            source_type="cosmetics",
            reference_type="lineup",
            reference_id="lotus",
        )
    except IdempotencyConflict:
        pass
    else:
        raise AssertionError("Dynamic replay accepted a different reference")


async def _assert_direct_transfers_are_closed():
    class NoDatabaseAccess:
        def __getattr__(self, name):
            raise AssertionError(f"Closed transfer attempted database access: {name}")

    ok, message = await transfer_currency(
        NoDatabaseAccess(), 1, 2, "zarniki", 999, chat_id=-100,
    )
    assert ok is False
    assert "Прямые переводы валют отключены" in message

    repository = (ROOT / "infrastructure/repositories/economy.py").read_text(encoding="utf-8")
    transfer_block = repository[
        repository.index("async def transfer_currency("):
        repository.index("async def transfer_mora(")
    ]
    assert "UPDATE users SET" not in transfer_block
    ai = (ROOT / "services/ai_assistant.py").read_text(encoding="utf-8")
    exposed_tools = ai[ai.index("_TOOLS ="):ai.index("# ── Динамические темы")]
    assert '"name": "propose_transfer"' not in exposed_tools


async def main():
    _assert_contract_validation()
    _assert_schema_and_boundaries_wired()
    await _assert_apply_replay_conflict_and_rollback()
    await _assert_exchange_retry_ignores_consumed_balance()
    await _assert_shop_and_spend_use_one_ledger_operation()
    await _assert_dynamic_reference_replay()
    await _assert_direct_transfers_are_closed()
    print("economy ledger tests: OK")


if __name__ == "__main__":
    asyncio.run(main())
