"""Картинка «бот я» в стиле скина: график активности в палитре скина внутри карточки с рамкой, фоном и шапкой.

Без скина бот шлёт график как раньше. Тема графика выводится из токенов скина (theme_for), декор — из его видов
(bot/chat/skin_card_draw.py). Сборка идёт в отдельном потоке и ждётся не дольше COMPOSE_BUDGET_SEC: не успели —
уходит обычный график, карточка от этого не страдает. Готовые картинки кэшируются на минуту, декор — на скин и тир."""
from __future__ import annotations

import asyncio
import functools
import hashlib
import io
import threading
import time
from pathlib import Path

from loguru import logger
from PIL import Image, ImageDraw, ImageFont

from bot.chat import activity_graph, skin_motion
from bot.chat.skin_card_draw import GRAPH_H, GRAPH_W, HEAD, M, W, decor, mix, rgb
from core.skins_v3_catalog import SKINS
from core.skins_v3_chat import ChatLook

COMPOSE_BUDGET_SEC = 0.9
MOTION_BUDGET_SEC = 3.0            # видео для SSS; не успели — уходит картинка
CACHE_TTL_SEC = 60.0
MAX_CACHE = 64
DECOR_CACHE = 8                     # ~4 МБ на штуку
_FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
_cache: dict[tuple, tuple[float, bytes]] = {}
_lock = threading.Lock()
_motion_busy = asyncio.Semaphore(1)  # одно видео за раз: второй запрос в это время получает картинку


def theme_for(look: ChatLook) -> str:
    """Зарегистрировать тему графика в палитре скина и вернуть её имя (ключ кэша activity_graph)."""
    name = f"skin:{look.skin_id}"
    if name not in activity_graph.THEMES:
        skin = SKINS[look.skin_id]
        tk, (p0, p1, p2) = skin["tokens"], skin["pal"]
        bg, g = tk["--v3-bg"], tuple(v / 255 for v in rgb(p0))
        hx = lambda c: "#%02x%02x%02x" % c   # noqa: E731
        activity_graph.THEMES[name] = {
            **activity_graph.THEMES[activity_graph.DEFAULT_THEME], "legend": None,
            "bg": bg, "bg_top": hx(mix(bg, p1, .12)), "bg_bot": bg, "bar": hx(mix(p1, p0, .25)),
            "bar_last": p2 if p2.lower() != "#ffffff" else p0, "grid": (*g, .10), "baseline": hx(mix(bg, p0, .28)),
            "avg": hx(mix(bg, p0, .5)), "title": tk["--v3-ink"], "value": p0, "foot": hx(mix(tk["--v3-ink"], p0, .25)),
            "dates": hx(mix(tk["--v3-dim"], p0, .3)), "label": tk["--v3-dim"], "y_label": hx(mix(tk["--v3-dim"], bg, .25)),
            "x_label": tk["--v3-dim"],
        }
    return name


@functools.lru_cache(maxsize=4)
def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_FONT_DIR / f"Onest-{weight}.ttf"), size)


@functools.lru_cache(maxsize=1)
def _glyphs() -> frozenset[int]:
    """Символы, которые есть в шрифте: эмодзи и иероглифы из имени не рисуются квадратиками, их просто нет."""
    try:
        from fontTools.ttLib import TTFont   # приходит вместе с matplotlib
        return frozenset(TTFont(str(_FONT_DIR / "Onest-700.ttf"))["cmap"].getBestCmap())
    except Exception as exc:
        logger.warning(f"Таблица символов шрифта не прочитана, оставляю латиницу и кириллицу: {exc}")
        return frozenset([*range(0x20, 0x7F), *range(0x400, 0x460), 0x2116])


def drawable(text: str | None) -> str:
    cmap = _glyphs()
    return " ".join("".join(ch for ch in (text or "") if ord(ch) in cmap).split())


def _fit(d: ImageDraw.ImageDraw, text: str, font, width: int) -> str:
    if d.textlength(text, font=font) <= width:
        return text
    while text and d.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text.rstrip() + "…"


@functools.lru_cache(maxsize=DECOR_CACHE)
def _decor(skin_id: str, tier: str, particles: bool = True) -> Image.Image:
    return decor(skin_id, tier, particles=particles)


