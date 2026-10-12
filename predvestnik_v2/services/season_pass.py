"""Free season pass for the games: points from qualifying games, levels claimed once.

Everything is dark until the ``season_pass_v1`` flag is on; counting starts at
that moment (no points are back-filled).  Point writes never stop a game from
finishing: they run in their own savepoint and a failure is only logged.
"""
from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger

from core import season_pass as rules
from core import seasons
from infrastructure.repositories import economy_ledger
from infrastructure.repositories import season_pass as repo
from infrastructure.repositories import system_flags
from services import skins_v3 as skins_service


class SeasonPassError(Exception):
    pass


async def enabled(db) -> bool:
    return await system_flags.is_enabled(db, rules.FLAG)


async def record_game(db, *, user_id: int, source: str, event_id: str,
                      occurred_at: datetime | None = None) -> int:
    """Count one qualifying game; returns the points added (0 when off, capped or already counted).

    The caller has already decided the game qualifies (see ``core.season_pass``).
    """
    if source not in rules.SOURCES:
        raise SeasonPassError(f"unknown point source: {source}")
    try:
        if not await enabled(db):
            return 0
        at = rules.utc(occurred_at or datetime.now(timezone.utc))
        season, day = seasons.season_number(at), at.date()
        async with db.connection.transaction():
            granted = rules.granted_points(await repo.lock_day(db, user_id=user_id, season=season, day=day))
            if not await repo.insert_receipt(db, user_id=user_id, source=source, event_id=str(event_id),
                                             season=season, day=day, points=granted):
                return 0
            if granted:
                await repo.add_points(db, user_id=user_id, season=season, day=day, points=granted)
            return granted
    except Exception:
        logger.exception("Season pass points failed for user {} ({}:{}); the game result is unaffected",
                         user_id, source, event_id)
        return 0


def _view(season: int, progress: dict | None, today_points: int, now: datetime) -> dict:
    points = int(progress["points"]) if progress else 0
    claimed = int(progress["claimed_level"]) if progress else 0
    level = rules.level_of(points)
    mora, essence = rules.reward_for_levels(claimed, level)
    start, end = seasons.season_bounds(season)
    return {
        "season": season, "starts_at": start.isoformat(), "ends_at": end.isoformat(),
        "claim_until": rules.claim_deadline(season).isoformat(),
        "points": points, "level": level, "levels": rules.LEVELS, "points_per_level": rules.POINTS_PER_LEVEL,
        "points_to_next": 0 if level >= rules.LEVELS else rules.POINTS_PER_LEVEL - points % rules.POINTS_PER_LEVEL,
        "claimed_level": claimed, "claimable_levels": level - claimed,
        "claimable": {"mora": mora, "essence": essence},
        "per_level": {"mora": rules.MORA_PER_LEVEL, "essence": rules.ESSENCE_PER_LEVEL},
        "full_track": {"mora": rules.FULL_TRACK_MORA, "essence": rules.FULL_TRACK_ESSENCE},
        "points_per_game": rules.POINTS_PER_GAME,
        "points_today": today_points, "points_today_cap": rules.DAILY_POINT_CAP,
        "current": season == seasons.season_number(now),
    }


async def status(db, *, user_id: int, now: datetime | None = None) -> dict:
    now = rules.utc(now or datetime.now(timezone.utc))
    if not await enabled(db):
        return {"enabled": False}
    current = seasons.season_number(now)
    today = await repo.day_points(db, user_id=user_id, season=current, day=now.date())
    return {"enabled": True, "seasons": [
        _view(season, await repo.progress(db, user_id=user_id, season=season),
              today if season == current else 0, now)
        for season in rules.claimable_seasons(now)]}


async def claim(db, *, user_id: int, season: int, now: datetime | None = None) -> dict:
    """Claim every reached, unclaimed level of one season: Mora and Essence in one transaction."""
    now = rules.utc(now or datetime.now(timezone.utc))
    if not await enabled(db):
        raise SeasonPassError("Сезонный пропуск пока выключен.")
    if int(season) not in rules.claimable_seasons(now):
        raise SeasonPassError("Срок получения наград этого сезона истёк.")
    async with db.connection.transaction():
        progress = await repo.progress(db, user_id=user_id, season=season, lock=True)
        points = int(progress["points"]) if progress else 0
        claimed = int(progress["claimed_level"]) if progress else 0
        level = rules.level_of(points)
        if level <= claimed:
            raise SeasonPassError("Нет новых уровней для получения.")
        mora, essence = rules.reward_for_levels(claimed, level)
        span = f"{claimed + 1}-{level}"
        await economy_ledger.apply_balance_change(
            db, user_id, {"mora": mora}, reason_code="season_pass",
            idempotency_key=f"season_pass:{season}:{user_id}:{span}",
            source_type="season", reference_type="season_pass", reference_id=f"{season}:{span}",
            metadata={"season": int(season), "levels": span, "mora": mora, "essence": essence},
            note=f"Пропуск сезона {season}: уровни {span}",
        )
        await skins_service.grant_essence_in_transaction(
            db, user_id, essence, reason="season_pass", reference=f"{season}:{user_id}:{span}")
        await repo.set_claimed_level(db, user_id=user_id, season=season, level=level)
    return {"season": int(season), "claimed_levels": span, "mora": mora, "essence": essence,
            "claimed_level": level}
