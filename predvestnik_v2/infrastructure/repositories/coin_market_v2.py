"""V2 persistence. Never touches legacy exchange tables or commits caller work."""

from __future__ import annotations

import json
from dataclasses import asdict

from core.coin_market_v2 import Book, Coin, PriceState, Short


def decode(value):
    return json.loads(value) if isinstance(value, str) else value


async def ensure_tables(db):
    await db.connection.execute("""
    CREATE TABLE IF NOT EXISTS coin_market_v2_coins (
      id TEXT PRIMARY KEY, owner_id BIGINT REFERENCES users(user_tg_id),
      name TEXT NOT NULL, name_key TEXT NOT NULL UNIQUE, ticker TEXT NOT NULL UNIQUE,
      icon TEXT NOT NULL, character TEXT NOT NULL, group_key TEXT NOT NULL,
      base NUMERIC(30,0) NOT NULL CHECK(base>=100),
      supply BIGINT NOT NULL CHECK(supply>0), loan_pool BIGINT NOT NULL CHECK(loan_pool>=0 AND loan_pool<=supply),
      reserve NUMERIC(30,0) NOT NULL CHECK(reserve>=0), insurance NUMERIC(30,0) NOT NULL CHECK(insurance>=0),
      held BIGINT NOT NULL DEFAULT 0 CHECK(held>=0), borrowed BIGINT NOT NULL DEFAULT 0 CHECK(borrowed>=0),
      price_state JSONB NOT NULL, rules TEXT NOT NULL, secret_id TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CHECK(held<=supply-loan_pool AND borrowed<=loan_pool),
      CHECK(reserve>=CEIL(held::numeric*CEIL(base*3/2)/1000))
    );
    CREATE UNIQUE INDEX IF NOT EXISTS coin_market_v2_one_owner ON coin_market_v2_coins(owner_id) WHERE owner_id IS NOT NULL;
    ALTER TABLE coin_market_v2_coins ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT '';
    CREATE TABLE IF NOT EXISTS coin_market_v2_accounts (
      coin_id TEXT NOT NULL REFERENCES coin_market_v2_coins(id), user_id BIGINT NOT NULL REFERENCES users(user_tg_id),
      units BIGINT NOT NULL DEFAULT 0 CHECK(units>=0), cost NUMERIC(30,0) NOT NULL DEFAULT 0 CHECK(cost>=0),
      PRIMARY KEY(coin_id,user_id), CHECK(units>0 OR cost=0)
    );
    CREATE TABLE IF NOT EXISTS coin_market_v2_shorts (
      id TEXT PRIMARY KEY, coin_id TEXT NOT NULL REFERENCES coin_market_v2_coins(id),
      user_id BIGINT NOT NULL REFERENCES users(user_tg_id), payload JSONB NOT NULL,
      opened_tick BIGINT NOT NULL, closed_tick BIGINT,
      CHECK(closed_tick IS NULL OR closed_tick>=opened_tick)
    );
    CREATE UNIQUE INDEX IF NOT EXISTS coin_market_v2_one_short ON coin_market_v2_shorts(coin_id,user_id) WHERE closed_tick IS NULL;
    CREATE TABLE IF NOT EXISTS coin_market_v2_receipts (
      user_id BIGINT NOT NULL REFERENCES users(user_tg_id), action_id TEXT NOT NULL,
      fingerprint TEXT NOT NULL, response JSONB NOT NULL,
      operation_id TEXT REFERENCES economic_operations(id), created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      PRIMARY KEY(user_id,action_id)
    );
    CREATE TABLE IF NOT EXISTS coin_market_v2_events (
      user_id BIGINT NOT NULL, action_id TEXT NOT NULL, coin_id TEXT NOT NULL REFERENCES coin_market_v2_coins(id),
      wallet NUMERIC(30,0) NOT NULL, reserve NUMERIC(30,0) NOT NULL,
      insurance NUMERIC(30,0) NOT NULL, escrow NUMERIC(30,0) NOT NULL,
      burned NUMERIC(30,0) NOT NULL CHECK(burned>=0), treasury NUMERIC(30,0) NOT NULL DEFAULT 0,
      FOREIGN KEY(user_id,action_id) REFERENCES coin_market_v2_receipts(user_id,action_id),
      PRIMARY KEY(user_id,action_id), CHECK(wallet+reserve+insurance+escrow+burned+treasury=0)
    );
    CREATE TABLE IF NOT EXISTS coin_market_v2_ticks (
      coin_id TEXT NOT NULL REFERENCES coin_market_v2_coins(id), tick BIGINT NOT NULL,
      price NUMERIC(30,0) NOT NULL CHECK(price>0), PRIMARY KEY(coin_id,tick)
    );
    CREATE TABLE IF NOT EXISTS coin_market_v2_favorites (
      user_id BIGINT NOT NULL REFERENCES users(user_tg_id), coin_id TEXT NOT NULL REFERENCES coin_market_v2_coins(id),
      PRIMARY KEY(user_id,coin_id)
    );
    CREATE TABLE IF NOT EXISTS coin_market_v2_visits (
      user_id BIGINT PRIMARY KEY REFERENCES users(user_tg_id), snapshot JSONB NOT NULL
    );
    CREATE TABLE IF NOT EXISTS coin_market_v2_fund (
      singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK(singleton),
      mora NUMERIC(30,0) NOT NULL CHECK(mora>=0), diamonds NUMERIC(30,0) NOT NULL DEFAULT 0 CHECK(diamonds>=0)
    );
    CREATE TABLE IF NOT EXISTS coin_market_v2_funding (
      id TEXT PRIMARY KEY, source TEXT NOT NULL, mora NUMERIC(30,0) NOT NULL CHECK(mora>0),
      metadata JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE OR REPLACE FUNCTION coin_market_v2_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'immutable coin market record'; END $$;
    DO $$ DECLARE t text; BEGIN
      FOREACH t IN ARRAY ARRAY['coin_market_v2_receipts','coin_market_v2_events','coin_market_v2_ticks','coin_market_v2_funding'] LOOP
        IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid=to_regclass(t) AND tgname='cm2_immutable') THEN
          EXECUTE format('CREATE TRIGGER cm2_immutable BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION coin_market_v2_immutable()',t);
        END IF;
      END LOOP;
    END $$;
    """)


