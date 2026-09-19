#!/usr/bin/env python3
"""Focused proof that only the developer rank crosses the Rhythm review gate."""
from __future__ import annotations

import asyncio

from fastapi import HTTPException

from FastAPI.routers import rhythm_v2 as router
from services.roles import DEVELOPER_GLOBAL_RANK


async def run() -> None:
    original = router.users_repo.get_global_rank

    async def rank_below(_db, _user_id):
        return DEVELOPER_GLOBAL_RANK - 1

    async def developer_rank(_db, _user_id):
        return DEVELOPER_GLOBAL_RANK

    try:
        router.users_repo.get_global_rank = rank_below
        try:
            await router._require_integrity_reviewer(object(), 975101)
        except HTTPException as exc:
            assert exc.status_code == 403
        else:
            raise AssertionError("non-developer must not review Rhythm runs")

        router.users_repo.get_global_rank = developer_rank
        assert await router._require_integrity_reviewer(object(), 975102) is None
    finally:
        router.users_repo.get_global_rank = original


asyncio.run(run())
print("OK: Rhythm integrity review is developer-only")
