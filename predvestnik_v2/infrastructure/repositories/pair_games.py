"""Доступ к данным игр вдвоём в личной переписке (S29a). Правила — core/pair_games.py, порядок действий — services/pair_games.py.

Строка партии — заодно и журнал ставки: сколько жетонов, из какого фонда, списаны ли (held) и выплачены ли (settled).
Связь с business_connections намеренно без внешнего ключа: отключение бота не должно стереть партию с замороженными
жетонами — сервис сначала возвращает ставки, потом связь удаляется.
"""
from __future__ import annotations

import json

_COLUMNS = ("id, kind, connection_id, chat_id, message_id, owner_id, partner_id, stake, funds, status, state, winner, held, "
            "settled, names, updated_at")


async def _ready(db) -> bool:
    async with db.execute("SELECT to_regclass('pair_games') IS NOT NULL") as c:
        row = await c.fetchone()
    return bool(row and row[0])


async def ensure_schema(db) -> None:
    if await _ready(db):
        return
    async with db.connection.transaction():
        await db.execute("SELECT pg_advisory_xact_lock(hashtextextended('ensure_schema:pair_games', 0))")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pair_games (
                id BIGSERIAL PRIMARY KEY,
                kind TEXT NOT NULL CHECK (kind IN ('rps', 'dice', 'ttt')),
                connection_id TEXT NOT NULL,
                chat_id BIGINT NOT NULL,
                message_id BIGINT,
                owner_id BIGINT NOT NULL,
                partner_id BIGINT NOT NULL,
                stake BIGINT NOT NULL DEFAULT 0 CHECK (stake >= 0),
                funds TEXT CHECK (funds IN ('bonus', 'redeemable')),
                status TEXT NOT NULL DEFAULT 'invited'
                    CHECK (status IN ('invited', 'playing', 'finished', 'declined', 'cancelled', 'expired')),
                state JSONB NOT NULL DEFAULT '{}'::jsonb,
                winner TEXT,
                held BOOLEAN NOT NULL DEFAULT FALSE,
                settled BOOLEAN NOT NULL DEFAULT FALSE,
                names JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_pair_games_open ON pair_games (updated_at) WHERE status IN ('invited', 'playing')")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_pair_games_connection ON pair_games (connection_id) WHERE status IN ('invited', 'playing')")


def _row(r) -> dict:
    load = lambda v: json.loads(v) if isinstance(v, str) else (v or {})  # noqa: E731
    return {"id": int(r[0]), "kind": r[1], "connection_id": r[2], "chat_id": int(r[3]), "message_id": int(r[4]) if r[4] else None,
            "owner_id": int(r[5]), "partner_id": int(r[6]), "stake": int(r[7]), "funds": r[8], "status": r[9], "state": load(r[10]),
            "winner": r[11], "held": bool(r[12]), "settled": bool(r[13]), "names": load(r[14]), "updated_at": r[15]}


async def create(db, *, kind: str, connection_id: str, chat_id: int, owner_id: int, partner_id: int, stake: int,
                 funds: str | None, state: dict, names: dict) -> int:
    async with db.execute(
        "INSERT INTO pair_games (kind, connection_id, chat_id, owner_id, partner_id, stake, funds, state, names) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?::jsonb, ?::jsonb) RETURNING id",
        (kind, str(connection_id), int(chat_id), int(owner_id), int(partner_id), int(stake), funds,
         json.dumps(state, ensure_ascii=False), json.dumps(names, ensure_ascii=False)),
    ) as c:
        return int((await c.fetchone())[0])


async def set_message(db, game_id: int, message_id: int) -> None:
    await db.execute("UPDATE pair_games SET message_id = ? WHERE id = ?", (int(message_id), int(game_id)))


async def get(db, game_id: int, *, lock: bool = False) -> dict | None:
    async with db.execute(f"SELECT {_COLUMNS} FROM pair_games WHERE id = ?" + (" FOR UPDATE" if lock else ""), (int(game_id),)) as c:
        row = await c.fetchone()
    return _row(row) if row else None


async def save(db, game_id: int, *, status: str, state: dict, winner: str | None = None, held: bool | None = None,
               settled: bool | None = None) -> None:
    await db.execute(
        "UPDATE pair_games SET status = ?, state = ?::jsonb, winner = COALESCE(?, winner), held = COALESCE(?, held), "
        "settled = COALESCE(?, settled), updated_at = NOW() WHERE id = ?",
        (status, json.dumps(state, ensure_ascii=False), winner, held, settled, int(game_id)),
    )


async def stale_ids(db, hours: int, limit: int = 50) -> list[int]:
    async with db.execute("SELECT id FROM pair_games WHERE status IN ('invited', 'playing') AND updated_at < NOW() - make_interval(hours => ?) "
                          "ORDER BY updated_at LIMIT ?", (int(hours), int(limit))) as c:
        return [int(r[0]) for r in await c.fetchall()]


async def open_ids_for_connection(db, connection_id: str) -> list[int]:
    async with db.execute("SELECT id FROM pair_games WHERE connection_id = ? AND status IN ('invited', 'playing')", (str(connection_id),)) as c:
        return [int(r[0]) for r in await c.fetchall()]


async def forget_finished(db, days: int = 30) -> None:
    """Партия — единственная запись о том, что жетоны перешли между игроками, поэтому строка остаётся навсегда;
    через месяц из неё стираются только имена."""
    await db.execute("UPDATE pair_games SET names = '{}'::jsonb WHERE status NOT IN ('invited', 'playing') AND names <> '{}'::jsonb "
                     "AND updated_at < NOW() - make_interval(days => ?)", (int(days),))
