"""Avatar cache failure/recovery proof without Telegram or database access."""
import asyncio
import os
from pathlib import Path
import sys
import time
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('BOT_TOKEN', '1:offline-avatar-test')
os.environ.setdefault('DATABASE_URL', 'postgresql://offline@127.0.0.1:1/offline')
from FastAPI.routers import profile

PHOTO = 'data:image/jpeg;base64,AAAA'


async def main():
    profile._AVATAR_CACHE.clear()
    with patch.object(profile, '_fetch_tg_avatar', AsyncMock(return_value=None)):
        profile._AVATAR_CACHE[1] = (PHOTO, time.time() - profile._AVATAR_TTL - 1)
        assert await profile._vip_avatar(None, 1, vip_active=True, wait=False) == PHOTO
        await profile._AVATAR_INFLIGHT[1]
        assert profile._AVATAR_CACHE[1][0] == PHOTO
        assert await profile._vip_avatar(None, 1, vip_active=False) is None

        assert await profile._vip_avatar(None, 2, vip_active=True) is None
        assert profile._AVATAR_CACHE[2][0] is None
    # A failed first download is retried after seconds, not six hours.
    profile._AVATAR_CACHE[2] = (None, time.time() - profile._AVATAR_MISS_TTL - 1)
    with patch.object(profile, '_fetch_tg_avatar', AsyncMock(return_value=PHOTO)) as fetch:
        assert await profile._vip_avatar(None, 2, vip_active=True) == PHOTO
        assert await profile._vip_avatar(None, 2, vip_active=True) == PHOTO
        assert fetch.await_count == 1

    completed = asyncio.Event()
    async def slow(_):
        await completed.wait()
        return PHOTO
    with patch.object(profile, '_fetch_tg_avatar', slow), patch.object(profile, '_AVATAR_BUDGET_SEC', .01):
        assert await profile._vip_avatar(None, 3, vip_active=True) is None
        task = profile._AVATAR_INFLIGHT[3]
        assert not task.cancelled()
        completed.set()
        await task
        assert await profile._vip_avatar(None, 3, vip_active=True) == PHOTO
    print('avatar recovery: stale photo, transient miss, timeout and VIP gate OK')


if __name__ == '__main__':
    asyncio.run(main())
