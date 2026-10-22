"""Картинки первого знакомства с ботом в личке: приветствие по имени, «подключить за 3 шага» и «что есть на сайте».

Фон — ночной город из Мафии, шрифт Onest, как у обложек патч-ноутов. Всё рисуется здесь же (без сети),
статичные картинки один раз, приветствие — под имя игрока (кэш по имени).
"""
from __future__ import annotations

import io
import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

_ROOT = Path(__file__).resolve().parents[1]
_FONTS = _ROOT / "bot" / "chat" / "assets" / "fonts"
_ART = _ROOT / "FastAPI" / "static" / "mafia-art"
W, H = 1280, 720
INK, MUTED, ACCENT = (244, 241, 255), (176, 168, 204), (176, 150, 255)
GOLD, GREEN, PANEL = (255, 204, 128), (120, 220, 160), (22, 18, 38)


def _font(weight: int, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_FONTS / f"Onest-{weight}.ttf"), size)


@lru_cache(maxsize=1)
def _city() -> Image.Image:
    with Image.open(_ART / "city.jpg") as src:
        return ImageOps.fit(src.convert("RGB"), (W, H), Image.LANCZOS, centering=(0.6, 0.5))


@lru_cache(maxsize=4)
def _shaded(shade_left: int, shade_right: int) -> Image.Image:
    across = Image.new("L", (W, 1))
    across.putdata([int(shade_left + (shade_right - shade_left) * min(1.0, x / (W - 1) * 1.4)) for x in range(W)])
    down = Image.new("L", (1, H))
    down.putdata([int(max(0, y - H * 0.6) / (H * 0.4) * 90) for y in range(H)])
    mask = ImageChops.add(across.resize((W, H)), down.resize((W, H)))
    return Image.composite(Image.new("RGB", (W, H), (8, 7, 16)), _city(), mask)


def _background(shade_left: int = 235, shade_right: int = 90) -> Image.Image:
    """Ночной город, затемнённый слева (там текст) и снизу."""
    return _shaded(shade_left, shade_right).copy()


def _veil(img: Image.Image, alpha: int) -> Image.Image:
    return Image.blend(img, Image.new("RGB", img.size, (8, 7, 16)), alpha / 255)


def _panel(img: Image.Image, box, radius: int = 28, fill=PANEL, alpha: int = 215, outline=(90, 72, 160)) -> None:
    """Полупрозрачная карточка с размытым фоном под ней."""
    x0, y0, x1, y1 = box
    region = img.crop(box).filter(ImageFilter.GaussianBlur(14))
    tint = Image.new("RGB", region.size, fill)
    region = Image.blend(region, tint, alpha / 255)
    m = Image.new("L", region.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, x1 - x0 - 1, y1 - y0 - 1), radius=radius, fill=255)
    img.paste(region, (x0, y0), m)
    ImageDraw.Draw(img).rounded_rectangle(box, radius=radius, outline=outline, width=2)


# ── Иконки: рисуем крупно и уменьшаем, так края гладкие ────────────────────

