"""Картинки патч-ноутов: фирменная обложка, когда скриншота нет, и чистка загруженных фото.

Загруженное фото всегда перекодируется: уходят EXIF (место съёмки, модель телефона) и лишние пиксели,
а Telegram получает файл, который точно примет (до 2560 px по большей стороне).
"""
from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from core import patch_notes as rules

_FONTS = Path(__file__).resolve().parents[1] / "bot" / "chat" / "assets" / "fonts"
W, H = 1280, 720
INK, MUTED, ACCENT = (244, 241, 255), (168, 160, 196), (176, 150, 255)


class ImageRejected(ValueError):
    pass


def _font(weight: int, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_FONTS / f"Onest-{weight}.ttf"), size)


def _background() -> Image.Image:
    img = Image.new("RGB", (W, H), (8, 9, 12))
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse((W - 700, -360, W + 260, 460), fill=255)
    glow = glow.filter(ImageFilter.GaussianBlur(170))
    tint = Image.new("RGB", (W, H), (70, 44, 150))
    img = Image.composite(tint, img, glow.point(lambda v: int(v * 0.7)))
    draw = ImageDraw.Draw(img)
    for i, r in enumerate((150, 112, 74)):
        draw.ellipse((W - 250 - r, 210 - r, W - 250 + r, 210 + r), outline=(120, 96, 210), width=2 if i else 3)
    draw.ellipse((W - 262, 198, W - 238, 222), fill=ACCENT)
    return img


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int, lines: int) -> list[str]:
    out, line = [], ""
    words: list[str] = []
    for word in text.split():   # короткие предлоги и союзы не висят в конце строки
        if words and len(words[-1].split(" ")[-1]) <= 2:
            words[-1] += " " + word
        else:
            words.append(word)
    for word in words:
        probe = f"{line} {word}".strip()
        if draw.textlength(probe, font=font) <= width or not line:
            line = probe
        else:
            out.append(line)
            line = word
    out.append(line)
    if len(out) > lines:
        out = out[:lines]
        out[-1] = out[-1].rstrip(" ,.") + "…"
    return out


@lru_cache(maxsize=32)
def cover(title: str, kind: str = "new") -> bytes:
    """Обложка 1280×720: «Предвестник · обновление», метка пункта и заголовок крупно."""
    img = _background()
    draw = ImageDraw.Draw(img)
    draw.text((88, 92), "ПРЕДВЕСТНИК · ОБНОВЛЕНИЕ", font=_font(500, 30), fill=MUTED)
    label = rules.KIND_LABEL.get(kind, "Новое")
    pill = _font(700, 30)
    pw = draw.textlength(label, font=pill)
    draw.rounded_rectangle((88, 160, 88 + pw + 44, 214), radius=27, fill=(52, 38, 104), outline=ACCENT, width=2)
    draw.text((110, 166), label, font=pill, fill=INK)
    big = _font(700, 72)
    y = 300
    for line in _wrap(draw, title, big, W - 300, 3):
        draw.text((88, y), line, font=big, fill=INK)
        y += 92
    draw.text((88, H - 92), "t.me/predvestnik_official", font=_font(400, 28), fill=MUTED)
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


def normalize_upload(raw: bytes) -> tuple[bytes, str, int, int]:
    """Проверить и перекодировать загруженное фото. Возвращает (байты, mime, ширина, высота)."""
    if not rules.IMAGE_MIN_BYTES <= len(raw) <= rules.UPLOAD_MAX_BYTES:
        raise ImageRejected("Фото должно весить от 2 КБ до 10 МБ.")
    Image.MAX_IMAGE_PIXELS = rules.UPLOAD_MAX_PIXELS
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            if probe.format not in {"PNG", "JPEG", "WEBP"}:
                raise ImageRejected("Подходят PNG, JPEG или WebP.")
            probe.verify()
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
        img.load()
    except ImageRejected:
        raise
    except Exception:
        raise ImageRejected("Файл не читается как изображение.") from None
    if min(img.size) < 200 or max(img.size) / max(1, min(img.size)) > 4:
        raise ImageRejected("Фото слишком маленькое или слишком вытянутое (нужно от 200 px, соотношение до 1:4).")
    img.thumbnail((rules.UPLOAD_MAX_SIDE, rules.UPLOAD_MAX_SIDE), Image.LANCZOS)
    out = io.BytesIO()
    if img.mode in ("RGBA", "LA", "P"):
        img.convert("RGBA").save(out, "PNG", optimize=True)
        mime = "image/png"
    else:
        img.convert("RGB").save(out, "JPEG", quality=90, optimize=True)
        mime = "image/jpeg"
    data = out.getvalue()
    if len(data) > rules.IMAGE_MAX_BYTES:
        out = io.BytesIO()
        img.convert("RGB").save(out, "JPEG", quality=82, optimize=True)
        data, mime = out.getvalue(), "image/jpeg"
    return data, mime, img.width, img.height
