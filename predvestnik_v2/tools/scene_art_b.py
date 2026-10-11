"""Scene art B (skin-scene-b-v3.css): Инферно, Ханами, Нефритовый Двор, Небесное Сияние, Рубиновый Собор, Лазурная Обсерватория, Золотой Лотос."""
from __future__ import annotations

import math
import random

from scene_kit import (art, bezier, circ, d_poly, d_ridge, d_smooth, ell, flip, jag, lingrad, mirror, n, path, poly, radgrad, rect, ribbon, ridge, star_d, stroke, svg)


def B(name: str, value: str) -> None:
    art(name, "b", value)


# ── Инферно: вулканы с лавовыми реками, дальний хребет, оплавленные скалы, лавовая бомба ──
def lava_river(points, width: float = 1) -> str:
    """A glowing river: soft halo, hot body, white-yellow core; the gradient `lv` (hot at the crater, cold at the foot) is defined by the volcano."""
    d = d_smooth(points, closed=False)
    return stroke(d, "#ff4a1f", 5 * width, "stroke-opacity='.16'") + stroke(d, "url(#lv)", 2.4 * width) + stroke(d, "url(#lc)", .9 * width)


def volcano_body(seed: int, rim_l=(93, 57), rim_r=(117, 53), top=56) -> str:
    prof = [(0, 200), (16, 189), (34, 166), (48, 142), (58, 122), (68, 102), (78, 84), (86, 69), rim_l,
            (101, 62), (109, 60), rim_r, (126, 62), (135, 80), (145, 100), (156, 121), (169, 144), (184, 167), (200, 185), (220, 200)]
    prof = jag(prof, 2.4, seed, 1)
    body = lingrad("r", [(0, "#3a130d", 1), (.5, "#1b0808", 1), (1, "#080203", 1)]) + lingrad("lv", [(0, "#ffd27a", 1), (.4, "#ff7a2a", .9), (1, "#b82a18", .2)], 0, top, 0, 200, True)
    body += lingrad("lc", [(0, "#fff0b8", .95), (.5, "#ffc060", .5), (1, "#ff9a3a", 0)], 0, top, 0, 200, True)
    body += poly(prof, "url(#r)")
    cx = (rim_l[0] + rim_r[0]) / 2
    lit = [(x + 15, y + 3) for x, y in prof[2:10]]                                                              # the flank that faces the crater is lit
    body += poly(prof[2:10] + lit[::-1], "#7a2a18", "fill-opacity='.38'")
    body += stroke(d_smooth(prof[:16], closed=False), "#ff8a45", 1.2, "stroke-opacity='.55'") + stroke(d_smooth(prof[16:], closed=False), "#ff5a2a", 1, "stroke-opacity='.2'")
    body += lava_river([(cx - 1, 60), (cx - 6, 78), (cx + 1, 98), (cx - 8, 122), (cx - 2, 146), (cx - 13, 172), (cx - 11, 200)])
    body += lava_river([(cx + 5, 61), (cx + 17, 76), (cx + 14, 96), (cx + 29, 114), (cx + 27, 138), (cx + 44, 162), (cx + 42, 200)], .85)
    body += lava_river([(cx - 5, 62), (cx - 21, 82), (cx - 23, 100), (cx - 35, 118)], .7)
    for x, y in ((cx - 30, 142), (cx + 18, 120), (cx + 52, 150), (cx - 44, 166), (cx + 30, 176)):          # small vents and cracks
        body += stroke(f"M{n(x)} {n(y)}l5 -4l3 3l5 -3", "#ff8a3a", .9, "stroke-opacity='.7'")
    body += ell(cx, 59, 15, 4.6, "#ff8a2a") + ell(cx, 58, 9.5, 2.8, "#ffd27a") + ell(cx, 57.5, 4, 1.4, "#fff6cf")
    return body


def broad_volcano_body(seed: int) -> str:
    """A lower, wider mountain: a crater on the left peak and a small cone beside it."""
    prof = [(0, 200), (18, 192), (40, 176), (62, 152), (84, 124), (100, 100), (114, 84), (124, 72), (131, 66), (139, 70), (146, 69), (152, 72), (162, 82), (176, 98), (190, 112),
            (200, 104), (207, 98), (214, 104), (224, 122), (238, 148), (250, 174), (260, 196)]
    prof = jag(prof, 2.2, seed, 1)
    body = lingrad("r", [(0, "#3d1430", 1), (.5, "#1c0a14", 1), (1, "#0b0306", 1)]) + lingrad("lv", [(0, "#ffd27a", 1), (.4, "#ff7a2a", .9), (1, "#b82a18", .2)], 0, 66, 0, 200, True)
    body += lingrad("lc", [(0, "#fff0b8", .95), (.5, "#ffc060", .5), (1, "#ff9a3a", 0)], 0, 66, 0, 200, True)
    body += poly(prof, "url(#r)") + stroke(d_smooth(prof[:12], closed=False), "#ff8a45", 1.1, "stroke-opacity='.45'")
    body += lava_river([(138, 71), (130, 86), (136, 104), (124, 126), (130, 150), (118, 176), (120, 200)])
    body += lava_river([(144, 71), (156, 88), (152, 108), (164, 128), (160, 152)], .7)
    body += lava_river([(205, 100), (200, 114), (208, 130), (204, 150)], .55)
    for x, y in ((92, 146), (176, 128), (214, 150), (70, 172), (150, 176)):
        body += stroke(f"M{x} {y}l5 -4l3 3l5 -3", "#ff8a3a", .9, "stroke-opacity='.65'")
    body += ell(142, 70, 13, 4, "#ff8a2a") + ell(142, 69, 8, 2.4, "#ffd27a") + ell(142, 68.6, 3.4, 1.2, "#fff6cf") + ell(207, 98, 5, 1.6, "#ff9a3a") + ell(207, 97.6, 2.4, .8, "#ffe9a0")
    return body


B("volcL", svg(220, 200, volcano_body(3)))
B("volcR", svg(260, 200, broad_volcano_body(8), "xMaxYMax meet"))


def far_range() -> str:
    """A red-brown ridge far away: a few cones, two of them glowing."""
    w, h = 400, 100
    pts = [(0, 100), (30, 84), (58, 62), (74, 52), (90, 62), (112, 80), (150, 74), (182, 56), (200, 44), (216, 56), (244, 78), (280, 70), (312, 48), (330, 38), (346, 50), (372, 72), (400, 80)]
    body = path(d_poly(jag(pts, 1.8, 2) + [(400, 100)]), "#3a120c") + stroke(d_smooth(pts, closed=False), "#ff7a3a", .9, "stroke-opacity='.35'")
    for cx, cy in ((74, 52), (200, 44), (330, 38)):
        body += ell(cx, cy + 1, 7, 2.2, "#ff8a3a", "fill-opacity='.9'") + ell(cx, cy, 3.4, 1.1, "#ffe08a")
    body += stroke("M200 46Q196 60 200 78M330 40Q326 56 332 74M74 54Q70 66 74 80", "#ff7a3a", 1.2, "stroke-opacity='.55'")
    return svg(w, h, body, "none")


B("volcFar", far_range())


