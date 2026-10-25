"""Pet actions → experience of the season pass (from season 2) or of the early-access demo (before it).

Call inside the pet writer's transaction, after ownership/validation and replay checks.  Which actions count
and how much: core.league_pass.PET_XP (free toggles give nothing), under the pets' own daily cap.
Experience never prevents the pet action: a failure is logged and skipped, and a counted action still rolls
back with the enclosing pet transaction.  The demo never changes a real pass, balances or League standings.
"""
from datetime import datetime, timezone

from loguru import logger

from core import league_pass as pass_rules
from core import league_v1 as league_rules
from core.league_v1 import DEMO_SEASON
from infrastructure.repositories import league_v1 as league_repo
from infrastructure.repositories import pets_v1, pets_v2


def _demo_active(now: datetime | None = None) -> bool:
    return not league_rules.is_public(now or datetime.now(timezone.utc))


async def record_pet_event(db, *, user_id: int, kind: str | None, event_id: str) -> int:
    xp = pass_rules.PET_XP.get(kind or "", 0)
    if not xp:
        return 0
    if not _demo_active():
        from services import league_pass
        return await league_pass.record_pet(db, user_id=int(user_id), kind=kind, event_id=str(event_id))
    try:
        from services import early_access

        async with db.connection.transaction():
            if not await early_access.allowed(db, int(user_id)):
                return 0
            await league_repo.ensure_tables(db)
            # Same lock as demo reset. Pet writers already own the pet user lock.
            await league_repo.lock_user(db, user_id=int(user_id))
            await league_repo.add_pet_xp(
                db, user_id=int(user_id), season=DEMO_SEASON, source=kind,
                event_id=str(event_id), xp=xp,
            )
    except Exception:
        logger.exception("Demo pet XP skipped: user={} kind={} event={}", user_id, kind, event_id)
    return 0


async def save_v1_action(db, user_id: int, action_id: str, request: dict, response: dict) -> None:
    response['pass_xp'] = await record_pet_event(db, user_id=user_id, kind=pass_rules.pet_action_kind(request), event_id=f"v1:{action_id}")
    await pets_v1.save_action(db, user_id, action_id, request, response)


async def save_v2_action(db, user_id: int, action_id: str, request: dict, response: dict) -> None:
    response['pass_xp'] = await record_pet_event(db, user_id=user_id, kind=pass_rules.pet_action_kind(request), event_id=f"v2:{action_id}")
    await pets_v2.save_action(db, user_id, action_id, request, response)