def _header(img: Image.Image, look: ChatLook, name: str, username: str | None) -> None:
    skin = SKINS[look.skin_id]
    tk, p0 = skin["tokens"], skin["pal"][0]
    ink, dim = rgb(tk["--v3-ink"]), rgb(tk["--v3-dim"])
    d = ImageDraw.Draw(img)
    badge_font, small = _font("700", 30), _font("400", 24)
    badge_w = int(d.textlength(look.tier, font=badge_font)) + 40
    right = W - M - 30
    d.rounded_rectangle([right - badge_w, 46, right, 94], 24, fill=rgb(p0) + (255,))
    d.text((right - badge_w + 20, 51), look.tier, font=badge_font, fill=rgb(tk["--v3-on-acc"]))
    if look.name != look.title:
        label = _fit(d, look.name, small, 300)
        d.text((right - d.textlength(label, font=small), 108), label, font=small, fill=dim)
    left, room = M + 30, W - 2 * M - 60 - max(badge_w, 300) - 30
    title_font = _font("700", 50)
    shown = _fit(d, drawable(name) or (f"@{username}" if username else "Игрок"), title_font, room)
    d.text((left, 34), shown, font=title_font, fill=ink)
    used = d.textlength(shown, font=title_font)
    if username and drawable(name) and used + 200 < room:
        d.text((left + used + 16, 54), _fit(d, f"@{username}", _font("500", 28), int(room - used - 16)), font=_font("500", 28), fill=dim)
    d.text((left, 104), _fit(d, look.title, _font("500", 30), room), font=_font("500", 30), fill=rgb(p0))


def _base(png: bytes, look: ChatLook, name: str, username: str | None, particles: bool = True) -> Image.Image:
    graph = Image.open(io.BytesIO(png)).convert("RGBA")
    if graph.size != (GRAPH_W, GRAPH_H):
        graph = graph.resize((GRAPH_W, GRAPH_H), Image.LANCZOS)
    img = _decor(look.skin_id, look.tier, particles).copy()
    rounded = Image.new("L", graph.size, 0)
    ImageDraw.Draw(rounded).rounded_rectangle([0, 0, *graph.size], 22, fill=255)
    img.paste(graph, (M, HEAD), rounded)
    _header(img, look, name, username)
    return img


def compose(png: bytes, look: ChatLook, name: str, username: str | None) -> bytes:
    """JPEG карточки. png — график activity_graph в теме theme_for(look)."""
    out = io.BytesIO()
    _base(png, look, name, username).convert("RGB").save(out, "JPEG", quality=88, optimize=True)
    return out.getvalue()


def motion(png: bytes, look: ChatLook, name: str, username: str | None) -> bytes:
    """MP4 карточки для SSS: частицы движутся (bot/chat/skin_motion.py)."""
    return skin_motion.animate(_base(png, look, name, username, particles=False), look.skin_id, look.tier)


Media = tuple[str, bytes, str]      # ("photo" | "animation", данные, имя файла)


async def _built(key: tuple, build, budget: float) -> bytes | None:
    with _lock:
        hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_TTL_SEC:
        return hit[1]
    try:
        data = await asyncio.wait_for(asyncio.to_thread(build), budget)
    except Exception as exc:
        logger.warning(f"Карточка скина не собрана ({key[1]}/{key[2]}/{key[-1]}): {type(exc).__name__}: {exc}")
        return None
    with _lock:
        _cache[key] = (time.monotonic(), data)
        while len(_cache) > MAX_CACHE:
            _cache.pop(next(iter(_cache)), None)
    return data


async def card_media(png: bytes, look: ChatLook, name: str, username: str | None) -> Media | None:
    """SSS — видео (если есть кодировщик и свободен), иначе картинка; None — не собралось, шлётся обычный график."""
    key = (hashlib.blake2b(png, digest_size=12).digest(), look.skin_id, look.tier, name, username)
    if look.tier == "SSS" and skin_motion.available() and not _motion_busy.locked():
        async with _motion_busy:
            mp4 = await _built((*key, "mp4"), lambda: motion(png, look, name, username), MOTION_BUDGET_SEC)
        if mp4:
            return "animation", mp4, "card.mp4"
    jpeg = await _built((*key, "jpg"), lambda: compose(png, look, name, username), COMPOSE_BUDGET_SEC)
    return ("photo", jpeg, "card.jpg") if jpeg else None


async def graph_media(db, user_id: int, chat_id: int | None, look: ChatLook | None, name: str, username: str | None) -> Media | None:
    """График активности для сообщения: в стиле скина, если он надет. chat_id=None — по всем чатам."""
    if look:
        png = await activity_graph.get_graph(db, user_id, chat_id, theme=theme_for(look))
    else:   # без скина — тот же вызов, что был до скинов
        png = await (activity_graph.get_graph(db, user_id, chat_id) if chat_id is not None else activity_graph.get_graph(db, user_id))
    if not png:
        return None
    styled = await card_media(png, look, name, username) if look else None
    return styled or ("photo", png, "activity.png")


async def answer(message, media: Media, caption: str | None = None) -> None:
    """Отправить картинку или видео; caption=None — без подписи."""
    from aiogram.types import BufferedInputFile
    kind, data, filename = media
    extra = {"caption": caption, "parse_mode": "HTML"} if caption is not None else {}
    file = BufferedInputFile(data, filename=filename)
    if kind == "animation":
        await message.answer_animation(file, **extra)
    else:
        await message.answer_photo(file, **extra)
