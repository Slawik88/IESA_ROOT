"""Real auth and endpoint regression: signed Mini App photo vs empty Bot API, photo address and VIP gate.

Real signed initData -> /profile/avatar (waits for the background refresh) -> real download through the shared
HTTP client (mock transport) -> real shrink to WebP -> /profile/avatar/{ref} serves it with ETag. Tampering,
cross-user isolation, the VIP rule on the direct address, host/redirect/size/SVG guards; no URL or token in logs.
"""
import asyncio
from contextlib import asynccontextmanager, ExitStack
import hashlib
import hmac
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from urllib.parse import urlencode
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI
from loguru import logger
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("BOT_TOKEN", "123456:offline-avatar-test")
os.environ.setdefault("DATABASE_URL", "postgresql://offline@127.0.0.1:1/offline")
from FastAPI import deps
from FastAPI.routers import profile
from infrastructure import telegram_photo
from services import avatar_photos, presence_v1
from test_avatar_recovery import MemoryRepo, run_db

URL = "https://t.me/i/userpic/320/signed-photo.jpg"
OWN_REF, OTHER_REF = "own-ref-0123456789ab", "other-ref-0123456789"
buffer = BytesIO()
Image.new("RGB", (400, 300), "purple").save(buffer, format="PNG")
PNG = buffer.getvalue()


def signed(user):
    fields = {"auth_date": str(int(time.time())), "user": json.dumps(user, separators=(",", ":"))}
    secret = hmac.new(b"WebAppData", os.environ["BOT_TOKEN"].encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, "\n".join(f"{k}={v}" for k,v in sorted(fields.items())).encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


async def refused(download) -> None:
    """A failed download raises, so the refresh keeps the stored photo instead of saving "no photo"."""
    try:
        await download
    except telegram_photo.TelegramUnavailable:
        return
    raise AssertionError("download should have been refused")


@asynccontextmanager
async def connection():
    yield object()


async def main():
    app = FastAPI()
    app.include_router(profile.router)
    repo = MemoryRepo()
    requests = []
    state = {"status": 200, "body": PNG}

    def handler(request):
        requests.append(request.url)
        return httpx.Response(state["status"], content=state["body"])
    refs = {OWN_REF: 1, OTHER_REF: 2}
    logs = []
    sink = logger.add(lambda message: logs.append(str(message)))
    try:
        with ExitStack() as stack:
            for target, name, value in (
                (profile, "create_pool", AsyncMock()), (profile, "get_pool", lambda: SimpleNamespace(acquire=connection)),
                (profile, "PGAdapter", lambda conn: object()), (profile, "assert_account_active", AsyncMock()),
                (profile, "is_vip_active", AsyncMock(return_value=True)),
                (profile.public_profiles, "resolve_reference", AsyncMock(side_effect=lambda db, profile_ref: refs.get(profile_ref))),
                (profile.public_profiles, "ensure_reference", AsyncMock(side_effect=lambda db, user_id: {1: OWN_REF, 2: OTHER_REF}[user_id])),
                (profile, "avatar_photo_repo", repo), (avatar_photos, "repo", repo), (avatar_photos, "_with_db", run_db),
                (telegram_photo, "current_photo", AsyncMock(return_value=None)),   # privacy hides the photo from the bot
                (telegram_photo, "_client", httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=telegram_photo.TIMEOUT)),
                (deps, "_capture_signals", AsyncMock()), (presence_v1, "note_activity", AsyncMock()),
            ):
                stack.enter_context(patch.object(target, name, value))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
                # Without a signed photo URL and with an empty Bot API there is no photo: a final answer.
                baseline = await api.get("/profile/avatar", headers={"x-init-data": signed({"id": 1, "first_name": "QA"})})
                assert baseline.json() == {"avatar": None, "vip": True, "avatar_state": "absent"}, baseline.text
                assert not requests
                repo.rows.clear()
                auth = signed({"id": 1, "first_name": "QA", "photo_url": URL})
                response = await api.get("/profile/avatar", headers={"x-init-data": auth})
                body = response.json()
                assert body["avatar_state"] == "ready" and body["avatar"].startswith(f"/profile/avatar/{OWN_REF}?v="), body
                assert len(requests) == 1 and str(requests[0]) == URL
                image = await api.get(body["avatar"])
                assert image.status_code == 200 and image.headers["content-type"] == "image/webp", image.status_code
                with Image.open(BytesIO(image.content)) as shown:
                    assert shown.format == "WEBP" and shown.size == (telegram_photo.SIDE, telegram_photo.SIDE)
                assert (await api.get(body["avatar"], headers={"if-none-match": image.headers["etag"]})).status_code == 304
                before = len(requests)
                assert (await api.get("/profile/avatar", headers={"x-init-data": auth.replace("signed-photo", "forged-photo")})).status_code == 401
                assert len(requests) == before
                # A viewer's authenticated photo never becomes someone else's.
                other = await api.get(f"/profile/avatar?profile_ref={OTHER_REF}", headers={"x-init-data": auth})
                assert other.json() == {"avatar": None, "vip": True, "avatar_state": "absent"} and len(requests) == before
                # The VIP rule holds on the direct address too, checked on every request.
                profile.is_vip_active.return_value = False
                assert (await api.get("/profile/avatar", headers={"x-init-data": auth})).json() == {"avatar": None, "vip": False, "avatar_state": "vip_only"}
                assert (await api.get(body["avatar"])).status_code == 404
                assert (await api.get(f"/profile/avatar/{'x' * 20}")).status_code == 404
                assert len(requests) == before
                for invalid in ("http://t.me/i/userpic/a", "https://t.me.evil.test/i/userpic/a", "https://127.0.0.1/i/userpic/a",
                                "https://t.me:8443/i/userpic/a", "https://user@t.me/i/userpic/a", "https://t.me/other"):
                    assert await telegram_photo.download_signed(invalid, 1) is None
                assert len(requests) == before
                state["status"] = 302
                await refused(telegram_photo.download_signed(URL, 1))
                assert len(requests) == before + 1, "redirect was not followed"
                state.update(status=200, body=b"<svg xmlns='http://www.w3.org/2000/svg'></svg>")
                assert await telegram_photo.shrink(await telegram_photo.download_signed(URL, 1)) is None
                state["body"] = b"x" * (telegram_photo.MAX_BYTES + 1)
                await refused(telegram_photo.download_signed(URL, 1))
                assert not any(URL in line or os.environ["BOT_TOKEN"] in line for line in logs)
        print("PASS: real signed initData -> avatar refresh -> WebP address with ETag; tampering, VIP on the direct address, "
              "cross-user isolation, host/redirect/size/SVG guards")
    finally:
        logger.remove(sink)
        avatar_photos._inflight.clear()


if __name__ == "__main__":
    asyncio.run(main())