async def ready(db):
    return bool(
        await db.connection.fetchval("SELECT to_regclass('coin_market_v2_coins')")
    )


async def user_lock(db, user_id):
    # Receipt serialization is shared by all coins and creation requests.
    await db.connection.execute("SELECT pg_advisory_xact_lock($1::bigint)", user_id)


async def catalogue_lock(db):
    # Caller holds the transaction through capacity check and insertion.
    await db.connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended('cm2-catalogue',0))"
    )


async def coin_count(db):
    return await db.connection.fetchval("SELECT count(*) FROM coin_market_v2_coins")


async def maintenance_coin_ids(db):
    return [row["id"] for row in await db.connection.fetch(
        "SELECT id FROM coin_market_v2_coins ORDER BY id"
    )]


async def require_active(db, user_id):
    row = await db.connection.fetchrow(
        "SELECT deleted_at FROM users WHERE user_tg_id=$1", user_id
    )
    if not row or row["deleted_at"] is not None:
        from core.coin_market_v2 import MarketError

        raise MarketError("Аккаунт недоступен для новых сделок.")


async def has_obligations(db, user_id):
    if not await ready(db):
        return False
    return bool(
        await db.connection.fetchval(
            """SELECT EXISTS(SELECT 1 FROM coin_market_v2_accounts WHERE user_id=$1 AND units>0)
           OR EXISTS(SELECT 1 FROM coin_market_v2_shorts WHERE user_id=$1 AND closed_tick IS NULL)""",
            user_id,
        )
    )


async def load(db, coin_id, *, lock=False):
    row = await db.connection.fetchrow(
        "SELECT * FROM coin_market_v2_coins WHERE id=$1"
        + (" FOR UPDATE" if lock else ""),
        coin_id,
    )
    return dict(row) if row else None