def _icon(img: Image.Image, kind: str, cx: int, cy: int, size: int, color=INK) -> None:
    k = 4
    s = size * k
    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    c = color + (255,)
    u = s / 100   # единица: 1/100 стороны

    def r(x0, y0, x1, y1):
        return (x0 * u, y0 * u, x1 * u, y1 * u)

    if kind == "shield":
        d.polygon([(50 * u, 6 * u), (88 * u, 20 * u), (84 * u, 58 * u), (50 * u, 94 * u), (16 * u, 58 * u), (12 * u, 20 * u)], fill=c)
        d.line([(34 * u, 50 * u), (46 * u, 63 * u), (68 * u, 38 * u)], fill=(20, 16, 34, 255), width=int(9 * u), joint="curve")
    elif kind == "trophy":
        d.pieslice(r(20, -10, 80, 64), 0, 180, fill=c)
        d.rectangle(r(20, 8, 80, 27), fill=c)
        d.arc(r(4, 12, 34, 46), 90, 270, fill=c, width=int(7 * u))
        d.arc(r(66, 12, 96, 46), 270, 90, fill=c, width=int(7 * u))
        d.rectangle(r(44, 60, 56, 78), fill=c)
        d.rounded_rectangle(r(28, 78, 72, 92), radius=3 * u, fill=c)
    elif kind == "game":
        d.rounded_rectangle(r(6, 26, 94, 78), radius=24 * u, fill=c)
        dark = (20, 16, 34, 255)
        d.rectangle(r(24, 46, 42, 54), fill=dark)
        d.rectangle(r(29, 41, 37, 59), fill=dark)
        d.ellipse(r(62, 38, 72, 48), fill=dark)
        d.ellipse(r(72, 52, 82, 62), fill=dark)
    elif kind == "user":
        d.ellipse(r(32, 8, 68, 44), fill=c)
        d.pieslice(r(14, 50, 86, 122), 180, 360, fill=c)
    elif kind == "paw":
        d.ellipse(r(28, 46, 72, 88), fill=c)
        for x0, y0 in ((12, 30), (30, 12), (52, 12), (70, 30)):
            d.ellipse(r(x0, y0, x0 + 18, y0 + 22), fill=c)
    elif kind == "scroll":
        d.rounded_rectangle(r(16, 8, 84, 92), radius=10 * u, fill=c)
        dark = (20, 16, 34, 255)
        for y in (30, 50, 70):
            d.ellipse(r(26, y - 5, 36, y + 5), fill=dark)
            d.rounded_rectangle(r(42, y - 4, 74, y + 4), radius=3 * u, fill=dark)
    elif kind == "crown":
        d.polygon([(10 * u, 30 * u), (32 * u, 52 * u), (50 * u, 16 * u), (68 * u, 52 * u), (90 * u, 30 * u),
                   (82 * u, 78 * u), (18 * u, 78 * u)], fill=c)
        d.rounded_rectangle(r(18, 82, 82, 92), radius=3 * u, fill=c)
    elif kind == "moon":
        d.ellipse(r(10, 10, 90, 90), fill=c)
        d.ellipse(r(32, 0, 106, 74), fill=(0, 0, 0, 0))
    elif kind == "plus":
        d.rounded_rectangle(r(42, 12, 58, 88), radius=6 * u, fill=c)
        d.rounded_rectangle(r(12, 42, 88, 58), radius=6 * u, fill=c)
    elif kind == "arrow":
        d.rounded_rectangle(r(8, 42, 64, 58), radius=6 * u, fill=c)
        d.polygon([(56 * u, 22 * u), (94 * u, 50 * u), (56 * u, 78 * u)], fill=c)
    small = layer.resize((size, size), Image.LANCZOS)
    img.paste(small, (cx - size // 2, cy - size // 2), small)


def _badge(img: Image.Image, kind: str, cx: int, cy: int, radius: int = 34, ring=ACCENT) -> None:
    d = ImageDraw.Draw(img)
    d.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(44, 32, 92), outline=ring, width=2)
    _icon(img, kind, cx, cy, int(radius * 1.15), INK)


def _toggle(d: ImageDraw.ImageDraw, x: int, y: int, on: bool = True) -> None:
    d.rounded_rectangle((x, y, x + 58, y + 32), radius=16, fill=GREEN if on else (70, 64, 90))
    cx = x + 42 if on else x + 16
    d.ellipse((cx - 12, y + 4, cx + 12, y + 28), fill=(250, 250, 255))


def _jpeg(img: Image.Image) -> bytes:
    out = io.BytesIO()   # фото Telegram всё равно пережимает в JPEG; PNG тут только медленнее и тяжелее
    img.save(out, "JPEG", quality=90, optimize=True)
    return out.getvalue()


# ── Имя на картинке ─────────────────────────────────────────────────────────

_NAME_JUNK = re.compile(r"[^0-9A-Za-zА-Яа-яЁё \-'.]")


def clean_name(first_name: str | None) -> str:
    """Только то, что точно есть в шрифте: эмодзи и экзотические буквы вместо «квадратиков» просто убираем."""
    name = re.sub(r"\s+", " ", _NAME_JUNK.sub("", first_name or "")).strip(" -'.")
    if sum(ch.isalpha() for ch in name) < 2:
        return ""
    return name[:16].rstrip(" -'.") + ("…" if len(name) > 16 else "")


# ── Картинки ────────────────────────────────────────────────────────────────

def welcome(name: str = "") -> bytes:   # без кэша: после первой отправки Telegram отдаёт её по file_id
    """Приветствие 1280×720: «Привет, Имя!», кто такой бот и три главных умения."""
    img = _background()
    d = ImageDraw.Draw(img)
    _icon(img, "moon", 104, 104, 40, ACCENT)
    d.text((136, 86), "ПРЕДВЕСТНИК", font=_font(700, 30), fill=ACCENT)
    title = f"Привет, {name}!" if name else "Добро пожаловать!"
    big = _font(700, 78)
    while d.textlength(title, font=big) > 760 and big.size > 54:
        big = _font(700, big.size - 4)
    d.text((86, 160), title, font=big, fill=INK)
    d.text((88, 266), "Я бот для чатов и игр в Telegram.", font=_font(500, 36), fill=INK)
    d.text((88, 314), "Вот что я умею:", font=_font(400, 30), fill=MUTED)
    rows = (("shield", "Порядок в чате", "муты, варны, баны и ранги модераторов"),
            ("trophy", "Профили и топ", "кто самый активный, награды и серии"),
            ("game", "Игры", "Мафия, Ритм, Сапёр и питомцы"))
    y = 384
    for kind, head, sub in rows:
        _badge(img, kind, 124, y + 26)
        d.text((180, y - 2), head, font=_font(700, 32), fill=INK)
        d.text((180, y + 38), sub, font=_font(400, 26), fill=MUTED)
        y += 88
    pill = _font(700, 28)
    label = "Добавьте меня в свой чат — это пара минут"
    pw = int(d.textlength(label, font=pill))
    x0, y0 = 88, H - 80
    _panel(img, (x0, y0, x0 + pw + 100, y0 + 56), radius=28, fill=(64, 44, 140), alpha=235, outline=ACCENT)
    d.text((x0 + 28, y0 + 10), label, font=pill, fill=INK)
    _icon(img, "arrow", x0 + pw + 62, y0 + 28, 34, INK)
    return _jpeg(img)


@lru_cache(maxsize=1)
def connect_steps() -> bytes:
    """Подключение за 3 шага: как это выглядит в Telegram, на макетах."""
    img = _veil(_background(200, 150), 60)
    d = ImageDraw.Draw(img)
    d.text((64, 46), "Подключить бота за 3 шага", font=_font(700, 54), fill=INK)
    d.text((66, 116), "Пара минут. Я подскажу каждый шаг и сам проверю права.", font=_font(400, 28), fill=MUTED)
    cards = [(48 + i * 400, 186, 48 + i * 400 + 376, 640) for i in range(3)]
    heads = ("Добавьте меня в чат", "Выдайте два права", "Напишите в чате")
    for i, box in enumerate(cards):
        _panel(img, box)
        x0, y0, x1, _ = box
        d.ellipse((x0 + 24, y0 + 24, x0 + 80, y0 + 80), fill=ACCENT)
        num = str(i + 1)
        f = _font(700, 34)
        d.text((x0 + 52 - d.textlength(num, font=f) / 2, y0 + 30), num, font=f, fill=(20, 16, 34))
        d.text((x0 + 96, y0 + 34), heads[i], font=_font(700, 26), fill=INK)
    # 1: кнопка и выбор чата
    x0, y0 = cards[0][0] + 28, cards[0][1] + 120
    d.rounded_rectangle((x0, y0, x0 + 320, y0 + 64), radius=16, fill=(64, 44, 140), outline=ACCENT, width=2)
    _icon(img, "plus", x0 + 36, y0 + 32, 28, INK)
    d.text((x0 + 62, y0 + 16), "Добавить бота в чат", font=_font(700, 24), fill=INK)
    for j, (title, on) in enumerate((("Моя группа", True), ("Друзья", False), ("Работа", False))):
        yy = y0 + 96 + j * 70
        fill = (52, 40, 100) if on else (34, 28, 56)
        d.rounded_rectangle((x0, yy, x0 + 320, yy + 58), radius=14, fill=fill, outline=ACCENT if on else None, width=2)
        d.ellipse((x0 + 14, yy + 11, x0 + 50, yy + 47), fill=(96, 80, 170) if on else (70, 60, 110))
        d.text((x0 + 64, yy + 14), title, font=_font(500, 24), fill=INK if on else MUTED)
        if on:
            _icon(img, "arrow", x0 + 292, yy + 29, 26, ACCENT)
    # 2: права администратора
    x0, y0 = cards[1][0] + 28, cards[1][1] + 120
    d.text((x0, y0), "Права администратора", font=_font(500, 22), fill=MUTED)
    rights = (("Удаление сообщений", True), ("Блокировка", True), ("Остальное", False))
    for j, (title, on) in enumerate(rights):
        yy = y0 + 44 + j * 74
        d.rounded_rectangle((x0, yy, x0 + 320, yy + 60), radius=14, fill=(34, 28, 56))
        d.text((x0 + 18, yy + 18), title, font=_font(500, 20), fill=INK if on else MUTED)
        _toggle(d, x0 + 246, yy + 14, on)
    d.text((x0, y0 + 278), "Telegram сам отметит нужное", font=_font(400, 21), fill=GREEN)
    # 3: «бот помощь» и ответ бота
    x0, y0 = cards[2][0] + 28, cards[2][1] + 120
    f = _font(500, 26)
    bw = int(d.textlength("бот помощь", font=f)) + 40
    d.rounded_rectangle((x0 + 320 - bw, y0 + 8, x0 + 320, y0 + 64), radius=20, fill=(96, 72, 200))
    d.text((x0 + 340 - bw, y0 + 20), "бот помощь", font=f, fill=INK)
    d.rounded_rectangle((x0, y0 + 88, x0 + 290, y0 + 236), radius=20, fill=(40, 34, 66))
    d.text((x0 + 20, y0 + 104), "Предвестник", font=_font(700, 22), fill=ACCENT)
    for j, line in enumerate(("Помощь: все команды", "Модерация · Игры · Топ")):
        d.text((x0 + 20, y0 + 142 + j * 38), line, font=_font(400, 22), fill=INK)
    d.ellipse((x0 + 4, y0 + 274, x0 + 40, y0 + 310), fill=GREEN)
    d.line([(x0 + 13, y0 + 292), (x0 + 20, y0 + 300), (x0 + 32, y0 + 284)], fill=(20, 16, 34), width=4)
    d.text((x0 + 52, y0 + 278), "Готово, бот работает", font=_font(700, 22), fill=GREEN)
    d.text((64, 664), "Команды в чате начинаются со слова «бот»", font=_font(500, 26), fill=MUTED)
    return _jpeg(img)


@lru_cache(maxsize=1)
def site_tour() -> bytes:
    """Что есть на сайте Предвестника: шесть плиток, у Мафии — настоящий портрет роли."""
    img = _veil(_background(210, 160), 70)
    d = ImageDraw.Draw(img)
    _icon(img, "moon", 86, 78, 40, ACCENT)
    d.text((118, 52), "Сайт Предвестника", font=_font(700, 54), fill=INK)
    d.text((66, 122), "Открывается прямо в Telegram. Входить никуда не нужно.", font=_font(400, 28), fill=MUTED)
    tiles = (("user", "Профиль", ("образы, рамки,", "награды")),
             ("game", "Игры", ("Ритм и Сапёр",)),
             ("mafia", "Мафия", ("роли и правила", "игры в чате")),
             ("paw", "Питомцы", ("экипировка", "и Вылазки")),
             ("scroll", "Задания", ("награды", "каждый день")),
             ("crown", "Топ", ("лучшие игроки", "и чаты")))
    tw, th, gap = 376, 214, 24
    for i, (kind, head, sub) in enumerate(tiles):
        col, row = i % 3, i // 3
        x0, y0 = 48 + col * (tw + gap), 190 + row * (th + gap)
        box = (x0, y0, x0 + tw, y0 + th)
        _panel(img, box, radius=26)
        if kind == "mafia":
            with Image.open(_ART / "mafia.jpg") as src:
                face = ImageOps.fit(src.convert("RGB"), (120, 120), Image.LANCZOS, centering=(0.5, 0.3))
            m = Image.new("L", (120, 120), 0)
            ImageDraw.Draw(m).ellipse((0, 0, 119, 119), fill=255)
            img.paste(face, (x0 + 28, y0 + 26), m)
            d.ellipse((x0 + 28, y0 + 26, x0 + 148, y0 + 146), outline=GOLD, width=3)
        else:
            _badge(img, kind, x0 + 88, y0 + 86, radius=58)
        d.text((x0 + 172, y0 + 52), head, font=_font(700, 34), fill=INK)
        for j, line in enumerate(sub):
            d.text((x0 + 172, y0 + 102 + j * 32), line, font=_font(400, 24), fill=MUTED)
    d.text((64, 668), "Кнопка «Открыть сайт» — под сообщением", font=_font(500, 26), fill=MUTED)
    return _jpeg(img)
