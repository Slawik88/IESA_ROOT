"""Pet action receipts and isolated early-access demo progress.

Call inside the pet writer's transaction, after ownership/validation and replay checks.
The demo never changes a real pass, balances, inventory or League standings.
"""
from datetime import datetime, timezone

from loguru import logger

from core.league_pass_demo import PET_ACTION_XP
from core import league_v1 as league_rules
from core.league_v1 import DEMO_SEASON
from infrastructure.repositories import league_v1 as league_repo
from infrastructure.repositories import pets_v1, pets_v2


def _demo_active(now: datetime | None = None) -> bool:
    return not league_rules.is_public(now or datetime.now(timezone.utc))


async def record_pet_event(db, *, user_id: int, source: str, event_id: str) -> None:
    # Optional demo progress must never prevent feeding or a real pet reward.
    # Successful XP still rolls back with the enclosing pet transaction.
    if not _demo_active():
        return
    try:
        from services import early_access

        async with db.connection.transaction():
            if not await early_access.allowed(db, int(user_id)):
                return
            await league_repo.ensure_tables(db)
            # Same lock as demo reset. Pet writers already own the pet user lock.
            await league_repo.lock_user(db, user_id=int(user_id))
            await league_repo.add_pet_xp(
                db, user_id=int(user_id), season=DEMO_SEASON, source=source,
                event_id=str(event_id), xp=PET_ACTION_XP,
            )
    except Exception:
        logger.exception("Demo pet XP skipped: user={} source={} event={}", user_id, source, event_id)


async def save_v1_action(db, user_id: int, action_id: str, request: dict, response: dict) -> None:
    await pets_v1.save_action(db, user_id, action_id, request, response)
    await record_pet_event(db, user_id=user_id, source="pet_v1", event_id=action_id)


async def save_v2_action(db, user_id: int, action_id: str, request: dict, response: dict) -> None:
    await pets_v2.save_action(db, user_id, action_id, request, response)
    await record_pet_event(db, user_id=user_id, source="pet_v2", event_id=action_id)
