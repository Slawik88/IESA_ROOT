"""Real PostgreSQL proof for atomic, unlimited, replay-safe Zarniki exchange."""
from __future__ import annotations
import argparse, asyncio, pathlib, sys
from urllib.parse import urlparse
import asyncpg

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import economy_ledger, star_payments_v1, zarniki_exchange_v1 as usage_repo
from services import zarniki_exchange_v1


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def run(dsn: str) -> None:
    conn = await asyncpg.connect(dsn)
    db = PGAdapter(conn)
    transaction = conn.transaction()
    await transaction.start()
    try:
        await economy_ledger.ensure_tables(db)
        await star_payments_v1.ensure_tables(db)
        await usage_repo.ensure_tables(db)
        user = 976201
        credit = await economy_ledger.apply_balance_change(
            db, user, {"zarniki": 5000}, reason_code="stars_purchase",
            idempotency_key="seed-zarniki", source_type="stars", reference_type="test", reference_id="seed",
        )
        first = await zarniki_exchange_v1.exchange(
            db, user_id=user, zarniki=2000, target="mora", action_id="http:exchange-1",
        )
        assert first["amount_received"] == 20000.0 and first["daily_cap"] is None
        replay = await zarniki_exchange_v1.exchange(
            db, user_id=user, zarniki=2000, target="mora", action_id="http:exchange-1",
        )
        assert replay["idempotent_replay"] and replay["operation_id"] == first["operation_id"]
        # A pre-upgrade exhausted quota cannot block either target.
        await usage_repo.add_usage_today(db, user, 50)
        second = await zarniki_exchange_v1.exchange(db, user_id=user, zarniki=1000, target="diamonds", action_id="chat:split")
        assert second["amount_received"] == 10
        try:
            await zarniki_exchange_v1.exchange(db, user_id=user, zarniki=49, target="mora", action_id="http:exchange-1")
        except Exception:
            pass
        else:
            raise AssertionError("same idempotency key accepted a different quote")
        from core.economy_contract import InsufficientBalance
        try:
            await zarniki_exchange_v1.exchange(db,user_id=user,zarniki=2001,target="mora",action_id="too-poor")
        except InsufficientBalance:
            pass
        else:
            raise AssertionError("unlimited exchange spent more than the balance")
        held_user = 976202
        held_credit = await economy_ledger.apply_balance_change(
            db, held_user, {"zarniki": 50}, reason_code="stars_purchase",
            idempotency_key="hold-zarniki", source_type="stars", reference_type="test", reference_id="hold",
        )
        await star_payments_v1.record_credit(
            db, charge_id="hold-charge", user_id=held_user, stars=5, zarniki=50,
            payload="zarniki:v1:c:5:50", payload_version="v1", operation_id=held_credit.operation_id,
        )
        await star_payments_v1.mark_review(db, "hold-charge")
        try:
            await zarniki_exchange_v1.exchange(db, user_id=held_user, zarniki=1, target="mora", action_id="held")
        except zarniki_exchange_v1.ZarnikiExchangeConflict:
            pass
        else:
            raise AssertionError("payment-review state did not freeze premium exchange")
        async with db.execute("SELECT user_balance_mora,user_balance_diamonds,user_balance_zarniki FROM users WHERE user_tg_id=?", (user,)) as cursor:
            balances = await cursor.fetchone()
        assert tuple(float(value) for value in balances) == (20000.0, 10.0, 2000.0)
        policy = await zarniki_exchange_v1.policy(db, user_id=user)
        from core.zarniki_exchange_v1 import EXCHANGE_ROUTES
        from core.skins_v3 import ESSENCE_PACKS, purchased_essence
        assert policy['remaining_today'] is None and policy['daily_cap'] is None
        routes = {route['id']: route for route in policy['routes']}
        assert {key: routes[key]['rate'] for key in EXCHANGE_ROUTES} == {key: str(value) for key, value in EXCHANGE_ROUTES.items()}
        assert routes['essence']['packs'] == [{'zarniki': n, 'amount': purchased_essence(n)} for n in ESSENCE_PACKS]
        # Quota is explicitly UTC even if a deployment/session uses another zone.
        await db.execute("SET LOCAL TIME ZONE 'Pacific/Kiritimati'")
        assert (await zarniki_exchange_v1.policy(db, user_id=user))['remaining_today'] is None
        await usage_repo.add_usage_today(db, 976203, 7)
        async with db.execute("SELECT utc_date=(NOW() AT TIME ZONE 'UTC')::date FROM zarniki_exchange_usage_v1 WHERE user_id=976203") as cursor:
            assert (await cursor.fetchone())[0]
    finally:
        await transaction.rollback()
        await conn.close()
    print("OK: Zarniki v1 PostgreSQL atomic debit/credit above old cap, replay, cross-target conversion and payment hold")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", type=local_dsn, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.dsn))
