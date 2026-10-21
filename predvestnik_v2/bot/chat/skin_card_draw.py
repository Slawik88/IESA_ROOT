"""Рисование карточки «бот я» в стиле скина (Pillow): фон, рамка, частицы, шапка; график кладётся поверх.

Всё выводится из каталога: kinds.bg — фон, kinds.frame — рамка, kinds.pt — частицы, pal и tokens — цвета.
Тир добавляет эффекты: частицы с B, вторую линию рамки с S, свечение рамки с SS, звёзды по углам на SSS.
Декор (без имени игрока) один на пару «скин + тир» и кэшируется вызывающим кодом (bot/chat/skin_card.py)."""
from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageFilter

from core.skins_v3 import TIERS
from core.skins_v3_catalog import SKINS

GRAPH_W, GRAPH_H = 1120, 700        # размер картинки activity_graph.render
M, HEAD = 40, 170                   # поле вокруг графика и высота шапки
W, H = GRAPH_W + 2 * M, HEAD + GRAPH_H + M
PARTICLES = (0, 0, 10, 18, 28, 38, 52)      # по тирам D…SSS
LOW = 6                             # фон рисуется в 1/LOW размера и растягивается: размытие дёшево


def rgb(value: str) -> tuple[int, int, int]:
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


def mix(a, b, k: float) -> tuple[int, int, int]:
    a, b = (rgb(a) if isinstance(a, str) else a), (rgb(b) if isinstance(b, str) else b)
    return tuple(round(x + (y - x) * k) for x, y in zip(a, b))


