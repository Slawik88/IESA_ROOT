"""Gentle pet reminder: pure rules always; with PG_TEST_DSN also the SQL day counter
against the pure model on random visit histories, the show claim and the pets hook."""
from __future__ import annotations

import asyncio
import os
import random
import sys
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.pet_nudge_v1 import COOLDOWN_DAYS, MAX_SHOWS, STREAK_DAYS, NudgeState, card, due, visit

D0 = date(2026, 10, 1)


def pure() -> None:
    s = NudgeState()
    for i in range(STREAK_DAYS - 1):
        s = visit(visit(s, D0 + timedelta(i), False), D0 + timedelta(i), False)  # two visits a day count once
        assert not due(s, D0 + timedelta(i))
    day = D0 + timedelta(STREAK_DAYS - 1)
    s = visit(s, day, False)
    assert s.streak == STREAK_DAYS and due(s, day), "fourth app day in a row without pets"
    assert not due(visit(s, day, True), day), "opening pets the same day cancels"
    gap = visit(s, day + timedelta(2), False)
    assert gap.streak == 1, "a missed day restarts the count"
    pets_day = visit(visit(NudgeState(), D0, True), D0 + timedelta(1), False)
    assert pets_day.streak == 1
    shown = NudgeState(last_day=day, streak=9, shown_on=day, shows=1)
    assert not due(shown, day + timedelta(COOLDOWN_DAYS - 1)) and due(shown, day + timedelta(COOLDOWN_DAYS))
    assert not due(NudgeState(last_day=day, streak=9, shows=MAX_SHOWS), day)
    assert card(None, True)["title"] == "Здесь живут питомцы"
    named = card({"name": "Тень", "icon": "🦊"}, False)
    assert named["title"] == "Тень скучает по вам" and named["icon"] == "🦊" and len(named["tiles"]) == 3
    for c in (card(None, False), named):
        assert all(len(t["text"]) <= 60 for t in c["tiles"]), "tiles stay one line"


async def database(dsn: str) -> None:
    import asyncpg
    from infrastructure.pg_adapter import PGAdapter
    from infrastructure.repositories import pet_nudge_v1 as repo
    from services import pet_nudge_v1 as service

    schema = "pet_nudge_" + uuid4().hex[:10]
    conn = await asyncpg.connect(dsn)
    db = PGAdapter(conn)
    try:
        await conn.execute(f'CREATE SCHEMA "{schema}"')
        await conn.execute(f'SET search_path TO "{schema}"')
        await repo.ensure_tables(db)
        # SQL counter == pure model, on random histories. Day is moved by rewriting last_day.
        rng = random.Random(7)
        for user in range(1, 120):
            model = NudgeState()
            today = await conn.fetchval("SELECT (NOW() AT TIME ZONE 'UTC')::date")
            day = today - timedelta(days=60)
            for _ in range(rng.randint(1, 25)):
                day += timedelta(days=rng.choice((0, 0, 1, 1, 1, 2, 5)))
                pets = rng.random() < 0.25
                model = visit(model, day, pets)
                shift = (today - day).days   # pretend "today" is `day`
                await conn.execute("UPDATE pet_nudge_v1 SET last_day = last_day + $2::int WHERE user_id=$1", user, shift)
                await repo.visit(db, user, pets)
                await conn.execute("UPDATE pet_nudge_v1 SET last_day = last_day - $2::int WHERE user_id=$1", user, shift)
                row = await conn.fetchrow("SELECT last_day,last_day_pets,streak FROM pet_nudge_v1 WHERE user_id=$1", user)
                assert (row["last_day"], row["last_day_pets"], row["streak"]) == (model.last_day, model.last_day_pets, model.streak), (user, model, dict(row))
        # Show claim: once per day even under parallel requests; pets screen resets.
        uid = 999
        today = await conn.fetchval("SELECT (NOW() AT TIME ZONE 'UTC')::date")
        await conn.execute("INSERT INTO pet_nudge_v1(user_id,last_day,streak) VALUES($1,$2,$3)", uid, today - timedelta(1), STREAK_DAYS - 1)
        conns = [await asyncpg.connect(dsn) for _ in range(5)]
        try:
            for c in conns:
                await c.execute(f'SET search_path TO "{schema}"')
            await repo.visit(db, uid, False)
            claims = await asyncio.gather(*(repo.claim_show(PGAdapter(c), uid) for c in conns))
        finally:
            for c in conns:
                await c.close()
        assert sum(claims) == 1, claims
        assert (await service.app_opened(db, uid)) == {"show": False}, "not twice a day"
        uid2 = 1000
        await conn.execute("CREATE TABLE pets(id BIGSERIAL PRIMARY KEY, owner_id BIGINT, name TEXT, species_id TEXT, created_at TIMESTAMPTZ DEFAULT NOW())")
        await conn.execute("CREATE TABLE system_flags(key TEXT PRIMARY KEY, enabled BOOLEAN NOT NULL DEFAULT FALSE)") if not await conn.fetchval("SELECT to_regclass('system_flags')") else None
        await conn.execute("INSERT INTO pets(owner_id,name,species_id) VALUES($1,NULL,'moss_cat')", uid2)
        await conn.execute("INSERT INTO pet_nudge_v1(user_id,last_day,streak) VALUES($1,$2,$3)", uid2, today - timedelta(1), STREAK_DAYS - 1)
        await service.pets_opened(db, uid2)
        assert (await service.app_opened(db, uid2)) == {"show": False}, "pets visit today resets"
        await conn.execute("UPDATE pet_nudge_v1 SET last_day=$2, last_day_pets=FALSE, streak=$3 WHERE user_id=$1", uid2, today - timedelta(1), STREAK_DAYS - 1)
        shown = await service.app_opened(db, uid2)
        assert shown["show"] and shown["title"] == "Моховой кот скучает по вам" and shown["icon"] == "🐈", shown
        await service.answered(db, uid2, "later")
        assert await conn.fetchval("SELECT answer FROM pet_nudge_v1 WHERE user_id=$1", uid2) == "later"
    finally:
        await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await conn.close()


if __name__ == "__main__":
    pure()
    dsn = os.environ.get("PG_TEST_DSN")
    if dsn:
        asyncio.run(database(dsn))
    print("PASS: pet reminder — 4-day count, resets, cooldown, limit, copy" + (", SQL = model, one show per day" if dsn else ""))