def unpack(row):
    coin = Coin(row["id"], int(row["base"]), int(row["supply"]), int(row["loan_pool"]))
    book = Book(
        *(int(row[key]) for key in ("reserve", "held", "borrowed", "insurance"))
    )
    state = PriceState(**decode(row["price_state"]))
    return coin, book, state


async def save(db, coin_id, book, state):
    await db.connection.execute(
        """UPDATE coin_market_v2_coins SET reserve=$2,held=$3,borrowed=$4,insurance=$5,price_state=$6::jsonb WHERE id=$1""",
        coin_id,
        book.reserve,
        book.held,
        book.borrowed,
        book.insurance,
        json.dumps(asdict(state)),
    )


async def account(db, coin_id, user_id):
    row = await db.connection.fetchrow(
        "SELECT units,cost FROM coin_market_v2_accounts WHERE coin_id=$1 AND user_id=$2",
        coin_id,
        user_id,
    )
    return (int(row["units"]), int(row["cost"])) if row else (0, 0)


async def put_account(db, coin_id, user_id, units, cost):
    await db.connection.execute(
        """INSERT INTO coin_market_v2_accounts(coin_id,user_id,units,cost) VALUES($1,$2,$3,$4)
       ON CONFLICT(coin_id,user_id) DO UPDATE SET units=EXCLUDED.units,cost=EXCLUDED.cost""",
        coin_id,
        user_id,
        units,
        cost,
    )


async def replay(db, user_id, action_id):
    return await db.connection.fetchrow(
        "SELECT fingerprint,response FROM coin_market_v2_receipts WHERE user_id=$1 AND action_id=$2",
        user_id,
        action_id,
    )


