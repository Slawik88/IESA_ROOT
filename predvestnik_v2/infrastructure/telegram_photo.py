"""Download the Telegram photo URL from an already verified WebApp user."""
import asyncio
import base64
from io import BytesIO
from urllib.parse import urlsplit

import httpx
from loguru import logger
from PIL import Image, UnidentifiedImageError

MAX_BYTES = 2 * 1024 * 1024
MAX_PIXELS = 4096 * 4096
MIME_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


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


def _data_uri(data: bytes) -> str | None:
    try:
        with Image.open(BytesIO(data)) as image:
            mime = MIME_TYPES.get(image.format)
            if not mime or image.width * image.height > MAX_PIXELS:
                return None
            image.verify()
        return f"data:{mime};base64,{base64.b64encode(data).decode()}"
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return None


async def download_signed_photo(url: str | None, user_id: int) -> str | None:
    """No arbitrary hosts, redirects, SVG or unbounded response bodies."""
    if not valid_url(url):
        return None
    try:
        async with httpx.AsyncClient(timeout=6, follow_redirects=False) as client:
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    logger.info("avatar uid={} source=webapp status={}", user_id, response.status_code)
                    return None
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        logger.warning("avatar uid={} source=webapp oversized", user_id)
                        return None
        avatar = await asyncio.to_thread(_data_uri, bytes(data))
        logger.info("avatar uid={} source=webapp result={}", user_id, "photo" if avatar else "invalid_image")
        return avatar
    except (httpx.HTTPError, ValueError) as error:
        # Exception text may contain URLs; log only the safe exception class.
        logger.warning("avatar uid={} source=webapp error={}", user_id, type(error).__name__)
        return None
