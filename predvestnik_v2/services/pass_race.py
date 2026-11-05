"""«Гонка за Пропуском» (core.pass_race): switch, places, the owner's message and check card, manual payout marks.

Nothing here pays: the owner sends the Stars by hand and presses «выплачено».  A failure of the race never costs a
player experience (league_pass.add_xp calls on_reached in its own savepoint and only logs); the sweep in
announce_pending then finds the crossing in the pass receipts and records it.  The owner's «place taken» message goes
after the experience is committed: a background step re-reads the place a moment later (the maintenance task and the
admin block repeat it), so a rolled-back result never reaches the owner, and the mark «told» is kept only when at least
one owner got the message.
"""
from __future__ import annotations

import asyncio
import html
from datetime import datetime, timezone

from loguru import logger

from core import account_age, league_pass as pass_rules, pass_race as rules, seasons
from infrastructure.repositories import account_age as account_age_repo
from infrastructure.repositories import pass_race as repo
from infrastructure.repositories import system_flags

ANNOUNCE_DELAY_S = 3.0      # the result that crossed the level is committed by then; the maintenance sweep is the backstop
FULL_XP = pass_rules.LEVELS * pass_rules.XP_PER_LEVEL
_tasks: set[asyncio.Task] = set()


class RaceError(Exception):
    pass


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


async def running(db, now: datetime | None = None) -> dict | None:
    """The race of the current season when the switch is on, else None."""
    if not await system_flags.is_enabled(db, rules.FLAG):
        return None
    await repo.ensure_tables(db)
    return await repo.run(db, seasons.season_number(_now(now)))


async def set_enabled(db, *, enabled: bool, actor_id: int, now: datetime | None = None) -> dict | None:
    """The admin switch.  On: the flag; the first time this season also the start moment, later only the end of a pause.
    Off: only the flag (places already taken stay; a pass closed while it is off never counts)."""
    await repo.ensure_tables(db)
    season = seasons.season_number(_now(now))
    if enabled and season < 2:
        raise RaceError("Гонка работает с Пропуском сезона 2 и дальше.")
    async with db.connection.transaction():
        await repo.lock_race(db, season)
        await repo.put_flag(db, enabled)
        if enabled:
            await repo.start(db, season=season, actor_id=actor_id)
    return await running(db, now)


# ── Places ─────────────────────────────────────────────────────────────────────────────

async def on_reached(db, *, user_id: int, season: int, xp_before: int, xp_after: int) -> bool:
    """Called by league_pass.add_xp inside its transaction after the experience is added.  True: the player took a place."""
    if not rules.crossed(xp_before, xp_after):
        return False
    await repo.ensure_tables(db)
    await repo.lock_race(db, season)   # before reading the switch: a pause that commits meanwhile is seen
    race = await running(db)
    if not race or race["season"] != int(season):
        return False
    if await repo.add_entry(db, season=season, user_id=user_id) is None:
        return False
    took = any(int(e["user_id"]) == int(user_id) for e in rules.seated(await repo.entries(db, season)))
    if took:
        _schedule_announce()
    return took


def _schedule_announce() -> None:
    try:
        task = asyncio.get_running_loop().create_task(_announce_later())
    except RuntimeError:
        return
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _announce_later() -> None:
    await asyncio.sleep(ANNOUNCE_DELAY_S)
    try:
        from infrastructure import lazy_db
        from infrastructure.database import get_pool
        async with lazy_db.lazy_connection(get_pool(), source="background") as db:
            await announce_pending(db)
    except Exception as exc:   # the maintenance task repeats it
        logger.warning(f"pass race announce postponed: {type(exc).__name__}: {exc}")


async def drain() -> None:   # tests: wait for the background announcements
    while _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)


