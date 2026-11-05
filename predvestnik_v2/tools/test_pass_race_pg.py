#!/usr/bin/env python3
"""Real PostgreSQL proof of «Гонка за Пропуском» (S28b, core/pass_race.py): the race is money, so every rule is shown here.

Run on a disposable loopback database (it commits: places are taken from parallel connections):
    BOT_TOKEN=1:x PYTHONPATH=. python tools/test_pass_race_pg.py --dsn postgresql://…@127.0.0.1:55432/<empty db>

Proves: off by default; the switch records the start; a player at level 40 before the start is outside the race;
six simultaneous crossings get four places in server-time order; the owner hears about each place exactly once
(with tg://user?id=…); «проверен» queues the winner's message only with consent; a second «выплачено» changes nothing;
a rejection hands the place to the next player and tells the owner; a pause keeps the start; a failure of the race
never takes experience away.
"""
from __future__ import annotations

import argparse
import asyncio
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("DATABASE_URL", "postgresql://unused@127.0.0.1/unused")

from core import league_pass as pass_rules, pass_race as rules, seasons  # noqa: E402
from infrastructure.pg_adapter import PGAdapter  # noqa: E402

OWNER = 982900
EARLY = 982901                                    # at level 40 before the start
RACERS = [982910 + n for n in range(6)]           # cross at the same moment
LATE = 982920                                     # crosses while the race is paused
FULL = pass_rules.LEVELS * pass_rules.XP_PER_LEVEL


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []
        self.down = False

    async def send_message(self, chat_id, text, **_):
        if self.down:
            raise ConnectionError("Telegram is unreachable")
        self.sent.append((int(chat_id), text))


async def setup(db) -> None:
    await db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS bot_rank INTEGER")   # created at bot start, not by init_db
    old = datetime.now(timezone.utc) - timedelta(days=60)
    for user in (OWNER, EARLY, LATE, *RACERS):
        await db.execute("INSERT INTO users (user_tg_id, user_tg_username) VALUES (?, ?) ON CONFLICT DO NOTHING", (user, f"racer{user}"))
        await db.execute("INSERT INTO user_chat_stats(user_tg_id, chat_tg_id, joined_at, membership_since) VALUES (?,1,?,?) "
                         "ON CONFLICT DO NOTHING", (user, old.replace(tzinfo=None), old))
    await db.execute("UPDATE users SET bot_rank = 6 WHERE user_tg_id = ?", (OWNER,))
    await db.execute("DELETE FROM pass_race_entries")
    await db.execute("DELETE FROM pass_race_runs")
    await db.execute("UPDATE system_flags SET enabled = 0 WHERE key = ?", (rules.FLAG,))


async def xp_to(db, user: int, target: int, tag: str) -> int:
    from services import league_pass
    from infrastructure.repositories import league_pass as repo
    have = await repo.xp(db, user_id=user, season=seasons.season_number(datetime.now(timezone.utc)))
    return await league_pass.add_xp(db, user_id=user, source="proof", event_id=f"{tag}:{user}", xp=target - have, casual=False)


