"""Best-effort cross-surface product telemetry."""
from __future__ import annotations

import logging

from core.reconstruction import BALANCE_VERSION, GAME_VERSION
from infrastructure.repositories import gameplay_events as event_repo


logger = logging.getLogger(__name__)


async def record_surface_open(db, user_id: int, surface_id: str, source: str) -> None:
    try:
        await event_repo.record_event(
            db,
            user_id=user_id,
            event_name="product_surface_opened",
            game_version=GAME_VERSION,
            balance_version=BALANCE_VERSION,
            source=source,
            payload={"surface_id": surface_id},
        )
        await db.commit()
    except Exception as exc:  # telemetry must not break the player flow
        logger.warning("surface telemetry failed: %s", exc)


async def record_preference_change(
    db, user_id: int, preference: str, enabled: bool, source: str
) -> None:
    try:
        await event_repo.record_event(
            db,
            user_id=user_id,
            event_name="player_preference_changed",
            game_version=GAME_VERSION,
            balance_version=BALANCE_VERSION,
            source=source,
            payload={"preference": preference, "enabled": enabled},
        )
        await db.commit()
    except Exception as exc:
        logger.warning("preference telemetry failed: %s", exc)
