"""Whole-bot scenarios: the Pass in the chat and «Гонка за Пропуском» (S28) — «бот пропуск» with the new ranked experience,
the race line only while the race runs, the owner's message about a taken place and the winner's message after the check.

The race is the owner's money, so the scenario leaves it switched off and empty, whatever happens."""
from __future__ import annotations

from datetime import datetime, timezone

from tools.mafia_sim.harness import Harness
from tools.mafia_sim.registry import bot_scenario, ok
from tools.mafia_sim.scn_bot_dm_push import database, deliver, player, to_player
from tools.mafia_sim.scn_bot_util import said, say


async def _reset_race(db) -> None:
    from core import pass_race as rules
    from infrastructure.repositories import pass_race as repo
    await repo.ensure_tables(db)
    await db.execute("DELETE FROM pass_race_entries")
    await db.execute("DELETE FROM pass_race_runs")
    await db.execute("UPDATE system_flags SET enabled = 0 WHERE key = ?", (rules.FLAG,))
    await db.commit()


@bot_scenario(volatile=True)   # the owner's message carries the server time of the place
async def pass_command_and_race(h: Harness) -> None:
    from core import league_pass as pass_rules, league_v1, pass_race as rules
    from infrastructure.repositories import dm_push as dm_repo
    from services import admin_security, league_pass, pass_race
    racer = await player(h, "Гонщик")
    owner = await player(h, "Владелец")
    full = pass_rules.LEVELS * pass_rules.XP_PER_LEVEL
    async with database() as db:
        await _reset_race(db)
        await db.execute("UPDATE users SET bot_rank = 6 WHERE user_tg_id = ?", (owner.id,))
        await db.commit()
    previous = admin_security._bot_getter
    admin_security.use_bot(lambda: h.bot)
    try:
        text = said(await say(h, racer, racer.id, "пропуск"))
        stars = league_v1.XP_BY_STARS
        ok("Пропуск сезона" in text and f"{stars[1]}, {stars[2]} или {stars[3]}" in text, f"the pass in the DM with the new ranked xp: {text[:300]!r}")
        ok("🏁" not in text, "no race line while the race is off")

        async with database() as db:
            await pass_race.set_enabled(db, enabled=True, actor_id=owner.id)
            await league_pass.add_xp(db, user_id=racer.id, source="sim", event_id=f"near:{racer.id}", xp=full - 30, casual=False)
            await league_pass.add_xp(db, user_id=racer.id, source="sim", event_id=f"cross:{racer.id}", xp=60, casual=False)
            await pass_race.announce_pending(db)
        await admin_security.drain()
        to_owner = [p["text"] for p in to_player(h, owner)]
        ok(any(f"tg://user?id={racer.id}" in t and "Место <b>1 из 4</b>" in t for t in to_owner),
           f"the owner gets the place, the id and the tg:// link: {[t[:120] for t in to_owner]}")

        text = said(await say(h, racer, racer.id, "бот пропуск"))
        ok(f"по {rules.PRIZE_STARS} ⭐" in text and "Осталось мест: 3" in text, f"the race line with the places left: {text[-260:]!r}")

        async with database() as db:
            await dm_repo.set_consent(db, racer.id, "pass", True)
            result = await pass_race.mark(db, user_id=racer.id, status=rules.VERIFIED, actor_id=owner.id)
            ok(result["player_told"], "with consent the winner's message is queued")
            since = len(h.world.calls)
            await deliver(h, db, datetime.now(timezone.utc).replace(hour=12))
        got = to_player(h, racer, since)
        ok(any("Ты среди первых четырёх" in p["text"] for p in got), f"the winner hears it only after the check: {[p['text'][:80] for p in got]}")
    finally:
        admin_security.use_bot(previous)
        async with database() as db:
            await _reset_race(db)