async def receipt(
    db, user_id, action_id, fingerprint, response, operation_id, coin_id, flow
):
    await db.connection.execute(
        "INSERT INTO coin_market_v2_receipts(user_id,action_id,fingerprint,response,operation_id) VALUES($1,$2,$3,$4::jsonb,$5)",
        user_id,
        action_id,
        fingerprint,
        json.dumps(response),
        operation_id,
    )
    await db.connection.execute(
        """INSERT INTO coin_market_v2_events(user_id,action_id,coin_id,wallet,reserve,insurance,escrow,burned,treasury)
      VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
        user_id,
        action_id,
        coin_id,
        flow.wallet,
        flow.reserve,
        flow.insurance,
        flow.escrow,
        flow.burned,
        flow.treasury,
    )


async def active_shorts(db, coin_id):
    rows = await db.connection.fetch(
        "SELECT * FROM coin_market_v2_shorts WHERE coin_id=$1 AND closed_tick IS NULL ORDER BY user_id,id",
        coin_id,
    )
    return [dict(row) for row in rows]


def short_payload(row):
    return Short(**decode(row["payload"]))


async def reconcile(db, row, book):
    held = await db.connection.fetchval(
        "SELECT COALESCE(sum(units),0) FROM coin_market_v2_accounts WHERE coin_id=$1",
        row["id"],
    )
    positions = await active_shorts(db, row["id"])
    borrowed = sum(short_payload(p).units for p in positions)
    if int(held) != book.held or borrowed != book.borrowed:
        raise RuntimeError("Coin market accounting mismatch")


async def current_tick(db):
    return int(
        await db.connection.fetchval(
            "SELECT FLOOR(EXTRACT(EPOCH FROM clock_timestamp())/300)::bigint"
        )
    )


async def insert_coin(
    db,
    *,
    coin,
    book,
    state,
    owner_id,
    name,
    ticker,
    icon,
    character,
    group,
    rules,
    secret_id,
    description="",
):
    await db.connection.execute(
        """INSERT INTO coin_market_v2_coins
      (id,owner_id,name,name_key,ticker,icon,character,group_key,base,supply,loan_pool,reserve,insurance,held,borrowed,price_state,rules,secret_id,description)
      VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16::jsonb,$17,$18,$19)""",
        coin.key,
        owner_id,
        name,
        name.casefold(),
        ticker,
        icon,
        character,
        group,
        coin.base,
        coin.supply,
        coin.loan_pool,
        book.reserve,
        book.insurance,
        book.held,
        book.borrowed,
        json.dumps(asdict(state)),
        rules,
        secret_id,
        description,
    )
    await db.connection.execute(
        "INSERT INTO coin_market_v2_ticks(coin_id,tick,price) VALUES($1,$2,$3)",
        coin.key,
        state.tick,
        state.price,
    )


async def put_short(db, *, position_id, coin_id, user_id, position, tick):
    await db.connection.execute(
        "INSERT INTO coin_market_v2_shorts(id,coin_id,user_id,payload,opened_tick) VALUES($1,$2,$3,$4::jsonb,$5)",
        position_id,
        coin_id,
        user_id,
        json.dumps(asdict(position)),
        tick,
    )


async def finish_short(db, position_id, tick):
    await db.connection.execute(
        "UPDATE coin_market_v2_shorts SET closed_tick=$2 WHERE id=$1 AND closed_tick IS NULL",
        position_id,
        tick,
    )


async def lock_fund(db):
    return await db.connection.fetchrow(
        "SELECT * FROM coin_market_v2_fund WHERE singleton=TRUE FOR UPDATE"
    )


async def peek_fund(db):
    return await db.connection.fetchrow('SELECT * FROM coin_market_v2_fund WHERE singleton=TRUE')


async def convert_deposit(db, mora, diamonds_hundredths):
    await db.connection.execute(
        "UPDATE coin_market_v2_fund SET mora=mora-$1,diamonds=diamonds+$2 WHERE singleton=TRUE",
        mora,
        diamonds_hundredths,
    )


async def rows(db, user_id):
    return [
        dict(row)
        for row in await db.connection.fetch(
            """SELECT c.*,COALESCE(a.units,0) user_units,COALESCE(a.cost,0) user_cost,
       (f.coin_id IS NOT NULL) favorite FROM coin_market_v2_coins c
       LEFT JOIN coin_market_v2_accounts a ON a.coin_id=c.id AND a.user_id=$1
       LEFT JOIN coin_market_v2_favorites f ON f.coin_id=c.id AND f.user_id=$1 ORDER BY c.owner_id NULLS FIRST,c.created_at,c.id""",
            user_id,
        )
    ]


async def user_shorts(db, user_id):
    return [
        dict(row)
        for row in await db.connection.fetch(
            "SELECT * FROM coin_market_v2_shorts WHERE user_id=$1 AND closed_tick IS NULL ORDER BY opened_tick DESC",
            user_id,
        )
    ]


async def history(db, coin_id, start):
    return [
        dict(row)
        for row in await db.connection.fetch(
            "SELECT tick,price FROM coin_market_v2_ticks WHERE coin_id=$1 AND tick>=$2 ORDER BY tick",
            coin_id,
            start,
        )
    ]


async def market_changes(db, since):
    """One row per coin: the earliest published tick inside the change window."""
    rows = await db.connection.fetch(
        """SELECT DISTINCT ON (coin_id) coin_id,tick,price
       FROM coin_market_v2_ticks WHERE tick>=$1 ORDER BY coin_id,tick""",
        since,
    )
    return {
        row["coin_id"]: {"tick": int(row["tick"]), "price": int(row["price"])}
        for row in rows
    }


async def user_trade_markers(db, user_id, coin_id, *, limit=40):
    """The player's own buy/sell ticks for the chart. Receipts are append-only."""
    return [
        dict(row)
        for row in await db.connection.fetch(
            """SELECT response->>'tick' tick,response->>'price' price,response->>'side' side
       FROM coin_market_v2_receipts
       WHERE user_id=$1 AND response->>'coin_id'=$2 AND response->>'side' IN ('buy','sell')
       ORDER BY (response->>'tick')::bigint DESC LIMIT $3""",
            user_id,
            coin_id,
            limit,
        )
    ]