def crags() -> str:
    """Charred rocks along the foot with glowing seams."""
    w, h = 420, 74
    top = ridge(w, 30, 9, [(160, 1), (60, .6), (26, .35)], 5, .6, 60)
    body = path(d_ridge(top, w, h), "#0b0302") + stroke(d_smooth(top, closed=False), "#ff6a30", 1.1, "stroke-opacity='.55'")
    r = random.Random(9)
    for _ in range(14):
        x = r.uniform(8, w - 20)
        y = top[int(x / w * 60)][1] + r.uniform(8, 30)
        body += stroke(f"M{n(x)} {n(y)}l{n(r.uniform(4, 9))} {n(r.uniform(-4, 4))}l{n(r.uniform(3, 7))} {n(r.uniform(2, 6))}l{n(r.uniform(4, 8))} {n(r.uniform(-5, 2))}", "#ff8a3a", 1.1, "stroke-opacity='.75'")
        body += circ(x + 2, y, 1.4, "#ffd27a", "fill-opacity='.8'")
    return svg(w, h, body, "none")


B("crags", crags())


def fireball() -> str:
    """A lava bomb with a tail (a mask: the layer paints it hot to cold)."""
    body = path("M0 15Q16 9 34 11Q44 7 52 15Q44 23 34 19Q16 21 0 15z", "#000") + circ(51, 15, 9, "#000")
    return svg(64, 30, body, "xMaxYMid meet")


B("fireball", fireball())


def bolt() -> str:
    """Volcanic lightning (a mask): one jagged stroke with a short branch."""
    pts = [(26, 0), (15, 36), (27, 38), (10, 78), (22, 80), (3, 128), (36, 70), (22, 68), (34, 34), (22, 32), (32, 0)]
    return svg(40, 128, poly(pts, "#000") + stroke("M22 80L34 98L30 112", "#000", 2.2), "xMidYMin meet")


B("bolt", bolt())


# ── общие мелочи семейства: диск (маска), волна для бегущей полосы ──
B("disc", svg(100, 100, circ(50, 50, 48, "#000"), "xMidYMid meet"))


