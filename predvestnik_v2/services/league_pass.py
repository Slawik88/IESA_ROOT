"""Season pass from season 2: experience in, rewards out.

Experience writes never stop a game or a level from finishing: they run in their own savepoint and a
failure is only logged. Quest reward XP is strict and rolls back with its reward. A claim grants every
reached row in one transaction (currency through the economy ledger, keys through the chest-key ledger);
its receipts make a retry harmless.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from loguru import logger

from core import account_age, seasons
from core import league_pass as rules
from core.chests_v1 import POLICY_VERSION as CHEST_POLICY, canonical_snapshot_fingerprint
from infrastructure.repositories import account_age as account_age_repo
from infrastructure.repositories import chests_v1 as chests_repo
from infrastructure.repositories import economy_ledger
from infrastructure.repositories import league_pass as repo
from infrastructure.repositories import vip_v2 as vip_repo


class PassError(Exception):
    pass


async def add_xp(db, *, user_id: int, source: str, event_id: str, xp: int, casual: bool,
                 at: datetime | None = None, season: int | None = None, pet: bool = False, strict: bool = False) -> int:
    """Add experience once per event; casual games and pets each respect their daily cap.  Returns what was added.

    ``season`` pins the pass season (a League level counts for the season of its run); by default it is
    the season of ``at``.
    """
    at = at or datetime.now(timezone.utc)
    season = int(season) if season is not None else seasons.season_number(at)
    if season < rules.FIRST_SEASON or int(xp) <= 0:
        return 0
    try:
        async with db.connection.transaction():   # schema comes from bot/startup_schema.py or FastAPI lifespan
            await chests_repo.lock_user(db, int(user_id))
            await repo.lock_user(db, user_id=user_id)
            gain, bucket = int(xp), "pet" if pet else "casual" if casual else None
            if bucket:
                cap = rules.PET_DAILY_CAP if pet else rules.CASUAL_DAILY_CAP
                gain = rules.capped(gain, (await repo.day_xp(db, user_id=user_id, day=at.date()))[bucket], cap)
            if not await repo.insert_receipt(db, user_id=user_id, source=source, event_id=event_id, season=season, xp=gain):
                return 0
            if gain:
                if bucket:
                    await repo.add_day(db, user_id=user_id, day=at.date(), bucket=bucket, xp=gain)
                await repo.add_xp(db, user_id=user_id, season=season, xp=gain)
            return gain
    except Exception:
        if strict:
            raise
        logger.exception("League pass experience failed for user {} ({}:{}); the game result is unaffected",
                         user_id, source, event_id)
        return 0


async def record_quest(db, *, user_id: int, kind: str, event_id: str, at: datetime | None = None) -> int:
    amount = rules.VIP_MISSION_XP if kind == 'vip' else rules.QUEST_XP.get(kind, 0)
    if not amount:
        return 0
    return await add_xp(db, user_id=user_id, source='quest', event_id=f'{kind}:{event_id}',
                        xp=amount, casual=False, at=at, strict=True)


def _repeat_view(xp: int, state: dict, now: datetime) -> dict:
    banked = max(0, xp - rules.LEVELS * rules.XP_PER_LEVEL - state['claimed'] * rules.XP_PER_LEVEL)
    until = state['next_claim_at']
    return {'level': rules.REPEAT_LEVEL, 'claimed': state['claimed'], 'banked_xp': banked,
            'xp_per_claim': rules.XP_PER_LEVEL, 'next_claim_at': until.isoformat() if until else None,
            'ready': banked >= rules.XP_PER_LEVEL and (until is None or now >= until),
            'wait_hours': int(rules.REPEAT_WAIT.total_seconds() // 3600), 'key_tier': rules.REPEAT_KEY_TIER}


async def record_pet(db, *, user_id: int, kind: str, event_id: str, at=None) -> int:
    """One counted pet action (core.league_pass.PET_XP); call inside the pet writer's transaction."""
    return await add_xp(db, user_id=user_id, source="pet", event_id=f"{kind}:{event_id}",
                        xp=rules.PET_XP.get(kind, 0), casual=False, pet=True, at=at)


