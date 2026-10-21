"""Анимированная карточка «бот я» для скина на SSS: частицы мерцают и плавно кружат, остальное неподвижно.

Видео MP4 (H.264) без звука: Telegram показывает его как GIF, по кругу и без кнопки. Кодирует PyAV (`av` в requirements).
Нет библиотеки или не успели — вызывающий шлёт обычную картинку (bot/chat/skin_card.py)."""
from __future__ import annotations

import io
import math

from PIL import Image

from bot.chat.skin_card_draw import draw_particles, particle_field

FPS = 12
FRAMES = 24          # две секунды по кругу: последний кадр переходит в первый без скачка


def available() -> bool:
    try:
        import av   # noqa: F401
        return True
    except Exception:
        return False


def animate(base: Image.Image, skin_id: str, tier: str) -> bytes:
    """base — карточка без частиц (декор, график, шапка). Возвращает MP4."""
    import av
    field = particle_field(skin_id, tier)
    out = io.BytesIO()
    with av.open(out, mode="w", format="mp4") as container:
        stream = container.add_stream("libx264", rate=FPS)
        stream.width, stream.height = base.width - base.width % 2, base.height - base.height % 2
        stream.pix_fmt = "yuv420p"
        stream.options = {"crf": "24", "preset": "veryfast", "tune": "animation"}
        for i in range(FRAMES):
            frame_img = base.copy()
            draw_particles(frame_img, skin_id, field, phase=2 * math.pi * i / FRAMES)
            frame = av.VideoFrame.from_image(frame_img.convert("RGB").crop((0, 0, stream.width, stream.height)))
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return out.getvalue()