def tide(name: str, width: int, amp: float, top: str, rim: str, depth: int = 40, opacity: float = .55) -> None:
    """A wave strip for a running `wave go` layer: the crest line and a fading body below it."""
    pts = []
    for i in range(0, width + 1, width // 12):
        x = i / width * math.tau
        pts.append((i, depth * .42 - amp * (math.sin(x) * .7 + math.sin(2 * x + 1.1) * .45)))
    crest = d_smooth(pts, closed=False)
    B(name, svg(width, depth, lingrad("g", [(0, top, opacity), (1, top, 0)]) + path(crest + f"V{depth}H0z", "url(#g)") + stroke(crest, rim, 1.2, "stroke-opacity='.6'"), "none"))


# ── Ханами: вишнёвое дерево в цвету, тории, каменный фонарь, Фудзи в дымке, розовая вода ──
def blossoms(cx: float, cy: float, spread: float, count: int, seed: int, scale: float = 1) -> str:
    r = random.Random(seed)
    out = ""
    for _ in range(count):
        a, d = r.uniform(0, math.tau), spread * math.sqrt(r.random())
        x, y = cx + math.cos(a) * d, cy + math.sin(a) * d * .7
        out += circ(x, y, r.uniform(2.4, 6.2) * scale, r.choice(("#ffa8cc", "#ef6aa3", "#ffd6e6", "#ff8fbd", "#fff0f6")), f"fill-opacity='{r.uniform(.62, .95):.2f}'")
    return out


def sakura_tree() -> str:
    d = "#1a0b14"
    body = path("M44 262Q50 220 52 188Q54 160 62 140Q48 120 30 104Q18 94 8 86L12 80Q28 90 44 104Q58 116 70 128Q84 100 110 84Q134 70 168 56L170 62Q142 78 122 94Q100 112 90 134Q96 150 94 176Q92 212 98 262z", d)
    body += stroke("M60 138Q40 132 20 138", d, 3.2) + stroke("M92 138Q112 122 126 104", d, 2.8) + stroke("M120 92Q118 70 126 52", d, 2.4) + stroke("M70 126Q64 106 70 90", d, 2.4)
    for cx, cy, sp, k, sd in ((16, 86, 30, 46, 1), (150, 58, 36, 62, 2), (118, 94, 24, 30, 3), (72, 92, 26, 36, 4), (30, 130, 24, 28, 5), (126, 52, 22, 28, 6)):
        body += blossoms(cx, cy, sp, k, sd)
    body += "".join(circ(x, y, 1.6, "#ffa8cc", "fill-opacity='.8'") for x, y in ((40, 252), (52, 258), (84, 256), (104, 250), (70, 261)))     # petals under the tree
    return svg(200, 262, body, "xMinYMax meet")


B("sakuraTree", sakura_tree())


def torii() -> str:
    d, rim = "#3a0f1c", "#ff8fbd"
    body = path("M2 26Q30 36 60 32Q90 36 118 26L112 36Q90 44 60 42Q30 44 8 36z", d) + stroke("M2 26Q30 36 60 32Q90 36 118 26", rim, 1.1, "stroke-opacity='.55'")
    body += path("M14 52L106 52L106 60L14 60z", d) + rect(52, 38, 16, 14, d)
    body += poly([(22, 36), (31, 36), (33, 130), (24, 130)], d) + poly([(89, 36), (98, 36), (96, 130), (87, 130)], d)
    body += stroke("M22 37L24 130", rim, .9, "stroke-opacity='.4'") + stroke("M89 37L87 130", rim, .9, "stroke-opacity='.4'")
    return svg(120, 130, body, "xMidYMax meet")


B("torii", torii())


def stone_lantern() -> str:
    d = "#170a13"
    body = rect(10, 100, 40, 8, d) + poly([(20, 100), (24, 70), (36, 70), (40, 100)], d) + rect(17, 62, 26, 8, d)
    body += rect(14, 36, 32, 26, d) + rect(19, 41, 8, 16, "#ffd6a0", "fill-opacity='.95'") + rect(33, 41, 8, 16, "#ffb878", "fill-opacity='.9'")
    body += poly([(6, 36), (30, 14), (54, 36)], d) + poly([(2, 38), (58, 38), (52, 32), (8, 32)], d) + circ(30, 11, 4, d) + poly([(28, 7), (30, 0), (32, 7)], d)
    body += stroke("M8 33L30 15L52 33", "#ff8fbd", 1, "stroke-opacity='.45'")
    return svg(60, 110, body, "xMidYMax meet")


B("tourou", stone_lantern())


def fuji() -> str:
    w, h = 400, 120
    body = lingrad("m", [(0, "#8a5a82", .62), (.55, "#5a3452", .42), (1, "#3a2038", 0)])
    cone = [(0, 118), (60, 104), (110, 92), (150, 74), (176, 40), (190, 24), (200, 20), (210, 24), (224, 40), (250, 74), (290, 94), (340, 106), (400, 116)]
    body += path(d_poly(cone + [(400, 120), (0, 120)]), "url(#m)")
    body += poly([(176, 40), (186, 34), (190, 44), (196, 32), (202, 44), (208, 34), (214, 42), (224, 40), (210, 24), (200, 20), (190, 24)], "#fff0f6", "fill-opacity='.7'")
    body += radgrad("f", [(0, "#ffd6e6", .5), (1, "#ffd6e6", 0)]) + ell(200, 72, 210, 6, "url(#f)") + ell(180, 92, 220, 8, "url(#f)")      # soft mist bands cross the slope
    return svg(w, h, body, "none")


B("fuji", fuji())
tide("sakuWave", 120, 5, "#d86a9c", "#ffd6e6")
tide("sakuWave2", 180, 4, "#f0a0c4", "#fff0f6", 36, .5)


# ── Нефритовый Двор: пагода, лунные врата, бамбук, золотые фонари, нефритовый дракон, дальние горы ──
def pagoda() -> str:
    d, rim = "#031510", "#6fe0b8"
    body = poly([(6, 240), (114, 240), (108, 226), (12, 226)], d) + rect(16, 222, 88, 5, d)
    y = 222
    for i in range(5):
        wr = 50 - i * 7.5
        bw = wr * .62
        body += rect(60 - bw / 2, y - 22, bw, 22, d) + rect(60 - 3.4, y - 17, 6.8, 10, "#ffd98a", "fill-opacity='.95'")
        y -= 22
        roof = [(60 - wr - 7, y - 3), (60 - wr * .9, y + 7), (60 + wr * .9, y + 7), (60 + wr + 7, y - 3), (60 + wr * .55, y - 7), (60 + wr * .2, y - 14), (60, y - 17), (60 - wr * .2, y - 14), (60 - wr * .55, y - 7)]
        body += poly(roof, d) + stroke(f"M{n(60 - wr - 7)} {n(y - 3)}Q{n(60 - wr * .5)} {n(y - 12)} 60 {n(y - 17)}Q{n(60 + wr * .5)} {n(y - 12)} {n(60 + wr + 7)} {n(y - 3)}", rim, 1, "stroke-opacity='.5'")
        y -= 9
    body += rect(58.8, y - 26, 2.4, 28, d) + circ(60, y - 8, 3.6, d) + circ(60, y - 16, 3, d) + circ(60, y - 26, 2.6, d, ) + poly([(60, y - 38), (57, y - 26), (63, y - 26)], d)
    return svg(120, 240, body, "xMidYMax meet")


B("pagoda", pagoda())


def moon_gate() -> str:
    """A garden wall with a round opening; the wall melts into the mist on the right so it never ends in a hard edge."""
    d = "#04120d"
    cx, cy, r = 112, 128, 62
    hole = f"M{cx + r} {cy}A{r} {r} 0 1 0 {cx - r} {cy}A{r} {r} 0 1 0 {cx + r} {cy}z"
    body = lingrad("w", [(0, d, 1), (.6, d, 1), (1, d, 0)], 0, 0, 1, 0) + lingrad("wr", [(0, "#6fe0b8", .5), (.6, "#6fe0b8", .5), (1, "#6fe0b8", 0)], 0, 0, 1, 0)
    body += path(f"M0 52H230V200H0z{hole}", "url(#w)", "fill-rule='evenodd'")
    body += path("M-8 54L-8 46Q100 28 230 46L230 54z", "url(#w)") + stroke("M-8 46Q100 28 230 46", "url(#wr)", 1.1)
    body += "".join(stroke(f"M{x} {n(49 - 18 * math.sin((x + 8) / 226 * math.pi) + 8)}V{n(53)}", "#6fe0b8", .8, "stroke-opacity='.3'") for x in range(6, 170, 12))
    body += stroke(f"M{cx + r + 3} {cy}A{r + 3} {r + 3} 0 1 0 {cx - r - 3} {cy}A{r + 3} {r + 3} 0 1 0 {cx + r + 3} {cy}", "#6fe0b8", 1.3, "stroke-opacity='.55'")
    body += stroke(f"M{cx + r - 5} {cy}A{r - 5} {r - 5} 0 1 0 {cx - r + 5} {cy}A{r - 5} {r - 5} 0 1 0 {cx + r - 5} {cy}", "#e8cf8a", 1, "stroke-opacity='.45'")
    for k in range(9):                                                   # carved studs around the opening
        a = math.tau * k / 9 + .3
        body += circ(cx + (r + 9) * math.cos(a), cy + (r + 9) * math.sin(a), 1.6, "#e8cf8a", "fill-opacity='.45'")
    return svg(230, 200, body, "xMinYMax meet")


B("moonGate", moon_gate())


def bamboo() -> str:
    r = random.Random(14)
    d = "#031a0e"
    body = ""
    for x0, hh, lean in ((18, 224, -.05), (40, 190, .04), (62, 238, -.03), (84, 168, .06), (102, 206, -.04)):
        x1 = x0 + lean * hh
        body += stroke(f"M{x0} 240Q{n(x0 + lean * hh * .4)} {n(240 - hh * .5)} {n(x1)} {n(240 - hh)}", d, 7.2)
        body += stroke(f"M{x0 - 1.6} 240Q{n(x0 - 1.6 + lean * hh * .4)} {n(240 - hh * .5)} {n(x1 - 1.6)} {n(240 - hh)}", "#2a8a5a", 1.2, "stroke-opacity='.45'")
        for k in range(1, int(hh // 30) + 1):
            ny = 240 - k * 30
            nx = x0 + lean * (k * 30) * .8
            body += stroke(f"M{n(nx - 4.6)} {n(ny)}L{n(nx + 4.6)} {n(ny)}", "#0f4a2c", 2)
            if k > 2:
                for side in (-1, 1):
                    for j in range(2):
                        ang = r.uniform(.25, .85) * side + j * .5 * side
                        body += ell(nx + side * (13 + 4 * j), ny - 5 - 4 * j, 15, 2.8, d, f"transform='rotate({n(math.degrees(ang) * -1)} {n(nx)} {n(ny)})'")
    return svg(120, 240, body, "xMidYMax meet")


B("bamboo", bamboo())


def hanging_lantern() -> str:
    body = stroke("M20 0V24", "#7a5a20", 1.2) + rect(12, 22, 16, 5, "#7a5a20") + ell(20, 50, 15, 22, "#d9b24c") + ell(20, 50, 9, 19, "#ffe9a6", "fill-opacity='.55'")
    body += "".join(stroke(f"M20 {28 + (1 - abs(k)) * 0}Q{n(20 + k * 17)} 50 20 72", "#7a5a20", .9, "stroke-opacity='.85'") for k in (-.9, -.45, 0, .45, .9))
    body += rect(13, 70, 14, 5, "#7a5a20") + stroke("M20 75V86M17 75L15 84M23 75L25 84", "#c9863a", 1.3)
    return svg(40, 88, body, "xMidYMin meet")


B("hangLantern", hanging_lantern())


def dragon() -> str:
    """A long dragon as a mask: wave-like body, horned head with whiskers, four short legs, a tail tuft."""
    w, h = 360, 96
    spine = (bezier((0, 70), (24, 6), (52, 8), (80, 44), 12)[:-1] + bezier((80, 44), (104, 80), (132, 84), (160, 48), 12)[:-1] +
             bezier((160, 48), (184, 12), (212, 14), (240, 44), 12)[:-1] + bezier((240, 44), (254, 60), (268, 58), (280, 46), 8))
    radii = [1.2 + (3.6 + 6.4 * math.sin(math.pi * min(i / (len(spine) * .55), 1))) * (1 if i < len(spine) * .8 else 1 - (i - len(spine) * .8) / (len(spine) * .2) * .4) for i in range(len(spine))]
    body = path(d_poly(ribbon(spine, radii)), "#000")
    hx, hy = spine[-1]
    body += poly([(hx - 10, hy - 11), (hx + 8, hy - 15), (hx + 30, hy - 9), (hx + 44, hy - 5), (hx + 46, hy + 1), (hx + 30, hy - 1), (hx + 8, hy + 8), (hx - 10, hy + 12)], "#000")   # head and upper jaw
    body += poly([(hx + 2, hy + 5), (hx + 28, hy + 3), (hx + 40, hy + 8), (hx + 24, hy + 13), (hx + 4, hy + 13)], "#000")                                                   # lower jaw
    body += poly([(hx - 12, hy - 4), (hx - 22, hy + 4), (hx - 8, hy + 8)], "#000")                                                                                          # cheek spike
    body += stroke(f"M{n(hx + 2)} {n(hy - 13)}Q{n(hx - 8)} {n(hy - 28)} {n(hx - 24)} {n(hy - 30)}M{n(hx + 12)} {n(hy - 14)}Q{n(hx + 6)} {n(hy - 32)} {n(hx - 8)} {n(hy - 37)}", "#000", 2.8)
    body += stroke(f"M{n(hx + 44)} {n(hy - 2)}Q{n(hx + 58)} {n(hy + 10)} {n(hx + 70)} {n(hy + 2)}M{n(hx + 40)} {n(hy + 6)}Q{n(hx + 54)} {n(hy + 22)} {n(hx + 68)} {n(hy + 18)}", "#000", 1.5)
    for i in (9, 19, 29, 38):
        x, y = spine[i]
        body += stroke(f"M{n(x)} {n(y + 5)}l{n(3)} 14l5 3M{n(x)} {n(y + 5)}l-3 13l-5 2", "#000", 2.2)
    for i in range(6, len(spine) - 6, 3):                                   # mane
        x, y = spine[i]
        body += poly([(x - 2, y - radii[i] + 1), (x + 3, y - radii[i] - 8), (x + 5, y - radii[i] + 1)], "#000")
    body += stroke("M0 70Q-6 80 -14 78", "#000", 2)
    return svg(w, h, body, "xMidYMid meet")


B("dragon", dragon())


def jade_hills() -> str:
    w, h = 400, 100
    pts = ridge(w, 62, 26, [(260, 1), (110, .6), (48, .25)], 11, .5, 50, lambda t: .45 + .55 * (1 - abs(t - .5) * 2) ** .6)
    body = lingrad("h", [(0, "#2a7a62", .8), (1, "#0d3a2c", .6)]) + path(d_ridge(pts, w, h), "url(#h)") + stroke(d_smooth(pts, closed=False), "#6fe0b8", .9, "stroke-opacity='.4'")
    body += radgrad("f", [(0, "#c8f5e4", .34), (1, "#c8f5e4", 0)]) + ell(200, 76, 220, 7, "url(#f)")
    return svg(w, h, body, "none")


B("jadeHills", jade_hills())
tide("jadeWave", 120, 5, "#1f9a74", "#8dffd0")
tide("jadeWave2", 180, 4, "#3fc79c", "#d8fff0", 36, .5)


# ── Небесное Сияние: море облаков, мраморные колонны, голуби, перья и витражная роза ──
def cloud_top(w: float, base: float, amp: float, bumps: int, seed: int, steps_per: int = 10):
    """The upper edge of a cloud bank: round bumps (half ellipses) of different width and height."""
    r = random.Random(seed)
    widths = [r.uniform(.6, 1.6) for _ in range(bumps)]
    total = sum(widths)
    pts, x0 = [], 0.0
    for wd in widths:
        bw = wd / total * w
        h = amp * r.uniform(.5, 1)
        for i in range(steps_per + 1):
            t = i / steps_per
            pts.append((x0 + bw * t, base - h * math.sqrt(max(0.0, 1 - (2 * t - 1) ** 2))))
        x0 += bw
    return pts


def cloud_sea() -> str:
    """A sea of clouds at dawn: the far bank is lit gold, the nearest one is dark blue with a golden crest (the title of the player stands on it and must stay readable)."""
    w, h = 400, 100
    body = lingrad("a", [(0, "#ffe6b0", .62), (1, "#ffe6b0", 0)]) + lingrad("b", [(0, "#c9a27a", .62), (1, "#c9a27a", 0)]) + lingrad("c", [(0, "#3e4a80", .9), (.6, "#2a3466", .62), (1, "#2a3466", 0)])
    for base, amp, bumps, seed, fill, rim, rim_alpha in ((54, 15, 11, 3, "a", "#fff6dd", .5), (70, 19, 8, 8, "b", "#ffe1a8", .45), (86, 21, 6, 15, "c", "#ffd78a", .6)):
        pts = cloud_top(w, base, amp, bumps, seed)
        body += path(d_poly(pts + [(w, h), (0, h)]), f"url(#{fill})")
        body += stroke("".join(("M" if i == 0 else "L") + f"{n(x)} {n(y)}" for i, (x, y) in enumerate(pts)), rim, .9, f"stroke-opacity='{rim_alpha}'")
    return svg(w, h, body, "none")


B("clouds", cloud_sea())


def column() -> str:
    w, h = 76, 300
    light, mid, dark = "#d9d2bd", "#9a9482", "#56524a"
    body = lingrad("s", [(0, light, 1), (.45, mid, 1), (1, dark, 1)], 0, 0, 1, 0)
    body += rect(8, 284, 60, 16, dark) + rect(12, 274, 52, 10, mid) + ell(38, 270, 24, 5, mid)                                  # base
    body += poly([(20, 270), (56, 270), (53, 62), (23, 62)], "url(#s)")                                                          # shaft
    body += "".join(stroke(f"M{x} 268L{n(x * .12 + 38 * .88 - 1.2 * (38 - x) / 10)} 64", dark, 1, "stroke-opacity='.45'") for x in (26, 31, 36, 41, 46, 51))
    body += rect(14, 52, 48, 10, mid) + path("M12 50Q38 38 64 50L64 54Q38 44 12 54z", light) + rect(10, 42, 56, 8, light)        # capital
    body += stroke("M16 50Q10 62 18 66Q24 64 22 58M60 50Q66 62 58 66Q52 64 54 58", dark, 2.2) + circ(18, 59, 2.4, dark) + circ(58, 59, 2.4, dark)
    body += stroke("M23 270L22 64", "#fff2c8", 1.1, "stroke-opacity='.6'")
    return svg(w, h, body, "xMidYMax meet")


B("column", column())


def dove(x: float, y: float, s: float) -> str:
    g = ell(30, 21, 13, 5, "#000", "transform='rotate(-12 30 21)'") + circ(43, 17, 4.4, "#000") + poly([(46, 15.5), (52, 17), (46, 19)], "#000")
    g += poly([(19, 23), (4, 29), (7, 23), (3, 19)], "#000") + path("M31 18Q22 -2 4 2Q16 8 20 21z", "#000") + path("M33 18Q38 2 54 0Q46 9 40 21z", "#000")
    return f"<g transform='translate({n(x)} {n(y)}) scale({s})'>{g}</g>"


B("doves", svg(150, 70, dove(46, 0, .9) + dove(4, 26, 1) + dove(84, 30, .8) + dove(104, 6, .7), "xMidYMid meet"))
def feather() -> str:
    """A drifting feather: two vanes with notched edges, a thin gap along the shaft."""
    left, right = [(9.2, 1)], [(10.8, 1)]
    for i in range(1, 9):
        y = 1 + i * 5.2
        spread = 8.4 * math.sin(min(1, i / 8) * 2.0) * (1 - i / 17)
        notch = 1.1 if i % 2 else 0
        left.append((9.2 - spread + notch, y)); right.append((10.8 + spread - notch, y + (2.2 if i % 2 else 0)))
    left.append((9.4, 47)); right.append((10.6, 47))
    body = poly(left, "#000") + poly(right, "#000") + stroke("M10 2L10 48", "#000", .7, "stroke-opacity='.55'")
    return svg(20, 48, body, "xMidYMid meet")


B("feather", feather())


def rose_window() -> str:
    cx = cy = 100
    ink = "#000"
    circle = lambda r: f"M{cx + r} {cy}A{r} {r} 0 1 0 {cx - r} {cy}A{r} {r} 0 1 0 {cx + r} {cy}"      # noqa: E731
    body = stroke(circle(95), ink, 6) + stroke(circle(82), ink, 2.4) + stroke(circle(46), ink, 4) + stroke(circle(14), ink, 4)
    for k in range(12):
        a, b = math.tau * k / 12, math.tau * (k + 1) / 12
        m = (a + b) / 2
        p = lambda ang, r: (cx + r * math.cos(ang), cy + r * math.sin(ang))   # noqa: E731
        (x1, y1), (x2, y2), (xm, ym), (xo, yo) = p(a, 46), p(b, 46), p(m, 66), p(m, 82)
        body += stroke(f"M{n(cx + 14 * math.cos(a))} {n(cy + 14 * math.sin(a))}L{n(p(a, 82)[0])} {n(p(a, 82)[1])}", ink, 2.6)
        body += stroke(f"M{n(x1)} {n(y1)}Q{n(xm + (xm - cx) * .5)} {n(ym + (ym - cy) * .5)} {n(x2)} {n(y2)}", ink, 2.4)
        body += circ(xm, ym, 5.2, ink) + circ(xo, yo, 2.6, ink)
    return svg(200, 200, body, "xMidYMid meet")


B("rose", rose_window())


# ── Рубиновый Собор: половина готической арки с витражом, подсвечник, люстра ──
def nave_half() -> str:
    """The left half of the nave seen from the middle: a pier, a rib that rises to the apex in the middle and a lancet window in the wall (the right half is this picture mirrored)."""
    w, h = 195, 347
    rib = "M44 150C44 60 110 20 195 6"
    body = lingrad("wall", [(0, "#0a0206", 1), (1, "#1c0710", 1)], 0, 0, 1, 0) + lingrad("glass", [(0, "#ff8a9a", 1), (.45, "#b3122f", 1), (1, "#4a0716", 1)])
    body += path(f"M0 0H195V6C110 20 44 60 44 150V347H0z", "url(#wall)")
    body += path("M14 142V88Q14 66 36 50Q58 66 58 88V142z", "url(#glass)", "fill-opacity='.95'")                       # the lancet window
    body += path("M24 138V90Q24 78 36 66Q48 78 48 90V138z", "#ffb25a", "fill-opacity='.35'")
    body += stroke("M14 98L58 98M14 118L58 118M36 50V142M25 62L47 142M47 62L25 142", "#14040a", 1.6, "stroke-opacity='.85'")
    body += stroke("M14 142V88Q14 66 36 50Q58 66 58 88V142z", "#f4d9b0", 1.2, "stroke-opacity='.4'")
    body += stroke(rib, "#2a0a12", 11) + stroke(rib, "#ff7a8e", 1.3, "stroke-opacity='.55'") + stroke("M44 146C44 64 108 26 195 12", "#f4d9b0", .9, "stroke-opacity='.28'")
    body += rect(36, 146, 18, 8, "#f4d9b0", "fill-opacity='.35'") + rect(0, 322, 50, 25, "#2a0a12") + rect(34, 154, 5, 168, "#30101a", "fill-opacity='.8'")
    body += "".join(stroke(f"M{x} 156V320", "#ff7a8e", .8, "stroke-opacity='.18'") for x in (8, 16, 24))
    return svg(w, h, body, "none")


B("nave", nave_half())


CANDLES = ((12, 76), (22, 70), (35, 48), (48, 70), (58, 76))     # where the five candles of the candelabra stand


def candelabra() -> str:
    """Iron stand with five wax candles; the flames are a picture of their own (flames) in the same frame, so they can flicker."""
    iron, gold = "#1a0a10", "#c9863a"
    body = poly([(35, 112), (22, 168), (30, 168), (35, 140), (40, 168), (48, 168)], iron) + rect(33, 100, 4, 44, iron) + circ(35, 124, 4.6, iron) + circ(35, 104, 3.4, iron)
    body += stroke("M35 100Q35 70 35 48M35 100Q22 96 22 70M35 100Q48 96 48 70M35 100Q14 98 12 76M35 100Q56 98 58 76", iron, 2.2)
    for x, y in CANDLES:
        body += rect(x - 4.4, y - 2, 8.8, 4, gold, "fill-opacity='.8'") + rect(x - 2.6, y - 20, 5.2, 19, "#f4d9b0") + stroke(f"M{x - 2.6} {y - 20}V{y - 2}", "#fff4dc", .8, "stroke-opacity='.7'")
    body += stroke("M35 100Q35 70 35 48M35 100Q22 96 22 70", gold, .8, "stroke-opacity='.45'")
    return svg(70, 170, body, "xMidYMax meet")


B("candelabra", candelabra())


def candle_flames() -> str:
    body = radgrad("h", [(0, "#ffb23a", .6), (.5, "#ff8a2a", .22), (1, "#ff8a2a", 0)])
    for x, y in CANDLES:
        body += circ(x, y - 27, 13, "url(#h)")
        body += path(f"M{x} {y - 33}Q{x + 3.8} {y - 26} {x} {y - 21}Q{x - 3.8} {y - 26} {x} {y - 33}z", "#ffb23a") + path(f"M{x} {y - 29}Q{x + 1.8} {y - 25.5} {x} {y - 22.5}Q{x - 1.8} {y - 25.5} {x} {y - 29}z", "#fff2b0")
    return svg(70, 170, body, "xMidYMax meet")


B("flames", candle_flames())


def censer() -> str:
    """A brass thurible on a chain: the chain starts at the top edge of the picture, so a swing around the top middle is the real swing."""
    body = lingrad("b", [(0, "#f4d9b0", 1), (.45, "#d9a24a", 1), (1, "#5a3410", 1)], 0, 0, 1, 1)
    body += "".join(ell(20, y, 1.7, 3.6, "none", "stroke='#d9a24a' stroke-width='1.1' stroke-opacity='.9'") for y in range(4, 80, 8))
    body += stroke("M20 82L9 102M20 82L31 102M20 82V100", "#d9a24a", .9, "stroke-opacity='.75'") + circ(20, 81, 2.6, "none", "stroke='#f4d9b0' stroke-width='1' stroke-opacity='.8'")
    body += path("M9 104Q20 88 31 104z", "url(#b)") + circ(20, 90, 2.2, "url(#b)") + path("M8 104H32Q32 126 20 132Q8 126 8 104z", "url(#b)")
    body += stroke("M8 104H32", "#f4d9b0", 1, "stroke-opacity='.7'")
    body += "".join(ell(x, y, 1.6, 2.6, "#ff7a3a", "fill-opacity='.9'") for x, y in ((14, 112), (20, 115), (26, 112), (17, 122), (23, 122)))
    body += poly([(20, 132), (17, 139), (23, 139)], "url(#b)")
    return svg(40, 150, body, "xMidYMin meet")


B("censer", censer())


def corona() -> str:
    """Streamers of an eclipse corona around the hidden disc (the disc is drawn by the scene): broad curved petals that fade towards their tips, thin hairs between them;
    the streamers shrink towards the bottom, where the nickname and the title of the player stand."""
    r = random.Random(11)
    cx = cy = 150
    base, count = 82, 28
    body = "<defs><radialGradient id='f' gradientUnits='userSpaceOnUse' cx='150' cy='150' r='150'><stop offset='.5' stop-color='#000' stop-opacity='1'/><stop offset='.78' stop-color='#000' stop-opacity='.7'/><stop offset='1' stop-color='#000' stop-opacity='0'/></radialGradient></defs>"
    pt = lambda ang, rad: f"{n(cx + rad * math.cos(ang))} {n(cy + rad * math.sin(ang))}"      # noqa: E731
    reach = lambda ang: min(1.0, max(.0, (abs(math.atan2(math.sin(ang - math.pi / 2), math.cos(ang - math.pi / 2))) - .45) / .7))      # noqa: E731  0 straight down, 1 from 65° off the bottom
    for k in range(count):
        a = math.tau * (k + r.uniform(-.25, .25)) / count
        tip, half, bend = 104 + 44 * r.random() ** 1.2, r.uniform(.04, .085), r.uniform(-.09, .09)
        tip = base + (tip - base) * reach(a)
        if tip < base + 10:
            continue
        mid = (base + tip) / 2
        body += path(f"M{pt(a - half, base)}Q{pt(a - half * .8 + bend * .4, mid)} {pt(a + bend, tip)}Q{pt(a + half * .8 + bend * .4, mid)} {pt(a + half, base)}z", "url(#f)")
    for _ in range(64):
        a = r.uniform(0, math.tau)
        length = (12 + 40 * r.random() ** 1.3) * reach(a)
        if length > 8:
            body += stroke(f"M{pt(a, base + 1)}L{pt(a + r.uniform(-.03, .03), base + 1 + length)}", "url(#f)", r.uniform(.5, 1.2))
    body += circ(cx, cy, base + 2, "none", "stroke='#000' stroke-width='3' stroke-opacity='.85'")
    return svg(300, 300, body, "xMidYMid meet")


B("corona", corona())


# ── Лазурная Обсерватория: купол с щелью, армиллярная сфера, оррери, орбиты с планетами, созвездие, газовый гигант ──
def dome_shell() -> str:
    w, h = 390, 347
    sl, sr = 92, 348                                     # the slit of the dome: wide, the telescope of the avatar looks out of it to the upper right
    brass = "#e0b86a"
    body = lingrad("shell", [(0, "#050a20", .96), (1, "#0b1a44", .88)], 0, 0, 1, 0) + lingrad("shr", [(0, "#0b1a44", .88), (1, "#050a20", .96)], 0, 0, 1, 0)
    body += path(f"M0 0H{sl}Q{sl + 4} {h / 2} {sl - 6} {h}H0z", "url(#shell)") + path(f"M{w} 0H{sr}Q{sr - 4} {h / 2} {sr + 6} {h}H{w}z", "url(#shr)")
    for x1, x2 in ((74, 62), (52, 34), (28, 4)):                                         # meridian ribs fan out from the zenith
        body += stroke(f"M{x1 + 16} 0Q{(x1 + x2) / 2 + 8} {h * .55} {x2 - 8} {h}", brass, 1.1, "stroke-opacity='.35'")
    body += stroke(f"M{w - 18} 0Q{w - 14} {h * .55} {w - 24} {h}", brass, 1.1, "stroke-opacity='.3'")
    for y, sag in ((70, 10), (140, 16), (220, 24), (290, 30)):                              # ring girders
        body += stroke(f"M0 {y}Q{sl * .5} {y + sag} {sl - 2} {y + sag * .5}", brass, 1.2, "stroke-opacity='.42'") + stroke(f"M{w} {y}Q{w - 20} {y + sag * .8} {sr + 2} {y + sag * .5}", brass, 1.2, "stroke-opacity='.4'")
        body += "".join(circ(x, y + sag * .5 * (1 - x / sl) + 1, 1.5, brass, "fill-opacity='.6'") for x in (20, 46, 72))
        body += circ(w - 20, y + sag * .5, 1.5, brass, "fill-opacity='.55'")
    body += stroke(f"M{sl} 0Q{sl + 4} {h / 2} {sl - 6} {h}", brass, 2.2, "stroke-opacity='.75'") + stroke(f"M{sr} 0Q{sr - 4} {h / 2} {sr + 6} {h}", brass, 2.2, "stroke-opacity='.75'")
    body += stroke(f"M{sl + 3} 0Q{sl + 7} {h / 2} {sl - 3} {h}", "#fff1c8", .8, "stroke-opacity='.4'") + stroke(f"M{sr - 3} 0Q{sr - 7} {h / 2} {sr + 3} {h}", "#fff1c8", .8, "stroke-opacity='.4'")
    return svg(w, h, body, "none")


B("domeShell", dome_shell())


def armillary() -> str:
    brass, dark = "#e0b86a", "#6a4a1a"
    body = poly([(50, 96), (38, 126), (62, 126)], dark) + rect(30, 124, 40, 6, dark) + rect(45, 86, 10, 12, dark) + circ(50, 50, 40, "none", f"stroke='{brass}' stroke-width='2.2' stroke-opacity='.9'")
    body += ell(50, 50, 40, 11, "none", f"stroke='{brass}' stroke-width='1.8' stroke-opacity='.85'") + ell(50, 50, 13, 40, "none", f"stroke='{brass}' stroke-width='1.6' stroke-opacity='.8' transform='rotate(28 50 50)'")
    body += ell(50, 50, 13, 40, "none", f"stroke='#fff1c8' stroke-width='1' stroke-opacity='.6' transform='rotate(-30 50 50)'") + stroke("M24 80L76 20", brass, 1.6, "stroke-opacity='.9'")
    body += circ(50, 50, 7, "#7fb2ff") + circ(48, 48, 2.6, "#d8eaff") + circ(88, 50, 3.4, brass) + circ(12, 52, 2.6, brass)
    return svg(100, 130, body, "xMidYMax meet")


B("armillary", armillary())


def orrery() -> str:
    brass, dark = "#e0b86a", "#5a3e14"
    body = ell(60, 98, 46, 8, dark) + rect(56, 66, 8, 32, dark) + ell(60, 66, 24, 5, brass, "fill-opacity='.8'")
    for rx, ry in ((50, 15), (34, 10), (19, 6)):
        body += ell(60, 50, rx, ry, "none", f"stroke='{brass}' stroke-width='1.1' stroke-opacity='.6'")
    body += circ(60, 50, 7, "#ffd27a") + circ(60, 50, 3, "#fff6d0") + circ(108, 50, 4.4, "#7fb2ff") + circ(26, 59, 3.4, "#e07a5a") + circ(76, 45, 2.4, "#cfd6e8") + circ(39, 44, 2, brass)
    body += stroke("M60 50L108 50M60 50L26 59", brass, .9, "stroke-opacity='.7'")
    return svg(120, 110, body, "xMidYMax meet")


B("orrery", orrery())


def orbits() -> str:
    """Three planet orbits around the middle of the picture; drawn so that the smallest one stays clear of the avatar frame when the picture is about 460 px wide."""
    body = ""
    for r, dash in ((69, ""), (97, "3 6"), (130, "")):
        body += circ(150, 150, r, "none", f"stroke='#000' stroke-width='1.4' {'stroke-dasharray=' + chr(39) + dash + chr(39) if dash else ''}")
    for r, a, pr in ((69, .7, 3.4), (97, 3.6, 5), (130, 5.4, 3.8), (130, 1.9, 2.8)):
        x, y = 150 + r * math.cos(a), 150 + r * math.sin(a)
        body += circ(x, y, pr, "#000")
    body += circ(150 + 97 * math.cos(3.6) + 8, 150 + 97 * math.sin(3.6) - 6, 1.7, "#000")
    return svg(300, 300, body, "xMidYMid meet")


B("orbits", orbits())


def constellation() -> str:
    pts = [(30, 14), (74, 20), (52, 52), (46, 58), (58, 62), (22, 96), (84, 92)]
    body = stroke("M30 14L52 52L74 20M46 58L22 96M58 62L84 92M52 52L46 58L58 62", "#000", 1)
    for i, (x, y) in enumerate(pts):
        body += circ(x, y, (4.2, 3.4, 3, 2.4, 2.6, 3.8, 3.2)[i], "#000")
    body += path(star_d(30, 14, 11), "#000") + path(star_d(84, 92, 9), "#000")
    return svg(110, 110, body, "xMidYMid meet")


B("constellation", constellation())


def gas_giant() -> str:
    body = "<defs><clipPath id='c'><circle cx='60' cy='60' r='52'/></clipPath></defs>"
    bands = ((8, 22, "#3a68d8"), (30, 12, "#1f3f9a"), (42, 18, "#9ac0ff"), (60, 10, "#2a56c9"), (70, 16, "#7fb2ff"), (86, 12, "#16307a"), (98, 20, "#3a68d8"))
    body += "<g clip-path='url(#c)'>" + circ(60, 60, 52, "#2f5cc4") + "".join(rect(0, y, 120, hh, col, "fill-opacity='.88'") for y, hh, col in bands)
    body += ell(32, 52, 14, 4.5, "#e0b86a", "fill-opacity='.85'") + ell(32, 52, 8, 2.2, "#fff1c8", "fill-opacity='.5'")
    body += radgrad("sh", [(0, "#000", 0), (.62, "#000", .1), (1, "#000", .78)], .36, .34, .78) + circ(60, 60, 52, "url(#sh)") + "</g>"
    body += circ(60, 60, 52, "none", "stroke='#9ac0ff' stroke-width='1' stroke-opacity='.45'")
    return svg(120, 120, body, "xMidYMid meet")


B("gasGiant", gas_giant())


# ── Золотой Лотос: дальний берег и храм, лотосы на переднем плане, цапля, журавль в небе, плавучий фонарик, мандала из лепестков ──
def temple_shore() -> str:
    w, h = 400, 100
    pts = ridge(w, 66, 18, [(230, 1), (96, .5), (40, .2)], 5, .6, 60, lambda t: .45 + .55 * (1 - abs(t - .4) * 1.5) ** .6)
    body = lingrad("h", [(0, "#6a3e14", .85), (1, "#2a1606", .75)]) + path(d_ridge(pts, w, h), "url(#h)") + stroke(d_smooth(pts, closed=False), "#ffd27a", .9, "stroke-opacity='.45'")
    body += radgrad("f", [(0, "#ffe9b0", .34), (1, "#ffe9b0", 0)]) + ell(200, 80, 220, 7, "url(#f)")
    return svg(w, h, body, "none")


B("shore", temple_shore())


def roof(cx: float, y: float, half: float, tip: float, rise: float, fill: str = "url(#r)") -> str:
    """A curved temple roof: the eaves swing up at both ends; `y` is the eave line, `rise` the height of the ridge above it."""
    return (path(f"M{n(cx - half - tip)} {n(y - rise * .55)}Q{n(cx - half * .5)} {n(y + 3)} {n(cx)} {n(y - rise)}Q{n(cx + half * .5)} {n(y + 3)} {n(cx + half + tip)} {n(y - rise * .55)}L{n(cx + half)} {n(y + 5)}H{n(cx - half)}z", fill)
            + stroke(f"M{n(cx - half - tip)} {n(y - rise * .55)}Q{n(cx - half * .5)} {n(y + 3)} {n(cx)} {n(y - rise)}Q{n(cx + half * .5)} {n(y + 3)} {n(cx + half + tip)} {n(y - rise * .55)}", "#ffd27a", 1, "stroke-opacity='.55'"))


def temple() -> str:
    dark = "#2a1606"
    body = lingrad("t", [(0, "#6a3e14", 1), (1, dark, 1)]) + lingrad("r", [(0, "#8a5420", 1), (1, "#3a2008", 1)])
    body += rect(6, 108, 168, 12, "url(#t)") + rect(16, 100, 148, 9, "url(#t)") + poly([(76, 120), (80, 100), (100, 100), (104, 120)], dark)
    body += rect(46, 80, 88, 20, "url(#t)") + rect(66, 58, 48, 22, "url(#t)") + rect(80, 38, 20, 20, "url(#t)")                      # three tiers of the hall
    body += rect(10, 86, 32, 14, "url(#t)") + rect(138, 86, 32, 14, "url(#t)")                                                    # side pavilions
    body += "".join(stroke(f"M{x} 82V100", "#ffd27a", 1, "stroke-opacity='.3'") for x in (56, 70, 110, 124)) + "".join(rect(x, 84, 9, 14, "#ffd27a", "fill-opacity='.85'") for x in (82, 94))
    body += rect(74, 62, 8, 12, "#ffd27a", "fill-opacity='.7'") + rect(98, 62, 8, 12, "#ffd27a", "fill-opacity='.7'") + rect(86, 42, 8, 12, "#ffd27a", "fill-opacity='.8'")
    body += rect(16, 88, 6, 9, "#ffd27a", "fill-opacity='.7'") + rect(158, 88, 6, 9, "#ffd27a", "fill-opacity='.7'")
    body += roof(26, 86, 22, 8, 12) + roof(154, 86, 22, 8, 12) + roof(90, 80, 52, 12, 18) + roof(90, 58, 38, 10, 15) + roof(90, 38, 24, 8, 12)
    body += stroke("M90 26V8", "#ffd27a", 1.4, "stroke-opacity='.8'") + circ(90, 8, 2.4, "#ffd27a") + "".join(ell(90, y, 4.2, 1.4, "none", "stroke='#ffd27a' stroke-width='.9' stroke-opacity='.7'") for y in (14, 19))
    return svg(180, 120, body, "xMidYMax meet")


B("temple", temple())


def lotus_bloom(x: float, y: float, s: float, tilt: float = 0) -> str:
    def petal(ang: float, length: float, width: float, fill: str) -> str:
        return f"<g transform='translate({n(x)} {n(y)}) rotate({n(ang + tilt)}) scale({s})'><path d='M0 0Q{-width} {-length * .55} 0 {-length}Q{width} {-length * .55} 0 0z' fill='{fill}' stroke='#ffd27a' stroke-width='.7' stroke-opacity='.55'/></g>"
    body = "".join(petal(a, 26, 9, "url(#po)") for a in (-64, -38, 38, 64)) + "".join(petal(a, 30, 8.5, "url(#pi)") for a in (-18, 18)) + petal(0, 33, 8, "url(#pi)")
    return body + ell(x, y, 5 * s, 2 * s, "#e08a4a", "fill-opacity='.9'")


def lotus_plants() -> str:
    body = lingrad("po", [(0, "#ffe9f0", 1), (1, "#ffb6c8", 1)]) + lingrad("pi", [(0, "#ffd27a", 1), (1, "#ffe9f0", 1)]) + lingrad("lf", [(0, "#6a3e14", 1), (1, "#2a1606", 1)])
    stem = "stroke='#3a2a0c' stroke-width='2.6' fill='none'"
    body += f"<path d='M38 200C36 150 44 104 40 64' {stem}/><path d='M74 200C76 160 70 120 72 86' {stem}/><path d='M110 200C108 170 114 140 112 118' {stem}/><path d='M18 200C20 170 14 142 18 118' {stem}/>"
    body += ell(40, 62, 31, 10.5, "url(#lf)", "transform='rotate(-10 40 62)'") + stroke("M10 66Q40 50 70 56", "#ffd27a", 1, "stroke-opacity='.5'") + "".join(stroke(f"M40 62L{n(40 + 30 * math.cos(a))} {n(62 + 10 * math.sin(a) - 4)}", "#ffd27a", .6, "stroke-opacity='.3'") for a in (-2.6, -1.9, -1.2, -.5, .2, .9, 1.6))
    body += lotus_bloom(74, 86, 1.0, 6) + lotus_bloom(112, 118, .72, -8)
    body += ell(18, 116, 4.4, 8, "#ffb6c8") + path("M18 108Q13 118 18 126Q23 118 18 108z", "#ffe9f0", "fill-opacity='.9'")
    body += ell(30, 192, 27, 6, "url(#lf)") + ell(88, 197, 30, 6, "url(#lf)") + ell(132, 190, 18, 5, "url(#lf)") + ell(14, 190, 14, 4, "url(#lf)")
    body += "".join(stroke(f"M{x - rx} {y}Q{x} {y - ry * 1.4} {x + rx} {y}", "#ffd27a", .8, "stroke-opacity='.45'") for x, y, rx, ry in ((30, 192, 27, 6), (88, 197, 30, 6), (132, 190, 18, 5)))
    return svg(150, 200, body, "xMinYMax meet")


B("lotusPlants", lotus_plants())


def heron() -> str:
    """A heron wading on one leg: dark body, a long S-curved neck, a long beak."""
    ink = "#2a1606"
    body = stroke("M30 62L28 106M27 106L22 108M27 106L32 109", ink, 1.8) + stroke("M34 62Q44 74 40 86Q38 92 42 98", ink, 1.4)
    body += path("M10 60Q8 48 18 46Q30 40 42 48Q48 56 36 64Q24 68 10 60z", ink) + path("M12 58Q2 54 0 62Q8 66 16 62z", ink)
    body += stroke("M40 48Q54 44 52 30Q50 20 44 16", ink, 3.4) + circ(44, 14, 4.2, ink) + poly([(47, 12), (60, 15), (47, 17.5)], ink)
    body += stroke("M14 52Q26 44 38 52", "#ffd27a", .9, "stroke-opacity='.5'") + stroke("M44 14Q46 12 48 12", "#ffd27a", .8, "stroke-opacity='.5'")
    return svg(64, 112, body, "xMidYMax meet")


B("crane", heron())


def crane_fly() -> str:
    body = ell(80, 40, 22, 6, "#000", "transform='rotate(-4 80 40)'") + stroke("M98 38Q112 36 124 30", "#000", 3.2) + circ(127, 28.6, 3, "#000") + poly([(129.5, 27.4), (142, 30), (129.5, 30.6)], "#000")
    body += stroke("M60 42L24 47M24 47L18 50M24 47L19 46", "#000", 1.4) + poly([(58, 40), (44, 44), (58, 44)], "#000")
    body += path("M72 37C68 20 52 7 28 3C44 14 54 26 58 40z", "#000") + path("M60 36C54 24 44 16 32 12", "#000") + path("M88 41C98 55 114 62 134 64C114 57 104 46 96 38z", "#000")
    return svg(150, 76, body, "xMidYMid meet")


B("craneFly", crane_fly())


def water_lantern() -> str:
    body = radgrad("hl", [(0, "#ffd27a", .75), (.5, "#ff9a4a", .22), (1, "#ff9a4a", 0)]) + lingrad("pe", [(0, "#ffe9f0", 1), (1, "#ffb0c4", 1)])
    body += circ(24, 18, 20, "url(#hl)") + ell(24, 34, 19, 3.6, "#3a2008", "fill-opacity='.7'")
    petal = lambda ang, ln, wd, fill: f"<g transform='translate(24 33) rotate({ang})'><path d='M0 0Q{-wd} {-ln * .55} 0 {-ln}Q{wd} {-ln * .55} 0 0z' fill='{fill}' stroke='#ffd27a' stroke-width='.6' stroke-opacity='.6'/></g>"      # noqa: E731
    body += petal(-58, 15, 5.4, "#ffc0cf") + petal(58, 15, 5.4, "#ffc0cf") + petal(-30, 17, 5.2, "url(#pe)") + petal(30, 17, 5.2, "url(#pe)") + petal(0, 18, 5, "url(#pe)")
    body += path("M24 25Q28 19 24 12Q20 19 24 25z", "#ffb23a") + path("M24 23Q26 19 24 15Q22 19 24 23z", "#fff2b0")
    return svg(48, 40, body, "xMidYMax meet")


B("waterLantern", water_lantern())


def mandala() -> str:
    """A halo of lotus petals: three rings of petals that start outside of the avatar frame and fade towards the tips."""
    cx = cy = 150
    body = "<defs><radialGradient id='m' gradientUnits='userSpaceOnUse' cx='150' cy='150' r='150'><stop offset='.58' stop-color='#000' stop-opacity='1'/><stop offset='.82' stop-color='#000' stop-opacity='.7'/><stop offset='1' stop-color='#000' stop-opacity='.1'/></radialGradient></defs>"
    pt = lambda ang, rad: f"{n(cx + rad * math.cos(ang))} {n(cy + rad * math.sin(ang))}"      # noqa: E731
    for count, r0, r1, wd, fo in ((24, 92, 148, .1, .5), (12, 96, 128, .2, .9), (24, 90, 108, .12, 1)):
        for k in range(count):
            a = math.tau * (k + (.5 if r1 == 148 else 0)) / count
            body += path(f"M{pt(a, r0)}Q{pt(a - wd, (r0 + r1) / 2)} {pt(a, r1)}Q{pt(a + wd, (r0 + r1) / 2)} {pt(a, r0)}z", "url(#m)", f"fill-opacity='{fo}'")
    body += circ(cx, cy, 90, "none", "stroke='#000' stroke-width='2' stroke-opacity='.9'") + circ(cx, cy, 111, "none", "stroke='#000' stroke-width='1' stroke-opacity='.6' stroke-dasharray='2 5'")
    return svg(300, 300, body, "xMidYMid meet")


B("mandala", mandala())
tide("goldWave", 120, 5, "#ffd27a", "#fff1c8")
tide("goldWave2", 180, 4, "#e08a4a", "#ffe9b0", 36, .5)