async def record_rhythm(db, *, user_id: int, run_id: str, score: int, at=None) -> int:
    return await add_xp(db, user_id=user_id, source="rhythm", event_id=str(run_id),
                        xp=rules.rhythm_casual_xp(score), casual=True, at=at)


async def record_mines(db, *, user_id: int, run_id: str, won: bool, difficulty: str, at=None) -> int:
    return await add_xp(db, user_id=user_id, source="minesweeper", event_id=str(run_id),
                        xp=rules.mines_casual_xp(won=won, difficulty=difficulty), casual=True, at=at)


def _row(level: int, track: str, reached: int, claimed: set, vip_open: bool) -> dict:
    item = rules.reward(level, track)
    state = ("claimed" if (level, track) in claimed else "locked" if level > reached
             else "vip" if track == "vip" and not vip_open else "ready")
    return {"text": rules.reward_text(item), "state": state}


async def status(db, *, user_id: int, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if not rules.active(now):
        return {"active": False, "starts_at": seasons.season_bounds(rules.FIRST_SEASON)[0].isoformat()}
    await repo.ensure_tables(db)
    vip_open = await vip_repo.pass_eligible(db, user_id=user_id, at=now, min_days=rules.VIP_MIN_DAYS)
    seen = (await account_age_repo.first_seen(db, [user_id])).get(int(user_id))
    views = []
    for season in rules.claimable_seasons(now):
        xp = await repo.xp(db, user_id=user_id, season=season)
        reached, claimed = rules.level_of(xp), await repo.claims(db, user_id=user_id, season=season)
        views.append({
            "season": season, "current": season == seasons.season_number(now), "xp": xp, "level": reached,
            "levels": rules.LEVELS, "xp_per_level": rules.XP_PER_LEVEL,
            "xp_to_next": 0 if reached >= rules.LEVELS else rules.XP_PER_LEVEL - xp % rules.XP_PER_LEVEL,
            "ends_at": seasons.season_bounds(season)[1].isoformat(), "claim_until": rules.claim_deadline(season).isoformat(),
            "repeat": {**_repeat_view(xp, await repo.repeat_state(db, user_id=user_id, season=season), now),
                       **({'ready': False} if season != seasons.season_number(now) else {}),
                       'current': season == seasons.season_number(now)},
            "track": [{"level": n, "free": _row(n, "free", reached, claimed, vip_open), "vip": _row(n, "vip", reached, claimed, vip_open)}
                      for n in range(1, rules.LEVELS + 1)],
        })
    async with db.connection.transaction():
        today = await repo.day_xp(db, user_id=user_id, day=now.date())
    return {"active": True, "vip": vip_open, "vip_min_days": rules.VIP_MIN_DAYS, "seasons": views,
            "quests": {**rules.QUEST_XP, 'vip': rules.VIP_MISSION_XP},
            "casual": {"today": today["casual"], "cap": rules.CASUAL_DAILY_CAP},
            "pets": {"today": today["pet"], "cap": rules.PET_DAILY_CAP, "xp": dict(rules.PET_XP)},
            "account": {"eligible": account_age.is_eligible(seen, now), "min_days": account_age.MIN_ACCOUNT_AGE.days}}


async def casual_receipt(db, *, user_id: int, source: str, event_id: str, now: datetime | None = None) -> dict:
    """What one casual game gave the pass, for the line «+N опыта Пропуска» on its result screen."""
    now = now or datetime.now(timezone.utc)
    if not rules.active(now):
        return {"active": False}
    gained = await repo.receipt(db, user_id=user_id, source=source, event_id=event_id)
    async with db.connection.transaction():
        today = (await repo.day_xp(db, user_id=user_id, day=now.date()))["casual"]
    return {"active": True, "xp": gained or 0, "counted": gained is not None, "today": today, "cap": rules.CASUAL_DAILY_CAP}


async def _grant(db, *, user_id: int, season: int, level: int, track: str, item: dict, cycle: int = 0) -> None:
    ref = f"40:{season}:{level}:{track}" + (f":{cycle}" if cycle else '')
    if "key" in item:
        await chests_repo.ensure_tables(db)
        await chests_repo.assert_delivery_ready(db)
        await chests_repo.lock_user(db, int(user_id))
        source = f"pass_tier{item['key']}"
        if await chests_repo.find_grant(db, user_id=user_id, source_kind=source, source_event_id=ref):
            return
        account = await chests_repo.lock_account(db, int(user_id))
        snapshot = {"season": season, "level": level, "track": track, "key_tier": item["key"]}
        await chests_repo.apply_grant(
            db, grant_id=uuid4().hex, user_id=int(user_id), source_kind=source, source_event_id=ref, amount=1,
            policy_version=CHEST_POLICY, source_snapshot=snapshot,
            source_snapshot_hash=canonical_snapshot_fingerprint(snapshot), balance_before=int(account["balance"]),
            account_epoch=int(account["account_epoch"]))
        return
    await economy_ledger.apply_balance_change(
        db, user_id, dict(item), reason_code=rules.REASON, idempotency_key=f"league_pass:{user_id}:{ref}",
        source_type="season", reference_type="league_pass", reference_id=ref,
        metadata={"season": season, "level": level, "track": track, **item},
        note=f"Пропуск сезона {season}: уровень {level}" + (" (VIP)" if track == "vip" else ""))


async def claim(db, *, user_id: int, season: int, now: datetime | None = None) -> dict:
    """Claim every reached, unclaimed level of both rows (VIP row only with a qualifying active term)."""
    now = now or datetime.now(timezone.utc)
    if int(season) not in rules.claimable_seasons(now):
        raise PassError("Награды этого сезона уже нельзя получить.")
    seen = (await account_age_repo.first_seen(db, [user_id])).get(int(user_id))
    if not account_age.is_eligible(seen, now):
        raise PassError(f"Награды выдаются аккаунтам, которые в боте не меньше {account_age.MIN_ACCOUNT_AGE.days} дней. "
                        "Опыт копится, получить можно позже.")
    await repo.ensure_tables(db)
    granted = []
    async with db.connection.transaction():
        await chests_repo.lock_user(db, int(user_id))
        await vip_repo.lock_user(db, user_id)
        await repo.lock_user(db, user_id=user_id)
        vip_open = await vip_repo.pass_eligible(db, user_id=user_id, at=now, min_days=rules.VIP_MIN_DAYS)
        xp = await repo.xp(db, user_id=user_id, season=season)
        reached, claimed = rules.level_of(xp), await repo.claims(db, user_id=user_id, season=season)
        for level in range(1, reached + 1):
            for track in ("free", "vip") if vip_open else ("free",):
                if (level, track) in claimed:
                    continue
                item = rules.reward(level, track)
                if await repo.insert_claim(db, user_id=user_id, season=season, level=level, track=track, reward=item):
                    await _grant(db, user_id=user_id, season=int(season), level=level, track=track, item=item)
                    granted.append({"level": level, "track": track, "text": rules.reward_text(item)})
        repeat = await repo.repeat_state(db, user_id=user_id, season=season)
        if int(season) == seasons.season_number(now) and _repeat_view(xp, repeat, now)['ready']:
            cycle = repeat['claimed'] + 1
            item = {'key': rules.REPEAT_KEY_TIER}
            await _grant(db, user_id=user_id, season=season, level=rules.REPEAT_LEVEL, track='free', item=item, cycle=cycle)
            await repo.save_repeat(db, user_id=user_id, season=season, claimed=cycle, next_claim_at=now + rules.REPEAT_WAIT)
            granted.append({'level': rules.REPEAT_LEVEL, 'track': 'free', 'text': rules.reward_text(item), 'cycle': cycle})
    if not granted:
        raise PassError("Нет новых наград для получения.")
    return {"season": int(season), "granted": granted}
