"""Telegram profile photos: Bot API lookup, signed Mini App photo URL, shrink to a small WebP.

One long-lived HTTP client serves every download (a new client per photo meant a new TLS handshake each time).
Nothing here logs a URL, the bot token or exception text: Telegram file URLs contain the token.
"""
import asyncio
from dataclasses import dataclass
from io import BytesIO
import os
from urllib.parse import urlsplit

import httpx
from loguru import logger
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 2 * 1024 * 1024
MAX_PIXELS = 4096 * 4096
SIDE = 128            # stored square side: enough for every avatar circle in the app and the admin panel at 2x
WEBP_QUALITY = 82
# Separate limits per step; the whole refresh has its own budget (services/avatar_photos.BUDGET_SEC).
TIMEOUT = httpx.Timeout(connect=3.0, read=5.0, write=5.0, pool=3.0)
_API = "https://api.telegram.org"
_client: httpx.AsyncClient | None = None


class TelegramUnavailable(Exception):
    """Telegram did not answer or answered with an error: keep the stored photo and try later."""


@dataclass(frozen=True)
class PhotoRef:
    version: str     # file_unique_id of the chosen size: stays the same while the photo is the same
    file_id: str


def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False)
    return _client


def _token() -> str:
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        raise TelegramUnavailable("no bot token")
    return token


async def _bot_api(method: str, params: dict) -> dict:
    try:
        response = await client().get(f"{_API}/bot{_token()}/{method}", params=params)
        answer = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise TelegramUnavailable(type(error).__name__) from None
    if not answer.get("ok"):
        # 400 "user not found"-style answers are final; anything else is Telegram trouble.
        if answer.get("error_code") == 400:
            return {}
        raise TelegramUnavailable(f"bot api {answer.get('error_code')}")
    return answer.get("result") or {}


def _pick_size(sizes: list[dict]) -> dict | None:
    """Sizes go from small to large: the smallest one that still fills SIDE, else the largest."""
    usable = [s for s in sizes if min(s.get("width") or 0, s.get("height") or 0) >= SIDE]
    if usable:
        return min(usable, key=lambda s: (s.get("width") or 0) * (s.get("height") or 0))
    return sizes[-1] if sizes else None


async def current_photo(user_id: int) -> PhotoRef | None:
    """The photo the bot sees now, or None (no photo, or privacy settings hide it from bots)."""
    result = await _bot_api("getUserProfilePhotos", {"user_id": int(user_id), "limit": 1})
    photos = result.get("photos") or []
    size = _pick_size(photos[0]) if photos else None
    if not size or not size.get("file_id") or not size.get("file_unique_id") or (size.get("file_size") or 0) > MAX_BYTES:
        return None
    return PhotoRef(version=str(size["file_unique_id"]), file_id=str(size["file_id"]))


async def download_file(file_id: str) -> bytes:
    found = await _bot_api("getFile", {"file_id": file_id})
    path = found.get("file_path")
    if not path:
        raise TelegramUnavailable("no file path")
    return await _read_capped(f"{_API}/file/bot{_token()}/{path}")


async def _read_capped(url: str) -> bytes:
    try:
        async with client().stream("GET", url) as response:
            if response.status_code != 200:
                raise TelegramUnavailable(f"http {response.status_code}")
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > MAX_BYTES:
                    raise TelegramUnavailable("oversized")
            return bytes(data)
    except httpx.HTTPError as error:
        raise TelegramUnavailable(type(error).__name__) from None


def valid_url(value: str | None) -> bool:
    if not isinstance(value, str):
        return False
    try:
        url = urlsplit(value)
        return (url.scheme == "https" and url.hostname in {"t.me", "telegram.org"}
                and url.port in {None, 443} and not url.username and not url.password
                and url.path.startswith("/i/userpic/") and not url.fragment)
    except ValueError:
        return False


async def download_signed(url: str | None, user_id: int) -> bytes | None:
    """The photo URL from the owner's own signed initData. No arbitrary hosts, redirects or unbounded bodies.
    None for a URL that is not Telegram's; TelegramUnavailable when the download fails (the stored photo stays)."""
    if not valid_url(url):
        return None
    try:
        return await _read_capped(url)
    except TelegramUnavailable as error:
        logger.info("avatar uid={} source=webapp result={}", user_id, error)
        raise


def _shrink(data: bytes) -> bytes | None:
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"} or image.width * image.height > MAX_PIXELS:
                return None
            image.load()
            square = ImageOps.fit(image.convert("RGB"), (SIDE, SIDE), Image.Resampling.LANCZOS)
        out = BytesIO()
        square.save(out, format="WEBP", quality=WEBP_QUALITY, method=4)
        return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return None


async def shrink(data: bytes | None) -> bytes | None:
    """A raster photo as a SIDE x SIDE WebP; None for SVG, broken or oversized images."""
    return await asyncio.to_thread(_shrink, data) if data else None