async def _recover_missed(db, now: datetime) -> int:
    """A crossing whose live recording failed (lock timeout, a broken step) is found in the pass receipts and recorded
    with its real time.  Only since the last switch-on: a pass closed during a pause does not count."""
    race = await running(db, now)
    if not race:
        return 0
    found = 0
    for user_id, crossed_at in await repo.missed_crossings(db, season=race["season"], since=race["resumed_at"], full_xp=FULL_XP):
        async with db.connection.transaction():
            await repo.lock_race(db, race["season"])
            if await repo.add_entry(db, season=race["season"], user_id=user_id, reached_at=crossed_at) is not None:
                found += 1
                logger.warning(f"pass race: recovered a missed crossing of {user_id} at {crossed_at}")
    return found


async def _close_stale_switch(db, now: datetime) -> None:
    """A new season has no race of its own: the switch goes off, so the guide and «Что нового» stop advertising it.
    The owner starts the next race explicitly (it is money)."""
    if await system_flags.is_enabled(db, rules.FLAG) and await repo.run(db, seasons.season_number(now)) is None:
        await repo.put_flag(db, False)
        logger.info("pass race: the season changed, the race switch is off until the owner starts a new one")


async def announce_pending(db, now: datetime | None = None) -> int:
    """Tell the owner about every place holder not told yet (new places, recovered ones and places handed on after a
    rejection).  Also the housekeeping of the race: missed crossings and the switch after a season change."""
    from services import admin_security
    now = _now(now)
    await repo.ensure_tables(db)
    await _recover_missed(db, now)
    await _close_stale_switch(db, now)
    sent = 0
    for season in await repo.seasons_to_alert(db):
        for entry in rules.seated(await repo.entries(db, season)):
            if entry["owner_alerted_at"] is not None or not await repo.claim_owner_alert(db, season=season, user_id=entry["user_id"]):
                continue
            names = await repo.usernames(db, [entry["user_id"]])
            delivered = await admin_security.alert_now(db, owner_alert_text(entry, names.get(int(entry["user_id"]))),
                                                       title="🏁 Гонка за Пропуском: место занято")
            if delivered:
                sent += 1
            else:   # nobody got it: the next sweep (maintenance, the admin block) tries again
                await repo.release_owner_alert(db, season=season, user_id=entry["user_id"])
    return sent


