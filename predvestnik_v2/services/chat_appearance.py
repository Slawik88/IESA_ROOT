"""Automatic chat colours from Telegram photos; bounded background I/O and no database holds."""
import asyncio
import base64
import colorsys
import hashlib
import io
import os
import time
from collections import OrderedDict

import httpx
from PIL import Image, UnidentifiedImageError
from loguru import logger

MAX_BYTES = 2 * 1024 * 1024
CACHE_SIZE = 512
PHOTO_TTL = 6 * 3600
MISS_TTL = 60


def _palette(rgb: tuple[int,int,int]) -> list[str]:
    # hls returns hue, lightness, saturation. Keep accents visible on dark cards.
    hue,_,saturation = colorsys.rgb_to_hls(*(c/255 for c in rgb))
    saturation = min(.72,max(.35,saturation))
    def colour(h,s,l):
        return "#"+"".join(f"{round(c*255):02x}" for c in colorsys.hls_to_rgb(h%1,l,s))
    return [colour(hue,saturation,.66),colour(hue+.10,saturation,.56),colour(hue-.08,saturation*.8,.78)]


def fallback_palette(chat_id: int) -> list[str]:
    raw=hashlib.blake2s(str(chat_id).encode(),digest_size=3).digest()
    return _palette(tuple(raw))


def from_photo(data: bytes) -> dict:
    if len(data)>MAX_BYTES:
        raise ValueError("chat photo too large")
    with Image.open(io.BytesIO(data)) as source:
        if source.width*source.height>16_000_000:
            raise ValueError("chat photo dimensions too large")
        source=source.convert("RGBA")
        background=Image.new("RGBA",source.size,(14,16,25,255));background.alpha_composite(source)
        image=background.convert("RGB");image.thumbnail((160,160))
        sample=image.copy();sample.thumbnail((32,32))
        colours=sample.quantize(colors=8).convert("RGB").getcolors(1024) or []
        def weight(entry):
            count,rgb=entry
            _,light,saturation=colorsys.rgb_to_hls(*(c/255 for c in rgb))
            return count*(.2+saturation) if .10<light<.9 else count*.03
        rgb=max(colours,key=weight)[1] if colours else (120,140,190)
        output=io.BytesIO();image.save(output,format="JPEG",quality=80)
    return {"avatar":"data:image/jpeg;base64,"+base64.b64encode(output.getvalue()).decode(),"palette":_palette(rgb)}


async def _download(chat_id: int) -> bytes | None:
    token=os.getenv("BOT_TOKEN","")
    if not token:
        return None
    async with httpx.AsyncClient(timeout=4) as client:
        async def call(method,params):
            response=await client.get(f"https://api.telegram.org/bot{token}/{method}",params=params)
            response.raise_for_status()
            payload=response.json()
            if not payload.get("ok"):
                raise ValueError("Telegram rejected chat photo lookup")
            return payload["result"]
        chat=await call("getChat",{"chat_id":chat_id})
        photo=chat.get("photo")
        if not photo:
            return None
        file=await call("getFile",{"file_id":photo["small_file_id"]})
        async with client.stream("GET",f"https://api.telegram.org/file/bot{token}/{file['file_path']}") as response:
            response.raise_for_status()
            data=bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data)>MAX_BYTES:
                    raise ValueError("chat photo download too large")
            return bytes(data)


class ChatAppearanceCache:
    def __init__(self):
        self.entries=OrderedDict()
        self.inflight={}
        self.gate=asyncio.Semaphore(4)

    async def refresh(self, chat_id: int) -> None:
        previous=self.entries.get(chat_id)
        try:
            async with self.gate:
                data=await asyncio.wait_for(_download(chat_id),8)
                value=await asyncio.to_thread(from_photo,data) if data else None
            self.entries[chat_id]=(time.monotonic()+(PHOTO_TTL if value else MISS_TTL),value)
        except (httpx.HTTPError,ValueError,KeyError,UnidentifiedImageError,Image.DecompressionBombError,TimeoutError,OSError) as error:
            logger.debug("Chat photo refresh failed for {}: {}",chat_id,type(error).__name__)
            # Transient failures retain the last photo, but retry after a minute.
            self.entries[chat_id]=(time.monotonic()+MISS_TTL,previous[1] if previous else None)
        finally:
            self.inflight.pop(chat_id,None)
            while len(self.entries)>CACHE_SIZE:
                self.entries.popitem(last=False)

    def project(self, chat_id: int) -> dict:
        entry=self.entries.get(chat_id)
        if (entry is None or entry[0]<time.monotonic()) and chat_id not in self.inflight and len(self.inflight)<100:
            self.inflight[chat_id]=asyncio.create_task(self.refresh(chat_id))
        value=entry[1] if entry else None
        return {"kind":"chat","avatar":value["avatar"] if value else None,
                "palette":value["palette"] if value else fallback_palette(chat_id),"avatar_pending":chat_id in self.inflight}


CACHE=ChatAppearanceCache()