async def favorite(db, user_id, coin_id, enabled):
    if enabled:
        await db.connection.execute(
            "INSERT INTO coin_market_v2_favorites(user_id,coin_id) VALUES($1,$2) ON CONFLICT DO NOTHING",
            user_id,
            coin_id,
        )
    else:
        await db.connection.execute(
            "DELETE FROM coin_market_v2_favorites WHERE user_id=$1 AND coin_id=$2",
            user_id,
            coin_id,
        )


async def visit(db, user_id, snapshot):
    await user_lock(db, user_id)
    old = await db.connection.fetchval(
        "SELECT snapshot FROM coin_market_v2_visits WHERE user_id=$1", user_id
    )
    await db.connection.execute(
        "INSERT INTO coin_market_v2_visits(user_id,snapshot) VALUES($1,$2::jsonb) ON CONFLICT(user_id) DO UPDATE SET snapshot=EXCLUDED.snapshot",
        user_id,
        json.dumps(snapshot),
    )
    return decode(old) if old else None


async def append_tick(db, coin_id, state):
    await db.connection.execute(
        "INSERT INTO coin_market_v2_ticks(coin_id,tick,price) VALUES($1,$2,$3)",
        coin_id,
        state.tick,
        state.price,
    )


async def balances(db, user_id):
    row = await db.connection.fetchrow(
        "SELECT GREATEST(0,u.user_balance_mora-COALESCE(r.reserved_mora,0)) user_balance_mora,u.user_balance_zarniki,u.user_balance_diamonds FROM users u LEFT JOIN user_reserve r ON r.user_id=u.user_tg_id WHERE u.user_tg_id=$1",
        user_id,
    )
    return (
        {
            "mora": str(row["user_balance_mora"]),
            "zarniki": str(row["user_balance_zarniki"]),
            "diamonds": str(row["user_balance_diamonds"]),
        }
        if row
        else {}
    )


async def edit_metadata(db,coin_id,icon,description):
    await db.connection.execute('UPDATE coin_market_v2_coins SET icon=$2,description=$3 WHERE id=$1',coin_id,icon,description)


async def bootstrap(db, coins, secret_id, rules, tick, *, source, issuance_authorization=None):
    # Initial capital is an explicit, owner-approved issuance, not a transfer
    # from player wallets and never an automatic response to reserve depletion.
    if (not isinstance(issuance_authorization, str)
            or not 8 <= len(issuance_authorization) <= 200):
        raise ValueError("Explicit one-time 120000 Mora issuance authorization required")
    if len(coins) != 6 or len({c[0] for c in coins}) != 6:
        raise ValueError("Initial issuance funds exactly six distinct system coins")
    async with db.connection.transaction():
        await db.connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended('cm2-bootstrap',0))"
        )
        await catalogue_lock(db)
        if await db.connection.fetchval(
            "SELECT 1 FROM coin_market_v2_funding WHERE id='initial-v2'"
        ):
            return False
        if await db.connection.fetchval("SELECT count(*) FROM coin_market_v2_coins"):
            raise RuntimeError("Cannot bootstrap over existing coins")
        await db.connection.execute(
            "INSERT INTO coin_market_v2_funding(id,source,mora,metadata) VALUES('initial-v2',$1,120000000000,$2::jsonb)",
            source,
            json.dumps(
                {"kind": "one_time_system_issuance", "currency": "mora",
                 "amount": "120000", "authorization": issuance_authorization,
                 "per_coin_mora": 15000, "conversion_fund_mora": 30000, "rules": rules}
            ),
        )
        await db.connection.execute(
            "INSERT INTO coin_market_v2_fund(singleton,mora) VALUES(TRUE,30000000000)"
        )
        for key, name, ticker, character, group in coins:
            coin = Coin(key, 20_000)
            await insert_coin(
                db,
                coin=coin,
                book=Book(15_000_000_000),
                state=PriceState(tick, coin.base),
                owner_id=None,
                name=name,
                ticker=ticker,
                icon="coin",
                character=character,
                group=group,
                rules=rules,
                secret_id=secret_id,
            )
        return True