async def proof(db, bot: FakeBot) -> None:
    from services import admin_security, feature_switches as fs, pass_race
    from infrastructure.repositories import dm_push as dm_repo, league_pass as pass_repo, pass_race as repo, system_flags
    season = seasons.season_number(datetime.now(timezone.utc))
    pass_race.ANNOUNCE_DELAY_S = 0.05

    # 1. Off by default: a crossing counts for nothing, the card shows nothing, «Функции» shows the event as off.
    assert not await pass_race.running(db)
    assert await xp_to(db, EARLY, FULL + 10, "early") > 0
    assert await pass_race.player_view(db) == {"running": False}
    assert (await fs.state(db, 0))["global"].get(rules.SWITCH) is not None, "the event row reads «выключено» until switched on"
    assert not await repo.entries(db, season)
    print("PASS off by default: no place, no line on the card, the switch row is off")

    # 2. The switch records the start (the flag and the season's run); the event row turns on.
    await fs.set_switch(db, 0, rules.SWITCH, True, actor_id=OWNER)
    race = await pass_race.running(db)
    assert race and race["season"] == season and race["started_by"] == OWNER
    assert rules.SWITCH not in (await fs.state(db, 0))["global"]
    started = race["started_at"]

    # 3. The player who was at level 40 before the start is outside the race, whatever experience comes later.
    await xp_to(db, EARLY, FULL + 900, "early-more")
    assert not await repo.entries(db, season), "a level reached before the start never counts"
    print("PASS switch-on records the start; a player at level 40 before it stays outside")

    # 4. Six players cross at the same moment from six connections: four places in the server's time order.
    for user in RACERS:
        await xp_to(db, user, FULL - 20, "near")
    assert not await repo.entries(db, season)

    async def cross(user: int) -> bool:
        from infrastructure.database import get_pool
        async with get_pool().acquire() as conn:
            other = PGAdapter(conn)
            async with conn.transaction():
                from services import league_pass
                return await league_pass.add_xp(other, user_id=user, source="proof", event_id=f"cross:{user}", xp=60, casual=False) == 60

    assert all(await asyncio.gather(*(cross(u) for u in RACERS)))
    rows = await repo.entries(db, season)
    assert sorted(int(r["user_id"]) for r in rows) == sorted(RACERS), rows
    times = [r["reached_at"] for r in rows]
    assert times == sorted(times) and len(set(times)) == len(times), "the race lock gives every crossing its own server moment"
    assert all(t >= started for t in times)
    seated = rules.seated(rows)
    assert [e["place"] for e in seated] == [1, 2, 3, 4] and [int(e["user_id"]) for e in seated] == [int(r["user_id"]) for r in rows[:4]]
    assert (await pass_race.player_view(db))["left"] == 0
    for user in RACERS:   # a repeat of the same result and further experience add no second entry
        await xp_to(db, user, FULL + 600, "after")
    assert len(await repo.entries(db, season)) == len(RACERS)
    print("PASS six simultaneous crossings: distinct server moments, places 1–4 by time, two in the queue")

    # 5. The owner hears about every place exactly once: background step plus the backstop sweep, no duplicates.
    await pass_race.drain()
    assert await pass_race.announce_pending(db) == 0
    await admin_security.drain()
    to_owner = [text for chat, text in bot.sent if chat == OWNER]
    assert len(to_owner) == rules.PLACES, to_owner
    first = seated[0]
    assert any(f"tg://user?id={first['user_id']}" in t and "Место <b>1 из 4</b>" in t and str(first["user_id"]) in t for t in to_owner)
    assert all("Выплачено" in t and "Отклонить" in t for t in to_owner), "the message says what to do"
    print("PASS the owner got one message per place with place, nick, id, time, tg://user link and the steps")

    # 6. «Проверен»: the winner's message goes through the shared queue, only with consent to Pass messages.
    one, two, three = (int(e["user_id"]) for e in seated[:3])
    queue = [int(r["user_id"]) for r in rows[4:]]
    result = await pass_race.mark(db, user_id=one, status=rules.VERIFIED, actor_id=OWNER)
    assert result["changed"] and result["player_told"] is False, "no consent: nothing queued, the admin says «напишите сами»"
    await dm_repo.set_consent(db, two, "pass", True)
    await dm_repo.touch_contact(db, two)
    result = await pass_race.mark(db, user_id=two, status=rules.VERIFIED, actor_id=OWNER)
    assert result["player_told"] is True
    async with db.execute("SELECT text FROM dm_push_outbox WHERE user_id = ? AND category = 'pass'", (two,)) as cur:
        queued = [r[0] for r in await cur.fetchall()]
    assert len(queued) == 1 and "Ты среди первых четырёх" in queued[0], queued
    print("PASS «проверен» queues «ты среди первых четырёх» only with consent")

    # 7. «Выплачено» once: the second press changes nothing and writes no second journal row.
    assert (await pass_race.mark(db, user_id=one, status=rules.PAID, actor_id=OWNER, note="подарок 50"))["changed"]
    again = await pass_race.mark(db, user_id=one, status=rules.PAID, actor_id=OWNER, note="ещё раз")
    assert again == {"changed": False, "status": rules.PAID, "player_told": None}
    async with db.execute("SELECT details->>'to', details->>'stars' FROM bot_admin_actions WHERE action = 'pass_race' AND user_id = ? "
                          "ORDER BY id", (one,)) as cur:
        journal = [tuple(r) for r in await cur.fetchall()]
    assert journal == [(rules.VERIFIED, "0"), (rules.PAID, str(rules.PRIZE_STARS))], journal
    for bad in ((one, rules.REJECTED), (queue[1], rules.VERIFIED), (one, "unknown")):
        try:
            await pass_race.mark(db, user_id=bad[0], status=bad[1], actor_id=OWNER)
        except pass_race.RaceError:
            pass
        else:
            raise AssertionError(f"{bad} must be refused")
    print("PASS a second «выплачено» is harmless; a paid place cannot be rejected; a queued player cannot be verified")

    # 8. A rejection hands the place on: the first in the queue becomes place 4 and the owner hears about that player.
    before = len([1 for chat, _ in bot.sent if chat == OWNER])
    assert (await pass_race.mark(db, user_id=three, status=rules.REJECTED, actor_id=OWNER, note="твинк"))["changed"]
    await admin_security.drain()
    seated = rules.seated(await repo.entries(db, season))
    assert three not in [int(e["user_id"]) for e in seated] and int(seated[-1]["user_id"]) == queue[0] and seated[-1]["place"] == 4
    news = [text for chat, text in bot.sent if chat == OWNER][before:]
    assert len(news) == 1 and f"tg://user?id={queue[0]}" in news[0], news
    try:
        await pass_race.mark(db, user_id=three, status=rules.VERIFIED, actor_id=OWNER)
    except pass_race.RaceError:
        pass
    else:
        raise AssertionError("a rejection is final")
    view = (await pass_race.admin_view(db))["seasons"][0]
    assert view["current"] and [e["place"] for e in view["entries"][:4]] == [1, 2, 3, 4] and view["left"] == 0
    print("PASS a rejection moves the next player into the place and tells the owner")

    # 9. A pause stops new places and keeps the start; the next switch-on in the season does not move it.
    await fs.set_switch(db, 0, rules.SWITCH, False, actor_id=OWNER)
    await xp_to(db, LATE, FULL - 10, "late-near")
    await xp_to(db, LATE, FULL + 10, "late")
    assert LATE not in [int(r["user_id"]) for r in await repo.entries(db, season)]
    assert (await pass_race.player_view(db)) == {"running": False}
    await fs.set_switch(db, 0, rules.SWITCH, True, actor_id=OWNER)
    assert (await repo.run(db, season))["started_at"] == started
    await pass_race.announce_pending(db)
    assert LATE not in [int(r["user_id"]) for r in await repo.entries(db, season)], "the sweep does not count a pass closed in a pause"
    print("PASS a pause counts no new places, keeps the original start, and the sweep does not bring the paused crossing back")

    # 10. A failure inside the race never takes the experience back.
    original = pass_race.on_reached

    async def broken(*_, **__):
        raise RuntimeError("race storage down")
    pass_race.on_reached = broken
    try:
        user = 982930
        await db.execute("INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (user,))
        await xp_to(db, user, FULL - 5, "fail-near")
        assert await xp_to(db, user, FULL + 5, "fail") == 10
        assert await pass_repo.xp(db, user_id=user, season=season) == FULL + 5
    finally:
        pass_race.on_reached = original
    assert user not in [int(r["user_id"]) for r in await repo.entries(db, season)]
    await pass_race.announce_pending(db)   # the sweep finds the crossing in the receipts
    found = {int(r["user_id"]): r for r in await repo.entries(db, season)}
    assert user in found and found[user]["recovered"] and found[user]["reached_at"] >= started
    print("PASS a broken race step leaves the experience in place, and the sweep records the place it missed")

    # 10b. Checked and paid places never move: an entry recorded later with an earlier time pushes only waiting ones.
    early = 982931
    await db.execute("INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (early,))
    async with db.connection.transaction():
        await repo.lock_race(db, season)
        await repo.add_entry(db, season=season, user_id=early, reached_at=started)
    seated = rules.seated(await repo.entries(db, season))
    ids = [int(e["user_id"]) for e in seated]
    assert len(seated) == rules.PLACES and one in ids and two in ids and ids[0] == early, seated
    print("PASS a paid or checked place is never pushed out (no fifth payout)")

    # 10c. Telegram down: the place is not marked «told», the next sweep tells the owner.
    bot.down = True
    holder = next(int(e["user_id"]) for e in seated if e["status"] == rules.PENDING and int(e["user_id"]) != early)
    await pass_race.mark(db, user_id=holder, status=rules.REJECTED, actor_id=OWNER, note="проверка отказа связи")
    waiting = [e for e in rules.seated(await repo.entries(db, season)) if e["owner_alerted_at"] is None]
    assert waiting, "the new holder is not marked as told while Telegram is down"
    bot.down = False
    before = len(bot.sent)
    assert await pass_race.announce_pending(db) >= 1 and len(bot.sent) > before
    assert all(e["owner_alerted_at"] is not None for e in rules.seated(await repo.entries(db, season)))
    print("PASS an owner message lost to Telegram is sent again by the next sweep")

    # 10d. The result that crossed the level is rolled back: no place, no message.
    ghost = 982932
    await db.execute("INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (ghost,))
    await xp_to(db, ghost, FULL - 5, "ghost-near")
    sent = len(bot.sent)
    try:
        async with db.connection.transaction():
            from services import league_pass
            await league_pass.add_xp(db, user_id=ghost, source="proof", event_id="ghost", xp=10, casual=False)
            raise RuntimeError("the game result failed after the experience")
    except RuntimeError:
        pass
    await pass_race.drain()
    await pass_race.announce_pending(db)
    assert ghost not in [int(r["user_id"]) for r in await repo.entries(db, season)] and len(bot.sent) == sent
    print("PASS a rolled-back result takes no place and sends nothing")

    # 11. The check card: account age, twins, unchecked games and bans — signals for the owner, nothing changes.
    card = await pass_race.check_card(db, user_id=one)
    assert card["account"]["ok"] and card["account"]["days"] >= 59 and card["ban"] == {"global": None, "blocked": None}
    assert set(card["unchecked"]) == {"rhythm", "minesweeper", "ranked_marked"} and isinstance(card["twins"], list)
    print("PASS the check card shows account age, twins, unchecked games and bans")

    # 12. A new season has no race of its own: the switch goes off by itself; the old season's unpaid places stay visible.
    next_start = seasons.season_bounds(season + 1)[0]
    await pass_race.announce_pending(db, now=next_start + timedelta(hours=1))
    assert not await system_flags.is_enabled(db, rules.FLAG)
    view = await pass_race.admin_view(db, now=next_start + timedelta(hours=1))
    assert [v["season"] for v in view["seasons"]] == [season + 1, season] and not view["seasons"][0]["entries"]
    left = next(e for e in view["seasons"][1]["entries"] if e["status"] == rules.VERIFIED)
    assert (await pass_race.mark(db, user_id=left["user_id"], status=rules.PAID, actor_id=OWNER, season=season,
                                 now=next_start + timedelta(hours=1)))["changed"], "a winner of the old season is still paid"
    print("PASS the switch closes with the season; places of the old season are still checked and paid")


async def run(dsn: str) -> None:
    if urlparse(dsn).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("only a loopback PostgreSQL DSN is allowed: this test deletes race rows")
    os.environ["DATABASE_URL"] = dsn
    from bot.core.database import init_db
    from bot.startup_schema import ensure_runtime_schema
    from infrastructure.database import create_pool, get_pool
    from services import admin_security, dm_push
    from infrastructure.repositories import dm_push as dm_repo
    await create_pool()
    await init_db()
    await ensure_runtime_schema(get_pool())
    bot = FakeBot()
    admin_security.use_bot(lambda: bot)
    async with get_pool().acquire() as connection:
        db = PGAdapter(connection)
        await admin_security.ensure_schema(db)
        from services import admin_people
        for sql in admin_people.STATEMENTS:
            await db.execute(sql)
        await dm_repo.ensure_schema(db)
        assert dm_push is not None
        await setup(db)
        await proof(db, bot)
    print("PASS «Гонка за Пропуском» on PostgreSQL")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    asyncio.run(run(parser.parse_args().dsn))
