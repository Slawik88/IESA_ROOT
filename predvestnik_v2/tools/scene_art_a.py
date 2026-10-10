"""Scene art A (skin-scene-a-v3.css): Лесной Странник, Песчаная Тропа, Тихая Гавань, Пруд Лотосов, Порог, Изморозь, Медные Сумерки, Бутон Сакуры."""
from __future__ import annotations

import math
import random

from scene_kit import (art, circ, d_poly, d_ridge, d_smooth, dune_top, ell, forest, gear_d, mirror, n, path, poly, rect, ridge, stroke, svg)


def A(name: str, value: str) -> None:
    art(name, "a", value)


def grad(gid: str, top: str, bottom: str, top_op: float = 1, bottom_op: float = 1) -> str:
    return (f"<defs><linearGradient id='{gid}' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='{top}' stop-opacity='{top_op}'/>"
            f"<stop offset='1' stop-color='{bottom}' stop-opacity='{bottom_op}'/></linearGradient></defs>")


# ── Лесной Странник ──
A("pineL", forest([(22, 200, 52), (62, 150, 44), (104, 118, 38)], 140, 210, "#031109"))
A("pineR", forest([(36, 126, 40), (78, 176, 48), (120, 208, 54)], 140, 210, "#031109"))

# ── Песчаная Тропа: два ряда барханов с подсвеченным гребнем, далёкий хребет и караван ──
def dunes(side: str, seed: int) -> str:
    w, h = 260, 130
    near = dune_top(w, 124, 78, 2.3, seed, fade=lambda t: 1 - .82 * t)
    far = dune_top(w, 120, 52, 2.9, seed + 7, fade=lambda t: .35 + .65 * (1 - t) ** .8)
    if side == "R":
        near, far = mirror(near, w), mirror(far, w)
    body = path(d_ridge(far, w, h), "#4a2a12") + path(d_ridge(near, w, h), "#1f1108")
    body += stroke(d_smooth(near, closed=False), "#f0c987", 1.3, "stroke-opacity='.5'") + stroke(d_smooth(far, closed=False), "#c98a4a", 1, "stroke-opacity='.4'")
    return svg(w, h, body)


A("duneL", dunes("L", 3))
A("duneR", dunes("R", 5))
far = dune_top(400, 70, 40, 3.6, 11)
A("duneFar", svg(400, 80, path(d_ridge(far, 400, 80), "#4b2a12") + stroke(d_smooth(far, closed=False), "#f0c987", 1, "stroke-opacity='.35'"), "xMidYMax slice"))


def camel(x: float, y: float, s: float, rider: bool = True) -> str:
    g = ell(22, 20, 15, 7.5, "#120a05") + ell(21, 11, 5, 5.5, "#120a05")
    g += poly([(30, 17), (35, 8), (39, 5), (41, 9), (37, 12), (37, 22)], "#120a05") + poly([(38, 5), (47, 3), (53, 7), (52, 10), (45, 10), (40, 11)], "#120a05")
    for lx in (10, 15, 28, 33):
        g += poly([(lx, 24), (lx + 3, 24), (lx + 2.2, 44), (lx - .2, 44)], "#120a05")
    g += stroke("M7 17Q3 22 4 30", "#120a05", 1.6)
    if rider:
        g += poly([(16, 11), (21, 3), (26, 11)], "#120a05") + circ(21, 1.6, 2.1, "#120a05")
    return f"<g transform='translate({n(x)} {n(y)}) scale({s})'>{g}</g>"


A("camels", svg(190, 48, camel(0, 2, .95) + camel(60, 1, 1) + camel(122, 2, .9, False) + stroke("M50 22Q57 24 61 22", "#120a05", .9) + stroke("M112 22Q118 25 124 23", "#120a05", .9)))

