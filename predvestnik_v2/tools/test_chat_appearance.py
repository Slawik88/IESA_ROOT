"""Photo palettes and bounded, nonblocking cache recovery without Telegram."""
import asyncio
import io
import pathlib
import re
import sys
import time
from unittest.mock import AsyncMock,patch
from PIL import Image
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from services import chat_appearance as appearance


def photo(colour):
    out=io.BytesIO();Image.new("RGB",(160,160),colour).save(out,format="PNG");return out.getvalue()


async def main():
    red=appearance.from_photo(photo((230,35,50)))
    blue=appearance.from_photo(photo((35,80,230)))
    assert red["palette"]!=blue["palette"]
    assert all(re.fullmatch(r"#[0-9a-f]{6}",c) for c in red["palette"]+blue["palette"])
    assert red["avatar"].startswith("data:image/jpeg;base64,")
    assert appearance.fallback_palette(-12)==appearance.fallback_palette(-12)
    cache=appearance.ChatAppearanceCache();release=asyncio.Event()
    async def slow(_):
        await release.wait();return photo((230,35,50))
    with patch.object(appearance,"_download",slow):
        before=time.monotonic();first=cache.project(-12);second=cache.project(-12)
        assert time.monotonic()-before<.05 and first["avatar_pending"] and second["avatar_pending"]
        assert len(cache.inflight)==1
        task=cache.inflight[-12];release.set();await task
        result=cache.project(-12)
        assert result["avatar"] and not result["avatar_pending"]
    cache.entries[-12]=(0,red)
    with patch.object(appearance,"_download",AsyncMock(side_effect=TimeoutError())):
        assert cache.project(-12)["avatar"]==red["avatar"]
        await cache.inflight[-12]
        assert cache.project(-12)["avatar"]==red["avatar"]
    cache.entries[-12]=(0,red)
    with patch.object(appearance,"_download",AsyncMock(return_value=None)):
        cache.project(-12);await cache.inflight[-12]
        assert cache.project(-12)["avatar"] is None
    print("PASS: photo-driven palettes, stable no-photo fallback, immediate projection, single-flight, transient recovery and removed photo")


if __name__=="__main__":asyncio.run(main())
