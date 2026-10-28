"""Avatar refresh failure/recovery proof without Telegram or a database (services/avatar_photos.py).

- a Telegram failure or a blown time budget keeps the stored photo, and the player is paused before a retry;
- concurrent requests share one refresh; an unchanged photo is not downloaded again;
- a photo hidden from the bot comes from the player's own signed Mini App URL;
- avatar_state: vip_only / loading / ready / absent, and a stale row is refreshed in the background.
"""
import asyncio
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('BOT_TOKEN', '1:offline-avatar-test')
os.environ.setdefault('DATABASE_URL', 'postgresql://offline@127.0.0.1:1/offline')
from infrastructure import telegram_photo
from infrastructure.repositories.avatar_photos import StoredPhoto
from services import avatar_photos
from services.support_diagnostics import RecentDiagnostics

WEBP = b'RIFF\x00\x00\x00\x00WEBPfake'
URL = 'https://t.me/i/userpic/320/own.jpg'


class MemoryRepo:
    """The repository contract in memory: rows {uid: (version, image, checked_at)}."""
    def __init__(self):
        self.rows, self.saves, self.touches = {}, 0, 0

    async def stored(self, db, user_ids):
        return {uid: StoredPhoto(v, img is not None, at) for uid, (v, img, at) in self.rows.items() if uid in user_ids}

    async def image(self, db, user_id):
        row = self.rows.get(user_id)
        return (row[0], row[1]) if row and row[1] else None

    async def save(self, db, user_id, version, image):
        self.saves += 1
        self.rows[user_id] = (version if image else None, image, datetime.now(timezone.utc))

    async def touch(self, db, user_id):
        self.touches += 1
        version, image, _ = self.rows[user_id]
        self.rows[user_id] = (version, image, datetime.now(timezone.utc))


async def run_db(action):
    return await action(None)


def reset():
    avatar_photos._inflight.clear()
    avatar_photos._failed_at.clear()


async def main():
    repo = MemoryRepo()
    old = datetime.now(timezone.utc) - timedelta(days=2)
    photo = telegram_photo.PhotoRef(version='uniq-1', file_id='f1')
    with patch.object(avatar_photos, 'repo', repo), patch.object(avatar_photos, '_with_db', run_db), \
         patch.object(telegram_photo, 'shrink', AsyncMock(side_effect=lambda data: WEBP if data else None)):
        # VIP rule first: no lookups at all for a non-VIP.
        with patch.object(telegram_photo, 'current_photo', AsyncMock()) as lookup:
            assert await avatar_photos.view(None, 1, 'r' * 16, vip_active=False) == avatar_photos.AvatarView(None, 'vip_only')
            assert lookup.await_count == 0

        # A Telegram outage keeps the stored photo and pauses the player.
        repo.rows[1] = ('uniq-0', WEBP, old)
        with patch.object(telegram_photo, 'current_photo', AsyncMock(side_effect=telegram_photo.TelegramUnavailable('down'))):
            shown = await avatar_photos.view(None, 1, 'r' * 16, vip_active=True)
            assert shown.state == 'ready' and shown.avatar.startswith('/profile/avatar/' + 'r' * 16 + '?v='), shown
            await avatar_photos._inflight[1]
            assert repo.rows[1][1] == WEBP and repo.saves == 0, 'a failure must not wipe the photo'
            assert avatar_photos.refresh(1) is None, 'paused after a failure'

        # Recovery: a changed photo is downloaded once, concurrent callers share the refresh.
        reset()
        with patch.object(telegram_photo, 'current_photo', AsyncMock(return_value=photo)), \
             patch.object(telegram_photo, 'download_file', AsyncMock(return_value=b'jpeg')) as download:
            first, second = avatar_photos.refresh(1), avatar_photos.refresh(1)
            assert first is second
            await first
            assert download.await_count == 1 and repo.rows[1][0] == 'uniq-1'
            # Same photo next time: only "still current", no download.
            repo.rows[1] = ('uniq-1', WEBP, old)
            await avatar_photos.refresh(1)
            assert download.await_count == 1 and repo.touches == 1

        # Time budget: a hanging Telegram does not block forever and keeps the stored photo.
        reset()
        release = asyncio.Event()

        async def hang(user_id):
            await release.wait()
        with patch.object(telegram_photo, 'current_photo', hang), patch.object(avatar_photos, 'BUDGET_SEC', .05):
            await avatar_photos.refresh(1)
            assert repo.rows[1][1] == WEBP and 1 in avatar_photos._failed_at

        # Hidden from the bot: the player's own signed Mini App URL fills in; a second time it is not re-downloaded.
        reset()
        monitor = RecentDiagnostics()
        with patch.object(avatar_photos, 'support_diagnostics', monitor), \
             patch.object(telegram_photo, 'current_photo', AsyncMock(return_value=None)), \
             patch.object(telegram_photo, 'download_signed', AsyncMock(return_value=b'jpeg')) as signed:
            shown = await avatar_photos.view(None, 2, 's' * 16, vip_active=True, photo_url=URL)
            assert shown == avatar_photos.AvatarView(None, 'loading'), shown
            await avatar_photos._inflight[2]
            assert repo.rows[2][1] == WEBP and repo.rows[2][0].startswith('u:')
            shown = await avatar_photos.view(None, 2, 's' * 16, vip_active=True)
            assert shown.state == 'ready', shown
            repo.rows[2] = (repo.rows[2][0], WEBP, old)
            await avatar_photos.refresh(2, URL)
            assert signed.await_count == 1, 'the same signed photo is not downloaded again'
            assert monitor.overview()['totals']['avatar_miss'] == 0

            # Tops, cards and the admin panel refresh without the signed URL: a photo the bot cannot see is kept.
            repo.rows[2] = (repo.rows[2][0], WEBP, old)
            await avatar_photos.refresh(2)
            assert repo.rows[2][1] == WEBP and repo.saves == 2, 'a signed-URL photo must survive a refresh without the URL'
            # A failed signed download keeps the stored photo too.
            reset()
            repo.rows[2] = ('u:previous', WEBP, old)
            with patch.object(telegram_photo, 'download_signed', AsyncMock(side_effect=telegram_photo.TelegramUnavailable('http 500'))):
                await avatar_photos.refresh(2, URL)
            assert repo.rows[2] == ('u:previous', WEBP, old) and 2 in avatar_photos._failed_at
            # While paused after a failure a player without any stored row is still "loading" (photo expected).
            avatar_photos._failed_at[4] = avatar_photos.time.monotonic()
            assert (await avatar_photos.view(None, 4, 'q' * 16, vip_active=True)).state == 'loading'

            # No photo anywhere: "absent", cached; the miss is visible in diagnostics.
            await avatar_photos.refresh(3)
            assert repo.rows[3][1] is None
            assert (await avatar_photos.view(None, 3, 't' * 16, vip_active=True)).state == 'absent'
            assert monitor.overview()['totals']['avatar_miss'] == 1
            assert 3 not in avatar_photos._inflight, 'a fresh "absent" is not asked again'
    print('avatar recovery: VIP gate, outage keeps photo, pause, single flight, version reuse, budget, signed fallback and states OK')


if __name__ == '__main__':
    asyncio.run(main())
