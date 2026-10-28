"""Player photos for the Mini App and the admin panel.

Rules:
- the Mini App shows a photo only while the player has an active VIP (perk); everyone else gets
  ``avatar=None`` with ``avatar_state="vip_only"``; the admin panel shows every player's photo;
- photos live in PostgreSQL (infrastructure/repositories/avatar_photos.py), so a deploy loses nothing;
- the Mini App gets a short address ``/profile/avatar/{profile_ref}?v=…`` instead of image bytes inside JSON;
  that address checks VIP again on every request (FastAPI/routers/profile.py);
- Telegram is asked in the background, one download per player at a time, with a time budget, and
  never while a database connection is held.

``avatar_state`` tells the client what to do: ``ready`` (show ``avatar``), ``loading`` (the photo is being
fetched: ask again a little later), ``absent`` (no photo visible to the bot: show the placeholder, do not
ask again), ``vip_only`` (not a VIP: placeholder, do not ask again).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import time
from typing import Literal

from loguru import logger

from infrastructure import telegram_photo
from infrastructure.database import create_pool, get_pool
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import avatar_photos as repo
from services.support_diagnostics import recent as support_diagnostics

AvatarState = Literal["ready", "loading", "absent", "vip_only"]
PHOTO_TTL = 24 * 3600     # a stored photo is re-checked daily (one Bot API call; downloaded again only if it changed)
MISS_TTL = 30 * 60        # "no photo" is re-checked after half an hour
FAILURE_PAUSE = 60        # after a Telegram failure the same player is not retried sooner
BUDGET_SEC = 8.0          # one whole refresh: lookup + download + shrink
_SIGNED_PREFIX = "u:"     # version of a photo taken from the owner's signed Mini App URL
_GATE = asyncio.Semaphore(4)
_inflight: dict[int, asyncio.Task] = {}
_failed_at: dict[int, float] = {}


@dataclass(frozen=True)
class AvatarView:
    avatar: str | None
    state: AvatarState


def _tag(version: str) -> str:
    return hashlib.sha256(version.encode()).hexdigest()[:16]


def image_etag(version: str) -> str:
    return f'"{_tag(version)}"'


def avatar_path(profile_ref: str, version: str) -> str:
    """Relative address; the client prefixes its base path."""
    return f"/profile/avatar/{profile_ref}?v={_tag(version)}"


async def _with_db(action):
    await create_pool()
    async with get_pool().acquire() as conn:
        return await action(PGAdapter(conn))


async def _refresh(user_id: int, photo_url: str | None) -> None:
    async with _GATE:
        try:
            async with asyncio.timeout(BUDGET_SEC):
                await _refresh_now(user_id, photo_url)
            _failed_at.pop(user_id, None)
        except (telegram_photo.TelegramUnavailable, TimeoutError) as error:
            # Keep whatever is stored: a Telegram hiccup must not wipe a known photo.
            _failed_at[user_id] = time.monotonic()
            support_diagnostics.record(user_id, "avatar", {"stage": "refresh", "outcome": "error", "error_kind": type(error).__name__})
            logger.warning("avatar uid={} refresh failed: {}", user_id, type(error).__name__)
        except Exception:   # a background task: an unexpected error is logged here, not lost
            _failed_at[user_id] = time.monotonic()
            logger.exception("avatar uid={} refresh crashed", user_id)


async def _refresh_now(user_id: int, photo_url: str | None) -> None:
    stored = (await _with_db(lambda db: repo.stored(db, [user_id]))).get(user_id)
    found = await telegram_photo.current_photo(user_id)
    version, image, source = None, None, "botapi"
    if found:
        if stored and stored.has_image and stored.version == found.version:
            await _with_db(lambda db: repo.touch(db, user_id))
            return
        version, image = found.version, await telegram_photo.shrink(await telegram_photo.download_file(found.file_id))
    if image is None and photo_url and telegram_photo.valid_url(photo_url):
        # Privacy settings may hide the photo from bots while Telegram still signs it for the Mini App.
        source, version = "webapp", _SIGNED_PREFIX + hashlib.sha256(photo_url.encode()).hexdigest()[:32]
        if stored and stored.has_image and stored.version == version:
            await _with_db(lambda db: repo.touch(db, user_id))
            return
        image = await telegram_photo.shrink(await telegram_photo.download_signed(photo_url, user_id))
    elif found is None and stored and stored.has_image and (stored.version or "").startswith(_SIGNED_PREFIX):
        # A photo only the owner's own launch can renew (tops, cards and the admin panel have no signed URL):
        # the bot not seeing it is expected, not a reason to forget it.
        await _with_db(lambda db: repo.touch(db, user_id))
        return
    await _with_db(lambda db: repo.save(db, user_id, version, image))
    support_diagnostics.record(user_id, "avatar", {"source": source, "stage": "final", "outcome": "photo" if image else "empty"})
    logger.info("avatar uid={} source={} result={}", user_id, source, "photo" if image else "empty")


def refresh(user_id: int, photo_url: str | None = None) -> asyncio.Task | None:
    """Start (or join) the background refresh; None while the player is paused after a Telegram failure."""
    uid = int(user_id)
    task = _inflight.get(uid)
    if task is not None:
        return task
    failed = _failed_at.get(uid)
    if failed is not None and time.monotonic() - failed < FAILURE_PAUSE:
        return None
    task = asyncio.create_task(_refresh(uid, photo_url))
    _inflight[uid] = task
    task.add_done_callback(lambda _t: _inflight.pop(uid, None))
    if len(_failed_at) > 10_000:
        _failed_at.clear()
    return task


def _stale(stored: repo.StoredPhoto) -> bool:
    age = time.time() - stored.checked_at.timestamp()
    return age > (PHOTO_TTL if stored.has_image else MISS_TTL)


async def views(db, players: dict[int, str], *, photo_urls: dict[int, str] | None = None) -> dict[int, AvatarView]:
    """Avatars of VIP players ({user_id: profile_ref}); the caller has already checked VIP.
    Missing or old photos are refreshed in the background; the answer never waits for Telegram."""
    try:
        stored = await repo.stored(db, list(players))
    except Exception:   # a photo is decoration: its storage failing must not take the profile or the top down
        logger.exception("avatar views unavailable")
        return {uid: AvatarView(None, "absent") for uid in players}
    result = {}
    for uid, ref in players.items():
        row = stored.get(uid)
        if row is None or _stale(row):
            refresh(uid, (photo_urls or {}).get(uid))
        if row and row.has_image:
            result[uid] = AvatarView(avatar_path(ref, row.version), "ready")
        elif row is None:
            result[uid] = AvatarView(None, "loading")   # being fetched, or retried after a Telegram failure
        else:
            result[uid] = AvatarView(None, "absent")
    return result


async def view(db, user_id: int, profile_ref: str, *, vip_active: bool, photo_url: str | None = None) -> AvatarView:
    if not vip_active:
        return AvatarView(None, "vip_only")
    return (await views(db, {int(user_id): profile_ref}, photo_urls={int(user_id): photo_url} if photo_url else None))[int(user_id)]


async def wait_for_refresh(user_id: int) -> None:
    """Wait (at most BUDGET_SEC) for a running refresh; holds no database connection."""
    task = _inflight.get(int(user_id))
    if task is not None:
        try:
            await asyncio.wait_for(asyncio.shield(task), BUDGET_SEC)
        except TimeoutError:
            pass


async def image_for_admin(user_id: int) -> bytes | None:
    """Admin panel: every player's photo (no VIP rule), refreshed first when missing or old."""
    uid = int(user_id)
    row = (await _with_db(lambda db: repo.stored(db, [uid]))).get(uid)
    if row is None or _stale(row):
        refresh(uid)
        if row is None:
            await wait_for_refresh(uid)
    stored = await _with_db(lambda db: repo.image(db, uid))
    return stored[1] if stored else None