def _glows(kind: str, pal, t: int) -> list[tuple[tuple[float, float, float, float], tuple[int, int, int], int]]:
    """Пятна света (доли ширины и высоты): wash — два, mesh и прочие — три."""
    p0, p1, p2 = pal
    base = 50 + 7 * t
    spots = [((.45, -.5, 1.4, .55), rgb(p1), base), ((-.3, .6, .45, 1.4), rgb(p2), base // 2)]
    if kind != "wash":
        spots.append(((-.2, -.3, .35, .4), rgb(p0), base // 2))
    if kind == "aurora":
        spots.append(((-.1, .05, 1.1, .3), rgb(p0), base // 2))
    return spots


def _background(skin: dict, t: int) -> Image.Image:
    bg = rgb(skin["tokens"]["--v3-bg"])
    small = Image.new("RGBA", (W // LOW, H // LOW), bg + (255,))
    layer = Image.new("RGBA", small.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    sw, sh = small.size
    for (x0, y0, x1, y1), color, alpha in _glows(skin["kinds"]["bg"], skin["pal"], t):
        d.ellipse([x0 * sw, y0 * sh, x1 * sw, y1 * sh], fill=color + (alpha,))
    small.alpha_composite(layer.filter(ImageFilter.GaussianBlur(sw / 10)))
    return small.resize((W, H), Image.BILINEAR)


def _texture(img: Image.Image, skin: dict, t: int, rnd: random.Random) -> None:
    """Рисунок фона поверх пятен: звёзды, сетка, лучи, вихрь, крапинки."""
    kind, (p0, _p1, p2) = skin["kinds"]["bg"], skin["pal"]
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    a = 14 + 3 * t
    if kind in ("stars", "bow"):
        for _ in range(70):
            x, y, r = rnd.uniform(0, W), rnd.uniform(0, H), rnd.choice((1, 1, 2, 2, 3))
            d.ellipse([x - r, y - r, x + r, y + r], fill=rgb(p2) + (a * 4,))
    elif kind == "grid":
        for x in range(0, W, 40):
            d.line([(x, 0), (x, H)], fill=rgb(p0) + (a,))
        for y in range(0, H, 40):
            d.line([(0, y), (W, y)], fill=rgb(p0) + (a,))
    elif kind == "rays":
        for i in range(7):
            ang = math.pi * (.52 + i * .07)
            d.polygon([(W, 0), (W + math.cos(ang) * 2000, math.sin(ang) * 2000),
                       (W + math.cos(ang + .025) * 2000, math.sin(ang + .025) * 2000)], fill=rgb(p0) + (a,))
    elif kind == "vortex":
        for i in range(1, 9):
            r = i * 90
            d.arc([W * .8 - r, -r * .6, W * .8 + r, r * .6], 20, 200, fill=rgb(p0) + (a + 6,), width=2)
    elif kind == "grunge":
        for _ in range(500):
            x, y = rnd.uniform(0, W), rnd.uniform(0, H)
            d.point((x, y), fill=rgb(p2) + (a * 3,))
    img.alpha_composite(layer)


def _particle(d: ImageDraw.ImageDraw, kind: str, x: float, y: float, r: float, color: tuple, rnd: random.Random) -> None:
    if kind in ("leaf", "petal"):
        ang = rnd.uniform(0, math.pi)
        d.polygon([(x + math.cos(ang + k * math.pi / 2) * r * (1 if k % 2 == 0 else .4),
                    y + math.sin(ang + k * math.pi / 2) * r * (1 if k % 2 == 0 else .4)) for k in range(4)], fill=color)
    elif kind == "snow":
        for k in range(3):
            ang = k * math.pi / 3
            d.line([(x - math.cos(ang) * r, y - math.sin(ang) * r), (x + math.cos(ang) * r, y + math.sin(ang) * r)],
                   fill=color, width=max(2, int(r / 5)))
    elif kind in ("spark", "glint", "star"):
        q = r * .24
        d.polygon([(x, y - r), (x + q, y - q), (x + r, y), (x + q, y + q), (x, y + r), (x - q, y + q), (x - r, y), (x - q, y - q)], fill=color)
    elif kind == "ring":
        d.ellipse([x - r / 2, y - r / 2, x + r / 2, y + r / 2], outline=color, width=2)
    elif kind == "drop":
        d.ellipse([x - r / 2, y, x + r / 2, y + r], fill=color)
        d.polygon([(x - r / 2.4, y + r / 3), (x, y - r / 2), (x + r / 2.4, y + r / 3)], fill=color)
    else:   # dot, ember, sand
        s = r / (3 if kind == "sand" else 2)
        d.ellipse([x - s, y - s, x + s, y + s], fill=color)


def _free(x: float, y: float) -> bool:
    """Частицы только по краям и в шапке, не по графику и не по имени и значку уровня."""
    if M - 6 < x < W - M + 6 and HEAD - 10 < y < H - M + 6:
        return False
    return not (y < HEAD - 10 and (x < 640 or x > W - 330))


def particle_field(skin_id: str, tier: str) -> list[tuple[float, float, int, tuple, float]]:
    """Частицы скина на тире: (x, y, радиус, цвет, фаза). Одинаковы для одного скина и тира; рисует draw_particles."""
    skin, t = SKINS[skin_id], TIERS.index(tier)
    rnd = random.Random(f"{skin_id}:{tier}:pt")
    p0, _p1, p2 = skin["pal"]
    out: list[tuple[float, float, int, tuple, float]] = []
    tries = 0
    while len(out) < PARTICLES[t] and tries < PARTICLES[t] * 30:
        tries += 1
        x, y = rnd.uniform(4, W - 4), rnd.uniform(4, H - 4)
        if _free(x, y):
            out.append((x, y, rnd.randint(6, 14), rgb(rnd.choice((p0, p2))) + (rnd.randint(110, 220),), rnd.uniform(0, 2 * math.pi)))
    return out


def draw_particles(img: Image.Image, skin_id: str, field: list, phase: float | None = None) -> None:
    """phase=None — неподвижная картинка; иначе частица мерцает и чуть плывёт по кругу (кадр анимации)."""
    d, kind = ImageDraw.Draw(img), SKINS[skin_id]["kinds"]["pt"]
    for i, (x, y, r, color, own) in enumerate(field):
        rnd = random.Random(i)
        if phase is not None:
            x, y = x + 6 * math.cos(phase + own), y + 6 * math.sin(phase + own)
            color = color[:3] + (int(color[3] * (0.55 + 0.45 * math.sin(phase * 2 + own))),)
        _particle(d, kind, x, y, r, color, rnd)


def _gradient(pal) -> Image.Image:
    ramp = Image.linear_gradient("L").rotate(90).resize((W, H))
    return Image.composite(Image.new("RGBA", (W, H), rgb(pal[1]) + (255,)), Image.new("RGBA", (W, H), rgb(pal[0]) + (255,)), ramp)


def _frame_mask(kind: str, t: int) -> Image.Image:
    mask = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(mask)
    width = 3 if t < 4 else 5
    box = [10, 10, W - 10, H - 10]
    if kind == "dash":
        for x in range(46, W - 46, 36):
            d.line([(x, 10), (x + 20, 10)], fill=255, width=width)
            d.line([(x, H - 10), (x + 20, H - 10)], fill=255, width=width)
        for y in range(46, H - 46, 36):
            d.line([(10, y), (10, y + 20)], fill=255, width=width)
            d.line([(W - 10, y), (W - 10, y + 20)], fill=255, width=width)
        for cx, cy, start in ((46, 46, 180), (W - 46, 46, 270), (W - 46, H - 46, 0), (46, H - 46, 90)):
            d.arc([cx - 36, cy - 36, cx + 36, cy + 36], start, start + 90, fill=255, width=width)
    else:
        d.rounded_rectangle(box, 36, outline=255 if kind != "seg" else 120, width=width if kind != "seg" else 2)
    if kind == "seg":
        for (x, y, sx, sy) in ((10, 10, 1, 1), (W - 10, 10, -1, 1), (10, H - 10, 1, -1), (W - 10, H - 10, -1, -1)):
            d.line([(x, y + sy * 36), (x, y + sy * 120)], fill=255, width=width + 3)
            d.line([(x + sx * 36, y), (x + sx * 120, y)], fill=255, width=width + 3)
    if kind == "double" or t >= 4:
        d.rounded_rectangle([22, 22, W - 22, H - 22], 28, outline=150, width=2)
    if kind == "drip":
        for x in range(70, W - 60, 95):
            depth = 18 + (x * 7) % 34
            d.rounded_rectangle([x - 4, 10, x + 4, 10 + depth], 4, fill=255)
            d.ellipse([x - 7, 4 + depth, x + 7, 18 + depth], fill=255)
    return mask


def _frame(img: Image.Image, skin: dict, t: int) -> None:
    mask = _frame_mask(skin["kinds"]["frame"], t)
    paint = _gradient(skin["pal"])
    if t >= 5:   # свечение рамки с SS
        halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        halo.paste(paint, (0, 0), mask)
        img.alpha_composite(halo.filter(ImageFilter.GaussianBlur(9)))
    img.paste(paint, (0, 0), mask)
    if t == 6:   # SSS: звёзды по углам
        d = ImageDraw.Draw(img)
        color = rgb(skin["pal"][2]) + (255,)
        for x, y in ((10, 10), (W - 10, 10), (10, H - 10), (W - 10, H - 10)):
            _particle(d, "star", x, y, 22, color, random.Random(0))


def decor(skin_id: str, tier: str, *, particles: bool = True) -> Image.Image:
    """Фон, частицы и рамка карточки, без текста и графика. Детерминирован: одинаковый скин — одинаковая картинка.
    particles=False — для анимации: частицы рисуются в каждом кадре своим положением (bot/chat/skin_motion.py)."""
    skin, t = SKINS[skin_id], TIERS.index(tier)
    img = _background(skin, t)
    _texture(img, skin, t, random.Random(f"{skin_id}:{tier}"))
    if particles:
        draw_particles(img, skin_id, particle_field(skin_id, tier))
    _frame(img, skin, t)
    return img
