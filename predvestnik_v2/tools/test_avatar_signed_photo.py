"""Real auth and endpoint regression: signed Mini App photo vs empty Bot API."""
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
from services import presence_v1

URL = "https://t.me/i/userpic/320/signed-photo.jpg"
REAL_CLIENT = httpx.AsyncClient
buffer = BytesIO()
Image.new("RGB", (16, 16), "purple").save(buffer, format="PNG")
PNG = buffer.getvalue()


def signed(user):
    fields = {"auth_date": str(int(time.time())), "user": json.dumps(user, separators=(",", ":"))}
    secret = hmac.new(b"WebAppData", os.environ["BOT_TOKEN"].encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, "\n".join(f"{k}={v}" for k,v in sorted(fields.items())).encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


@asynccontextmanager
async def connection():
    yield object()


async def main():
    app = FastAPI()
    app.include_router(profile.router)
    profile._AVATAR_CACHE.clear()
    requests = []
    status, body = 200, PNG
    def handler(request):
        requests.append(request.url)
        return httpx.Response(status, content=body)
    def client(**kwargs):
        return REAL_CLIENT(transport=httpx.MockTransport(handler), **kwargs)
    logs = []
    sink = logger.add(lambda message: logs.append(str(message)))
    try:
        with ExitStack() as stack:
            for target,name,value in (
                (profile,"create_pool",AsyncMock()), (profile,"get_pool",lambda: SimpleNamespace(acquire=connection)),
                (profile,"PGAdapter",lambda conn: object()), (profile,"assert_account_active",AsyncMock()),
                (profile,"is_vip_active",AsyncMock(return_value=True)),
                (profile.public_profiles,"resolve_reference",AsyncMock(return_value=2)),
                (profile,"_fetch_tg_avatar",AsyncMock(return_value=None)),
                (deps,"_capture_signals",AsyncMock()), (presence_v1,"note_activity",AsyncMock()),
                (telegram_photo.httpx,"AsyncClient",client),
            ):
                stack.enter_context(patch.object(target,name,value))
            async with REAL_CLIENT(transport=httpx.ASGITransport(app=app),base_url="http://test") as api:
                # The former bot-only path returns no photo even with an active VIP.
                baseline=await api.get("/profile/avatar",headers={"x-init-data":signed({"id":1,"first_name":"QA"})})
                assert baseline.json() == {"avatar":None,"vip":True}
                auth=signed({"id":1,"first_name":"QA","photo_url":URL})
                # A prior BotAPI-only miss is retried after the short TTL;
                # the profile's 0/2/6/12-second retries span this boundary.
                assert (await api.get("/profile/avatar",headers={"x-init-data":auth})).json()["avatar"] is None
                assert not requests
                profile._AVATAR_CACHE[1] = (None,time.time()-profile._AVATAR_MISS_TTL-1)
                response=await api.get("/profile/avatar",headers={"x-init-data":auth})
                assert response.status_code == 200 and response.json()["avatar"].startswith("data:image/png;base64,"),response.text
                assert len(requests) == 1 and str(requests[0]) == URL
                before=len(requests)
                assert (await api.get("/profile/avatar",headers={"x-init-data":auth.replace("signed-photo","forged-photo")})).status_code == 401
                assert len(requests) == before
                # A viewer's authenticated photo never becomes someone else's.
                response=await api.get("/profile/avatar?profile_ref=other",headers={"x-init-data":auth})
                assert response.json() == {"avatar":None,"vip":True} and len(requests) == before
                profile._AVATAR_CACHE.clear()
                profile.is_vip_active.return_value=False
                assert (await api.get("/profile/avatar",headers={"x-init-data":auth})).json() == {"avatar":None,"vip":False}
                assert len(requests) == before
                profile.is_vip_active.return_value=True
                for invalid in ("http://t.me/i/userpic/a", "https://t.me.evil.test/i/userpic/a", "https://127.0.0.1/i/userpic/a", "https://t.me:8443/i/userpic/a", "https://user@t.me/i/userpic/a", "https://t.me/other"):
                    assert await telegram_photo.download_signed_photo(invalid,1) is None
                assert len(requests) == before
                status=302
                assert await telegram_photo.download_signed_photo(URL,1) is None
                assert len(requests) == before+1, "redirect was not followed"
                status,body=200,b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"
                assert await telegram_photo.download_signed_photo(URL,1) is None
                body=b"x"*(telegram_photo.MAX_BYTES+1)
                assert await telegram_photo.download_signed_photo(URL,1) is None
                # Bad/expired signed source falls back to the existing Bot API path.
                profile._fetch_tg_avatar.return_value="data:image/jpeg;base64,AAAA"
                result=await api.get("/profile/avatar",headers={"x-init-data":auth})
                assert result.json()["avatar"] == "data:image/jpeg;base64,AAAA"
                assert not any(URL in line or os.environ["BOT_TOKEN"] in line for line in logs)
        print("PASS: real signed initData -> avatar endpoint -> raster photo; tampering, VIP, cross-user isolation, host/redirect/size/SVG guards and Bot API fallback")
    finally:
        logger.remove(sink)


if __name__ == "__main__":
    asyncio.run(main())