# ── Тихая Гавань: волна для бегущей полосы, причал, лодка, дальний парусник и чайка ──
def tide(name: str, width: int, amp: float, top: str, rim: str, depth: int = 40) -> None:
    pts = []
    for i in range(0, width + 1, width // 12):
        x = i / width * math.tau
        pts.append((i, depth * .42 - amp * (math.sin(x) * .7 + math.sin(2 * x + 1.1) * .45)))
    crest = d_smooth(pts, closed=False)
    A(name, svg(width, depth, grad("g", top, top, .55, 0) + path(crest + f"V{depth}H0z", "url(#g)") + stroke(crest, rim, 1.2, "stroke-opacity='.6'"), "none"))


tide("wave", 120, 5, "#2a6a96", "#9ccdee")
tide("wave2", 180, 4, "#4a8cb8", "#e8f3fb", 36)
A("pier", svg(190, 120,
    rect(0, 54, 190, 6, "#050e18") + rect(0, 60, 190, 3, "#0b2236") +
    "".join(poly([(x, 63), (x + 7, 63), (x + 6, 120), (x + 1, 120)], "#050e18") for x in (14, 52, 90, 128)) +
    stroke("M17 70L55 112M55 70L93 112M93 70L131 112", "#0b2236", 1.6) +
    rect(166, 12, 5, 44, "#050e18") + rect(160, 8, 17, 7, "#050e18") + poly([(160, 8), (168.5, 1), (177, 8)], "#050e18") + rect(158, 54, 22, 3, "#0b2236") +
    stroke("M16 56Q34 70 52 56", "#0b2236", 1.4) + stroke("M54 56Q72 70 90 56", "#0b2236", 1.4), "xMinYMax meet"))
A("boat", svg(104, 118,
    poly([(4, 94), (100, 94), (86, 110), (20, 110)], "#050e18") + rect(50, 10, 3.2, 84, "#050e18") +
    poly([(55, 12), (55, 88), (94, 88)], "#0a2236") + poly([(48, 22), (48, 88), (12, 88)], "#0b2a42") + stroke("M54 10L54 94", "#8fc3e6", .8, "stroke-opacity='.4'") +
    stroke("M52 10L98 90", "#050e18", .9) + rect(40, 88, 28, 6, "#050e18")))
A("ship", svg(190, 140,
    poly([(6, 104), (184, 104), (168, 128), (26, 128)], "#07182a") + poly([(168, 104), (184, 94), (190, 104)], "#07182a") +
    "".join(rect(x, 14, 2.6, 92, "#07182a") for x in (46, 94, 140)) +
    "".join(poly([(x - w, y), (x + w, y), (x + w - 2, y + hh), (x - w + 2, y + hh)], "#0c2d48") for x, w, y, hh in ((47, 22, 30, 26), (47, 26, 60, 30), (95, 26, 18, 30), (95, 30, 52, 34), (141, 22, 28, 26), (141, 26, 58, 30))) +
    stroke("M2 104L47 18M2 104L141 28", "#07182a", .9) + rect(150, 92, 22, 12, "#07182a") + circ(160, 98, 1.5, "#ffd98a")))
def quay() -> str:
    d = "#050e18"
    body = rect(60, 92, 56, 58, d) + poly([(56, 94), (88, 70), (120, 94)], d) + rect(124, 104, 40, 46, d) + poly([(120, 106), (144, 90), (168, 106)], d) + rect(170, 112, 30, 38, d)
    body += rect(22, 30, 5, 120, d) + rect(22, 30, 60, 5, d) + stroke("M24 32L70 12M82 33L70 12", d, 1.6) + stroke("M78 35V74", "#0b2236", 1.2) + rect(74, 74, 8, 8, d)
    body += "".join(rect(x, y, 5, 6, "#ffd98a", "fill-opacity='.95'") for x, y in ((68, 106), (84, 106), (100, 106), (68, 124), (100, 124), (134, 118), (150, 118), (178, 124)))
    body += rect(2, 118, 3, 32, d) + stroke("M3 118L3 50M3 60L-8 118M3 60L14 118", d, 1.2) + rect(0, 148, 200, 2, "#0b2236")
    return svg(200, 150, body, "xMaxYMax meet")


A("quay", quay())
A("gull", svg(46, 22, path("M2 13Q12 2 23 12Q34 2 44 13Q34 9 23 17Q12 9 2 13z", "#000"), "xMidYMid meet"))

# ── Пруд Лотосов: камыш, листья на воде и карп ──
def reeds(seed: int) -> str:
    r = random.Random(seed)
    w, h = 120, 210
    body = ""
    for x0, hh, lean in ((18, 200, -.12), (34, 160, .1), (50, 190, -.05), (66, 130, .16), (82, 170, .06), (98, 110, -.18), (110, 150, .12)):
        x1 = x0 + lean * hh
        body += stroke(f"M{x0} {h}Q{n(x0 + lean * hh * .2)} {n(h - hh * .6)} {n(x1)} {n(h - hh)}", "#02130f", 3.2)
        if hh > 120 and r.random() > .25:
            ang = math.degrees(math.atan2(lean, 1))
            body += ell(x1, h - hh - 12, 4.6, 14, "#02130f", f"transform='rotate({n(ang)} {n(x1)} {n(h - hh)})'")
    for x0, lean in ((26, -.5), (58, .5), (90, -.4)):                      # длинные листья осоки
        body += stroke(f"M{x0} {h}Q{n(x0 + lean * 60)} {n(h - 90)} {n(x0 + lean * 110)} {n(h - 120)}", "#02130f", 2.6)
    return svg(w, h, body, "xMidYMax meet")


A("reeds", reeds(4))
def pads() -> str:
    body = ""
    for cx, cy, rx, ry, a in ((26, 40, 24, 8, -.4), (74, 46, 18, 6, .5), (122, 38, 28, 9, 3.4), (172, 46, 20, 6.5, 1.2), (214, 40, 24, 8, 2.2)):
        x1, y1, x2, y2 = cx + rx * math.cos(a), cy + ry * math.sin(a), cx + rx * math.cos(a + .55), cy + ry * math.sin(a + .55)
        body += path(f"M{n(cx)} {n(cy)}L{n(x1)} {n(y1)}A{n(rx)} {n(ry)} 0 1 1 {n(x2)} {n(y2)}z", "#03211a")
        body += ell(cx - rx * .15, cy - ry * .2, rx * .62, ry * .5, "#0a4a3a", "fill-opacity='.55'") + stroke(f"M{n(cx - rx * .9)} {n(cy - ry * .1)}Q{n(cx)} {n(cy - ry * 1.15)} {n(cx + rx * .8)} {n(cy - ry * .3)}", "#2fb89a", .9, "stroke-opacity='.45'")
    body += stroke("M150 46Q146 30 150 14", "#03211a", 1.8) + path("M150 4Q144 12 146 20Q150 24 154 20Q156 12 150 4z", "#ffc2d6") + path("M150 8Q147 14 148 19Q150 21 152 19Q153 14 150 8z", "#ffe9f0")
    return svg(240, 60, body, "xMidYMax meet")


A("pads", pads())
def koi() -> str:
    body = poly([(30, 13), (40, 2), (47, 14)], "#ffb48a", "fill-opacity='.9'") + poly([(30, 31), (40, 42), (47, 30)], "#ffb48a", "fill-opacity='.9'")
    body += path("M96 22L118 4Q123 14 120 22Q123 30 118 40z", "#ff9a6a", "fill-opacity='.9'")
    body += path(d_smooth([(3, 22), (9, 13), (30, 11), (56, 14), (80, 18), (98, 21), (108, 22), (98, 23), (80, 26), (56, 30), (30, 33), (9, 31)]), "#fff4ea")
    body += ell(30, 22, 11, 7, "#ff7a3c") + ell(62, 22, 9, 5, "#ff7a3c") + ell(11, 22, 6, 6, "#e63b2e") + circ(8, 17, 1.2, "#2b1410") + circ(8, 27, 1.2, "#2b1410")
    return svg(124, 44, body, "xMidYMid meet")


A("koi", koi())

# ── Порог: менгиры с рунами и тень в капюшоне ──
def stones() -> str:
    body = ""
    for pts in (((20, 210), (26, 74), (40, 44), (55, 66), (59, 210)), ((64, 210), (71, 116), (84, 96), (98, 112), (102, 210)), ((106, 210), (113, 64), (128, 36), (143, 68), (147, 210))):
        body += poly(pts, "#08051a") + stroke(d_smooth(list(pts[1:4]), closed=False), "#5b3fd6", 1.2, "stroke-opacity='.7'")
    body += stroke("M40 78V150M33 96L47 96M33 118L47 118M40 150L34 164M40 150L46 164", "#b48cff", 1.5, "stroke-opacity='.85'")
    body += stroke("M128 74V150M121 92L135 92M121 112L135 112M121 132L135 132", "#7aa8ff", 1.5, "stroke-opacity='.85'")
    body += stroke("M84 130V176M78 146L90 146", "#b48cff", 1.4, "stroke-opacity='.7'")
    return svg(152, 214, body, "xMidYMax meet")


A("stones", stones())
def wisp() -> str:
    body = path("M35 4Q50 6 52 28Q56 50 62 90Q66 118 72 134L0 134Q6 118 10 90Q16 50 18 28Q20 6 35 4z", "#04020c")
    body += stroke("M18 30Q16 60 8 120M52 30Q56 60 64 120", "#5b3fd6", 1, "stroke-opacity='.55'") + ell(29, 25, 2.6, 1.5, "#e8dcff") + ell(41, 25, 2.6, 1.5, "#e8dcff")
    return svg(72, 136, body, "xMidYMax meet")


A("wisp", wisp())

# ── Изморозь: кристаллы льда по углам и сосульки сверху ──
def crystals() -> str:
    body = ""
    # x of the base, height, width, tilt in px of the apex: shards lean away from the middle, a few small ones fill the gaps
    for cx, hh, ww, tilt in ((34, 118, 26, -10), (68, 150, 30, 6), (102, 96, 24, 14), (126, 58, 16, 8), (12, 66, 16, -8), (84, 52, 14, -6)):
        base, top = 170, 170 - hh
        apex = cx + tilt
        body += poly([(apex, top), (cx - ww / 2, base), (cx + ww * .1, base)], "#d7f1ff", "fill-opacity='.95'")
        body += poly([(apex, top), (cx + ww * .1, base), (cx + ww / 2, base), (cx + ww * .34, top + hh * .34)], "#7cc3ee", "fill-opacity='.95'")
        body += poly([(apex, top), (cx + ww * .34, top + hh * .34), (cx + ww * .1, base)], "#a9dcf8", "fill-opacity='.9'")
        body += stroke(f"M{n(apex)} {n(top)}L{n(cx - ww / 2)} {n(base)}", "#ffffff", 1, "stroke-opacity='.7'")
    return svg(140, 170, body, "xMidYMax meet")


A("ice", crystals())
def icicles(seed: int) -> str:
    r = random.Random(seed)
    w, h = 240, 80
    pts, x = [(0, 0)], 0
    while x < w:
        step = r.uniform(9, 17)
        hh = r.uniform(14, 66) * (1 - .55 * x / w)
        pts += [(x + step * .15, 6), (x + step / 2, hh), (x + step * .85, 6)]
        x += step
    pts.append((w, 0))
    return svg(w, h, grad("g", "#ffffff", "#a6e0ff", .95, .2) + path(d_poly(pts), "url(#g)"), "xMinYMin meet")


A("icicles", icicles(6))

# ── Медные Сумерки: трубы кузни и шестерня (маской, цвет задаёт слой) ──
def pipes() -> str:
    d = "#170c07"
    body = poly([(18, 196), (25, 42), (22, 32), (58, 32), (55, 42), (62, 196)], d) + rect(20, 24, 40, 9, d)
    body += poly([(72, 196), (76, 96), (73, 90), (100, 90), (97, 96), (101, 196)], d) + rect(74, 83, 28, 8, d)
    body += rect(0, 150, 136, 11, d) + rect(104, 122, 9, 40, d) + circ(108.5, 116, 11, d) + circ(108.5, 116, 6, "#4a2616") + circ(108.5, 116, 2, d)
    body += rect(26, 168, 26, 28, "#3a1d10") + rect(30, 174, 18, 16, "#ff9a4a") + rect(33, 177, 12, 10, "#ffd27a")
    body += "".join(circ(x, 156, 1.3, "#e59a6b", "fill-opacity='.7'") for x in (12, 40, 68, 96, 124))
    body += stroke("M25 44L18 194M76 98L72 194M60 36L62 194", "#e59a6b", 1.1, "stroke-opacity='.5'")
    return svg(140, 200, body, "xMinYMax meet")


A("pipes", pipes())
A("cog", svg(100, 100, path(gear_d(50, 50, 48, 39, 14, 13), "#000", "fill-rule='evenodd'"), "xMidYMid meet"))

# ── Бутон Сакуры: ветка с тугими бутонами и распустившийся цветок ──
def bud(x: float, y: float, ang: float, s: float = 1) -> str:
    g = path("M0 0Q-5 -6 -3 -13Q0 -17 3 -13Q5 -6 0 0z", "#e9a3c0") + path("M0 -1Q-2 -6 -1 -11Q0 -13 1 -11Q2 -6 0 -1z", "#ffd6e6", "fill-opacity='.85'") + path("M-2.6 1.4Q0 -2 2.6 1.4Q0 3 -2.6 1.4z", "#5a2a3e")
    return f"<g transform='translate({n(x)} {n(y)}) rotate({n(ang)}) scale({s})'>{g}</g>"


def budded(mirror_it: bool) -> str:
    body = stroke("M0 128Q46 112 86 88Q128 62 172 40", "#1a0912", 5.4) + stroke("M60 100Q70 70 84 50", "#1a0912", 2.8) + stroke("M104 76Q120 96 132 118", "#1a0912", 2.6)
    body += stroke("M128 56Q138 34 154 20", "#1a0912", 2.4) + stroke("M84 50Q78 38 82 26", "#1a0912", 1.8) + stroke("M30 116Q32 94 42 78", "#1a0912", 2.2)
    body += bud(84, 50, 14, 1.15) + bud(82, 27, -10, .9) + bud(154, 21, 24, 1.1) + bud(132, 119, 160, 1) + bud(42, 78, -18, 1) + bud(172, 40, 62, 1.05) + bud(114, 84, 120, .85)
    return svg(180, 140, f"<g transform='translate(180 0) scale(-1 1)'>{body}</g>" if mirror_it else body, "xMidYMax meet")


A("budsL", budded(False))
A("budsR", budded(True))
A("bloom", svg(100, 100, "".join(ell(50, 27, 15, 24, "#000", f"transform='rotate({k * 72} 50 50)'") for k in range(5)) + circ(50, 50, 7, "#000"), "xMidYMid meet"))