def _when(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M:%S UTC")


def owner_alert_text(entry: dict, username: str | None) -> str:
    uid = int(entry["user_id"])
    who = html.escape(f"@{username}" if username else "без ника")
    found = "\n⚠️ Место найдено проверкой: в момент закрытия гонка не записала его сразу." if entry.get("recovered") else ""
    return (f"Место <b>{entry['place']} из {rules.PLACES}</b> · сезон {entry['season']}\n"
            f"Игрок: {who} · id <code>{uid}</code> · <a href=\"tg://user?id={uid}\">открыть чат с игроком</a>\n"
            f"Пропуск закрыт (уровень {rules.LEVEL}): {_when(entry['reached_at'])}{found}\n\n"
            "<b>Что сделать</b>\n"
            "1. Админка → «Функции» → блок «Гонка за Пропуском» → «Проверить»: возраст аккаунта, похожие аккаунты, "
            "непроверенные партии, бан.\n"
            "2. Всё чисто — «Проверен». Бот напишет игроку «ты среди первых четырёх», если у игрока включены уведомления о Пропуске.\n"
            f"3. Отправь игроку подарок на {rules.PRIZE_STARS} ⭐ со своего аккаунта и нажми «Выплачено».\n"
            "Подозрение на накрутку — «Отклонить»: место перейдёт следующему, бот напишет и о нём.")


# ── Views ──────────────────────────────────────────────────────────────────────────────

async def player_view(db, now: datetime | None = None) -> dict:
    """What the pass card shows: only whether the race runs and how many places are left (no names)."""
    race = await running(db, now)
    if not race:
        return {"running": False}
    left = rules.places_left(await repo.entries(db, race["season"]))
    return {"running": True, "places": rules.PLACES, "left": left, "prize_stars": rules.PRIZE_STARS, "level": rules.LEVEL}


def _iso(value) -> str | None:
    return value.isoformat() if value else None


async def _season_view(db, season: int, current: int, enabled: bool) -> dict:
    race = await repo.run(db, season)
    rows = await repo.entries(db, season)
    seated = {int(e["user_id"]): e["place"] for e in rules.seated(rows)}
    names = await repo.usernames(db, [e["user_id"] for e in rows] + [e["marked_by"] for e in rows])
    out = []
    for e in rows:
        uid = int(e["user_id"])
        out.append({"season": season, "user_id": uid, "username": names.get(uid), "place": seated.get(uid),
                    "reached_at": _iso(e["reached_at"]), "recovered": e["recovered"],
                    "status": e["status"], "status_label": rules.STATUS_LABELS[e["status"]],
                    "next": [s for s in rules.TRANSITIONS[e["status"]] if uid in seated or s == rules.REJECTED],
                    "marked_by": e["marked_by"], "marked_by_name": names.get(int(e["marked_by"])) if e["marked_by"] else None,
                    "marked_at": _iso(e["marked_at"]), "note": e["note"],
                    "owner_alerted": e["owner_alerted_at"] is not None, "player_told": e["player_told_at"] is not None})
    out.sort(key=lambda r: (r["place"] is None, r["place"] or 0, r["reached_at"] or ""))
    return {"season": season, "current": season == current, "running": bool(enabled and race and season == current),
            "started_at": _iso(race["started_at"]) if race else None, "left": rules.places_left(rows), "entries": out}


async def admin_view(db, now: datetime | None = None) -> dict:
    """The owner's block: the current season and every earlier one with places not paid yet (a winner of the last
    minutes of a season is still checked and paid after midnight)."""
    await repo.ensure_tables(db)
    current = seasons.season_number(_now(now))
    enabled = await system_flags.is_enabled(db, rules.FLAG)
    shown = sorted(set(await repo.open_seasons(db)) | {current}, reverse=True)
    return {"enabled": enabled, "places": rules.PLACES, "prize_stars": rules.PRIZE_STARS, "level": rules.LEVEL,
            "seasons": [await _season_view(db, s, current, enabled) for s in shown],
            "labels": rules.STATUS_LABELS, "min_account_days": account_age.MIN_ACCOUNT_AGE.days}


async def check_card(db, *, user_id: int, season: int | None = None, now: datetime | None = None) -> dict:
    """What the owner checks before paying, for the season of the place.  Signals only: the decision stays with the owner."""
    from services import global_moderation, twin_detection
    now = _now(now)
    uid = int(user_id)
    season = int(season or seasons.season_number(now))
    seen = (await account_age_repo.first_seen(db, [uid])).get(uid)
    unchecked = await repo.unchecked_games(db, user_id=uid, since=seasons.season_bounds(season)[0], league_season=f"s{season}")
    cached = twin_detection.get_cached()
    if not cached["computed_at"] or now.timestamp() - cached["computed_at"] > 600:
        cached = await twin_detection.recalculate(db)   # heavy, but only on the owner's press of «Проверить»
    twins = [{"user_id": p["user_b"] if p["user_a"] == uid else p["user_a"],
              "username": p["username_b"] if p["user_a"] == uid else p["username_a"],
              "score": p["score"], "signals": [s["label"] for s in p["signals"]]}
             for p in cached["pairs"] if uid in (p["user_a"], p["user_b"])]
    names = await repo.usernames(db, [uid])
    return {"user_id": uid, "season": season, "username": names.get(uid),
            "account": {"first_seen": _iso(seen), "days": (now - seen).days if seen else None,
                        "min_days": account_age.MIN_ACCOUNT_AGE.days, "ok": account_age.is_eligible(seen, now)},
            "twins": twins, "twins_checked_at": datetime.fromtimestamp(cached["computed_at"], timezone.utc).isoformat(),
            "unchecked": unchecked,
            "ban": {"global": await global_moderation.ban_info(db, uid), "blocked": await global_moderation.block_info(db, uid)}}


# ── The owner's marks ──────────────────────────────────────────────────────────────────

WINNER_TEXT = (f"🏁 <b>Ты среди первых четырёх!</b>\n"
               f"Твой Пропуск сезона закрыт одним из первых. Приз — {rules.PRIZE_STARS} ⭐ Telegram Stars.\n"
               "Администрация свяжется с тобой здесь, в Telegram, и пришлёт звёзды подарком. Делать ничего не нужно.")


def _dm_key(season: int) -> str:
    return f"pass_race:{int(season)}"


async def mark(db, *, user_id: int, status: str, actor_id: int, season: int | None = None, note: str = "",
               now: datetime | None = None) -> dict:
    """Change one place's status.  The same status again changes nothing (a second «выплачено» is harmless); a second
    «проверен» only retries the player's message if it was not queued the first time."""
    from services import admin_people
    season = int(season or seasons.season_number(_now(now)))
    note = str(note or "").strip()[:300]
    await repo.ensure_tables(db)
    async with db.connection.transaction():
        await repo.lock_race(db, season)
        entry = await repo.entry_for_update(db, season=season, user_id=user_id)
        if entry is None:
            raise RaceError("Этого игрока нет в гонке этого сезона.")
        same = entry["status"] == status
        if not same:
            try:
                rules.check_transition(entry["status"], status)
            except rules.RaceRuleError as exc:
                raise RaceError(str(exc)) from exc
            seated = {int(e["user_id"]) for e in rules.seated(await repo.entries(db, season))}
            if status in (rules.VERIFIED, rules.PAID) and int(user_id) not in seated:
                raise RaceError("Игрок пока в очереди: место освободится, только если кого-то из первых отклонят.")
            await repo.set_status(db, season=season, user_id=user_id, status=status, actor_id=actor_id, note=note)
            await admin_people.audit(db, actor_id, "pass_race", user_id=int(user_id),
                                     details={"season": season, "from": entry["status"], "to": status, "note": note,
                                              "stars": rules.PRIZE_STARS if status == rules.PAID else 0})
    told = None
    if status == rules.VERIFIED and (not same or entry["player_told_at"] is None):
        told = await _tell_winner(db, season=season, user_id=user_id)
    if status == rules.REJECTED and not same:
        await _withdraw_winner_message(db, season=season, user_id=user_id)
        await announce_pending(db)   # the next player in the queue may have taken the place
    return {"changed": not same, "status": status, "player_told": told}


async def _tell_winner(db, *, season: int, user_id: int) -> bool:
    """«Ты среди первых четырёх» through the shared DM queue: only with the player's consent to Pass messages."""
    from services import dm_push
    try:
        queued = await dm_push.enqueue(db, user_id=int(user_id), category="pass", dedup_key=_dm_key(season),
                                       text=WINNER_TEXT, button={"section": "guide_pass-race", "label": "🏁 Правила гонки"})
    except Exception as exc:   # the mark stays; «Проверен» again retries the message
        logger.warning(f"pass race winner message not queued for {user_id}: {type(exc).__name__}: {exc}")
        return False
    if queued:
        await repo.mark_player_told(db, season=season, user_id=user_id)
    return queued


async def _withdraw_winner_message(db, *, season: int, user_id: int) -> None:
    """A rejected player must not get a «ты среди первых четырёх» still waiting in the queue."""
    from infrastructure.repositories import dm_push as dm_repo
    try:
        await dm_repo.drop_pending_key(db, int(user_id), _dm_key(season), "pass_race_rejected")
    except Exception as exc:   # no DM tables yet: nothing was queued
        logger.warning(f"pass race winner message not withdrawn for {user_id}: {type(exc).__name__}: {exc}")
